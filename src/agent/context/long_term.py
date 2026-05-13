from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timedelta
import json
import sqlite3
import logging
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)


def get_namespace(
    tenant_id: str = "default",
    org_id: str = "default",
    user_id: str = "default",
    memory_type: str = "default",
) -> tuple[str, str, str, str]:
    """Namespace 设计：租户 > 组织 > 用户 > 记忆类型

    设计参考: docs/context_design.md 8.1 节
    """
    return (tenant_id, org_id, user_id, memory_type)


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


def _msg_role(msg):
    """Get role from message"""
    if isinstance(msg, dict):
        return msg.get("role", "")
    return getattr(msg, "role", "")


def _deduplicate_messages(messages: list) -> list:
    """去重消息列表"""
    if not messages:
        return []
    seen = set()
    result = []
    for msg in messages:
        role = _msg_role(msg)
        content = _msg_content(msg)
        if not content:
            content = str(msg)
        key = f"{role}:{content[:100]}"
        if key in seen:
            continue
        seen.add(key)
        result.append(msg)
    return result


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
                tenant_id TEXT DEFAULT 'default',
                org_id TEXT DEFAULT 'default',
                user_id TEXT DEFAULT 'default',
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

        # Memory entries table for conflict tracking
        self._db_conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                value TEXT NOT NULL,
                current_value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                value_history TEXT DEFAULT '[]',
                conflict_type TEXT,
                UNIQUE(namespace, memory_key)
            )
        """)

        self._db_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_namespace ON memories(namespace)
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

    def write_memory(
        self,
        content: str,
        category: str = "general",
        namespace: tuple = ("default", "default", "default", "default"),
        memory_key: str | None = None,
    ) -> str:
        """写入语义记忆（支持冲突检测）

        Returns:
            操作类型: "add" | "update" | "noop"
        """
        from .conflict_resolver import resolve_memory_conflict, MemoryEntry, MemoryOp

        ns_str = "|".join(namespace)
        key = memory_key or f"{category}_{datetime.now().timestamp()}"

        # 查找已存在的记忆
        cursor = self._db_conn.execute(
            "SELECT * FROM memories WHERE namespace = ? AND memory_key = ?",
            (ns_str, key),
        )
        row = cursor.fetchone()

        if row:
            # 冲突检测与解决
            old_mem = MemoryEntry(
                id=str(row["id"]),
                namespace=namespace,
                key=key,
                value=row["value"],
                current_value=row["current_value"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                value_history=json.loads(row["value_history"] or "[]"),
                conflict_type=row["conflict_type"],
            )
            op, updated = resolve_memory_conflict(old_mem, content)

            if op == MemoryOp.NOOP:
                logger.debug(f"[Memory] No-op for {key}")
                return "noop"

            self._db_conn.execute("""
                UPDATE memories
                SET value = ?, current_value = ?, updated_at = CURRENT_TIMESTAMP,
                    value_history = ?, conflict_type = ?
                WHERE namespace = ? AND memory_key = ?
            """, (
                updated.value,
                updated.current_value or updated.value,
                json.dumps(updated.value_history),
                updated.conflict_type,
                ns_str, key,
            ))
            self._db_conn.commit()
            logger.info(f"[Memory] Conflict resolved ({updated.conflict_type}): {key}")
            return "update"
        else:
            # 新增记忆
            self._db_conn.execute("""
                INSERT INTO memories (namespace, memory_key, value, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (ns_str, key, content))
            self._db_conn.commit()
            logger.info(f"[Memory] Added new: {key}")
            return "add"

    def read_memories(
        self,
        namespace: tuple = ("default", "default", "default", "default"),
        memory_type: str = "default",
    ) -> list[str]:
        """读取指定 namespace 的所有记忆值"""
        ns_str = "|".join(namespace)
        cursor = self._db_conn.execute(
            "SELECT value, current_value, conflict_type FROM memories WHERE namespace LIKE ? || '%'",
            (ns_str[:ns_str.index("|")],),
        )
        results = []
        for row in cursor.fetchall():
            if row["conflict_type"] == "contradiction" and row["current_value"]:
                results.append(f"[冲突历史] {row['value']} → [当前] {row['current_value']}")
            else:
                results.append(row["value"])
        return results

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
        """获取当前已保存的消息总数 - 优化：只读最后一行"""
        if not session_file.exists():
            return 0

        try:
            with open(session_file, "rb") as f:
                f.seek(0, 2)
                file_size = f.tell()
                if file_size == 0:
                    return 0
                f.seek(max(0, file_size - 4096))
                tail = f.read().decode('utf-8')
                lines = tail.split('\n')
                for line in reversed(lines):
                    if line.strip():
                        data = json.loads(line)
                        return data.get("turn_offset", 0) + len(data.get("messages", []))
        except (json.JSONDecodeError, OSError):
            pass
        return 0

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

    def load_session_messages(self, thread_id: str, max_messages: int = 20) -> list:
        """加载指定会话的消息（已去重，最多 max_messages 条）"""
        session_file = self.config.memory_dir / "sessions" / f"{thread_id}.jsonl"

        if not session_file.exists():
            return []

        messages = []
        with open(session_file, encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                messages.extend(data.get("messages", []))

        deduped = _deduplicate_messages(messages)
        return deduped[-max_messages:]

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
