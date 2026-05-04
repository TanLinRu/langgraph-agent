from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timedelta
import json
import sqlite3
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings


@dataclass
class LongTermConfig:
    """长期上下文配置"""
    memory_dir: Path = field(default_factory=lambda: Path("./memory"))
    session_ttl_days: int = 7
    vector_enabled: bool = True
    vector_dimension: int = 1536
    chroma_persist_dir: str = "./memory/chroma"


def _msg_content(msg):
    """Get content from message, supports dict and LangChain BaseMessage"""
    if isinstance(msg, dict):
        return msg.get("content", "")
    return getattr(msg, "content", str(msg))


class LongTermManager:
    """长期上下文管理器"""

    def __init__(self, config: LongTermConfig):
        self.config = config
        self._db_conn: Optional[sqlite3.Connection] = None
        self._vector_store = None
        self._ensure_directories()
        self._init_sqlite()
        self._init_chroma()

    def _ensure_directories(self):
        """创建目录结构"""
        (self.config.memory_dir / "memory").mkdir(parents=True, exist_ok=True)
        (self.config.memory_dir / "sessions").mkdir(parents=True, exist_ok=True)
        (self.config.memory_dir / "archive").mkdir(parents=True, exist_ok=True)

    def _init_sqlite(self):
        """初始化 SQLite"""
        db_path = self.config.memory_dir / "sessions.db"
        self._db_conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db_conn.row_factory = sqlite3.Row

        self._db_conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                preview TEXT,
                metadata TEXT
            )
        """)

        self._db_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_thread_id ON sessions(thread_id)
        """)

        self._db_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_updated_at ON sessions(updated_at)
        """)

        self._db_conn.commit()

    def _init_chroma(self):
        """初始化 ChromaDB"""
        if not self.config.vector_enabled:
            self._vector_store = None
            return

        self._chroma = chromadb.Client(ChromaSettings(
            persist_directory=self.config.chroma_persist_dir,
            anonymized_telemetry=False
        ))

        try:
            self._vector_store = self._chroma.get_collection("agent_memory")
        except Exception:
            self._vector_store = self._chroma.create_collection(
                "agent_memory",
                metadata={"hnsw:space": "cosine"}
            )

    def load_memory(self) -> str:
        """加载语义记忆 (MEMORY.md)"""
        memory_file = self.config.memory_dir / "memory" / "MEMORY.md"
        if not memory_file.exists():
            return ""
        return memory_file.read_text(encoding="utf-8")

    def write_memory(self, content: str, category: str = "general") -> None:
        """写入语义记忆（追加）"""
        memory_file = self.config.memory_dir / "memory" / "MEMORY.md"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        entry = f"\n### {timestamp} [{category}]\n{content}\n"

        existing = memory_file.read_text(encoding="utf-8") if memory_file.exists() else ""
        memory_file.write_text(existing + entry, encoding="utf-8")

        if self._vector_store:
            self._vector_store.add(
                documents=[content],
                ids=[f"memory_{datetime.now().timestamp()}"],
                metadatas=[{"category": category, "timestamp": timestamp}]
            )

    def search_similar(self, query: str, top_k: int = 3) -> list[str]:
        """语义搜索"""
        if not self._vector_store:
            return []

        try:
            results = self._vector_store.query(
                query_texts=[query],
                n_results=top_k
            )
            return results.get("documents", [[]])[0]
        except Exception:
            return []

    def save_session(self, thread_id: str, messages: list, metadata: dict) -> None:
        """保存会话到 SQLite 和 JSONL"""
        preview = _msg_content(messages[-1])[:200] if messages else ""

        self._db_conn.execute("""
            INSERT INTO sessions (thread_id, updated_at, message_count, preview, metadata)
            VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP,
                message_count = ?,
                preview = ?,
                metadata = ?
        """, (thread_id, len(messages), preview, json.dumps(metadata),
              len(messages), preview, json.dumps(metadata)))

        self._db_conn.commit()

        session_file = self.config.memory_dir / "sessions" / f"{thread_id}.jsonl"

        last_turn = self._get_last_turn_count(session_file)
        delta = messages[last_turn:]

        if delta:
            with open(session_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "messages": delta,
                    "turn_offset": last_turn,
                }, ensure_ascii=False, default=str) + "\n")

    def _get_last_turn_count(self, session_file: Path) -> int:
        """获取当前已保存的消息总数"""
        if not session_file.exists():
            return 0

        total = 0
        with open(session_file, encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                total += len(data.get("messages", []))
        return total

    def load_recent_sessions(self, limit: int = 5) -> list[dict]:
        """加载最近的 N 个会话"""
        cursor = self._db_conn.execute("""
            SELECT thread_id, preview, metadata, updated_at
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))

        return [
            {
                "thread_id": row["thread_id"],
                "preview": row["preview"],
                "metadata": json.loads(row["metadata"] or "{}"),
                "updated_at": row["updated_at"]
            }
            for row in cursor.fetchall()
        ]

    def load_session_messages(self, thread_id: str) -> list:
        """加载指定会话的所有消息"""
        session_file = self.config.memory_dir / "sessions" / f"{thread_id}.jsonl"

        if not session_file.exists():
            return []

        messages = []
        with open(session_file, encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                messages.extend(data.get("messages", []))

        return messages

    def get_latest_thread(self) -> Optional[str]:
        """获取最近会话 ID"""
        cursor = self._db_conn.execute("""
            SELECT thread_id FROM sessions
            ORDER BY updated_at DESC LIMIT 1
        """)
        row = cursor.fetchone()
        return row["thread_id"] if row else None

    def archive_old_sessions(self) -> tuple[list[str], str]:
        """归档 7 天前的会话，返回归档列表和通知"""
        cutoff = datetime.now() - timedelta(days=self.config.session_ttl_days)

        cursor = self._db_conn.execute("""
            SELECT thread_id FROM sessions
            WHERE updated_at < ?
        """, (cutoff.isoformat(),))

        archived_ids = []
        for row in cursor.fetchall():
            thread_id = row["thread_id"]
            archived_ids.append(thread_id)

            session_file = self.config.memory_dir / "sessions" / f"{thread_id}.jsonl"
            if session_file.exists():
                dest = self.config.memory_dir / "archive" / f"{thread_id}.jsonl"
                session_file.rename(dest)

            self._db_conn.execute("DELETE FROM sessions WHERE thread_id = ?", (thread_id,))

        self._db_conn.commit()

        notification = self._generate_notification(archived_ids)
        return archived_ids, notification

    def _generate_notification(self, sessions: list[str]) -> str:
        """生成归档通知"""
        if not sessions:
            return ""

        return f"""
归档通知

已归档 {len(sessions)} 个会话:
{chr(10).join(f'- {s}' for s in sessions)}

归档位置: {self.config.memory_dir / 'archive'}
如需恢复，请联系管理员。

归档时间: {datetime.now().isoformat()}
"""

    def close(self):
        """关闭连接"""
        if self._db_conn:
            self._db_conn.close()
