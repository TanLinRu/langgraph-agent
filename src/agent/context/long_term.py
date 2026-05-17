from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime, timedelta
import json
import sqlite3
import logging
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.agent.schemas import ErrorEnvelope, ErrorType, ErrorLevel, structured_catch, UserProfile

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
    memory_ttl_days: int = 30
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

        self._db_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at)
        """)

        # Tool results table for L3 persistence
        self._db_conn.execute("""
            CREATE TABLE IF NOT EXISTS tool_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                tool_call_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT DEFAULT 'success',
                metadata TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(thread_id, tool_call_id)
            )
        """)

        self._db_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tr_thread ON tool_results(thread_id)
        """)

        self._db_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tr_tool_call_id ON tool_results(tool_call_id)
        """)

        self._db_conn.commit()

    @structured_catch(
        error_code="VECTOR_STORE_INIT_ERROR",
        error_type=ErrorType.SYSTEM,
        error_level=ErrorLevel.HIGH,
        suppress=False,
        log_level="error",
    )
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
            try:
                self._vector_store = self._chroma.create_collection(
                    "agent_memory",
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception as e:
                logger.error(f"[LongTerm] ChromaDB 初始化失败: {e}")
                raise

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
            "SELECT value, current_value, conflict_type FROM memories WHERE namespace LIKE ?",
            (ns_str + "|%",),
        )
        results = []
        for row in cursor.fetchall():
            if row["conflict_type"] == "contradiction" and row["current_value"]:
                results.append(f"[冲突历史] {row['value']} → [当前] {row['current_value']}")
            else:
                results.append(row["value"])
        return results

    def search_similar(
        self,
        query: str,
        top_k: int = 3,
        namespace: tuple = ("default", "default", "default", "default"),
    ) -> list[str]:
        """语义搜索（带命名空间隔离）

        ChromaDB 1.x: 使用 get() 获取所有文档并内存过滤
        ChromaDB 0.4.x: 使用 where 过滤器
        """
        if not self._vector_store:
            return []

        ns_str = "|".join(namespace)
        try:
            results = self._vector_store.query(
                query_texts=[query],
                n_results=top_k,
                where={"namespace": {"$gte": ns_str, "$lt": ns_str + "\ufffd"}},
            )
            return results.get("documents", [[]])[0]
        except Exception:
            try:
                results = self._vector_store.query(
                    query_texts=[query],
                    n_results=top_k,
                    where_document={"$contains": ns_str.replace("|", "/")},
                )
                return results.get("documents", [[]])[0]
            except Exception:
                all_docs = self._vector_store.get(limit=50)
                if all_docs and "documents" in all_docs:
                    filtered = [
                        d for d in all_docs["documents"]
                        if ns_str in d
                    ]
                    return filtered[:top_k]
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

    def save_tool_results(self, thread_id: str, results: list[dict]) -> None:
        """批量持久化 tool results 到 L3"""
        if not results:
            return
        for r in results:
            try:
                self._db_conn.execute("""
                    INSERT OR REPLACE INTO tool_results
                        (thread_id, tool_call_id, tool_name, content, status, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    thread_id,
                    r.get("tool_call_id", ""),
                    r.get("tool_name", "unknown"),
                    r.get("content", ""),
                    r.get("status", "success"),
                    r.get("metadata", "{}"),
                ))
            except Exception as e:
                logger.warning(f"[ToolResult] Failed to save {r.get('tool_call_id')}: {e}")
        self._db_conn.commit()
        logger.debug(f"[ToolResult] Saved {len(results)} results for thread={thread_id}")

    def load_tool_result(self, thread_id: str, tool_call_id: str) -> dict | None:
        """加载指定 tool result"""
        cursor = self._db_conn.execute(
            "SELECT * FROM tool_results WHERE thread_id = ? AND tool_call_id = ?",
            (thread_id, tool_call_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "tool_call_id": row["tool_call_id"],
            "tool_name": row["tool_name"],
            "content": row["content"],
            "status": row["status"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
        }

    def load_tool_results_by_thread(self, thread_id: str, limit: int = 50) -> list[dict]:
        """加载指定线程的所有 tool results"""
        cursor = self._db_conn.execute(
            "SELECT * FROM tool_results WHERE thread_id = ? ORDER BY created_at DESC LIMIT ?",
            (thread_id, limit),
        )
        return [
            {
                "tool_call_id": row["tool_call_id"],
                "tool_name": row["tool_name"],
                "content": row["content"],
                "status": row["status"],
                "metadata": json.loads(row["metadata"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in cursor.fetchall()
        ]

    def search_tool_results(self, thread_id: str, query: str, top_k: int = 5) -> list[dict]:
        """按工具名搜索 tool results（基于 SQLite LIKE）"""
        cursor = self._db_conn.execute(
            "SELECT * FROM tool_results WHERE thread_id = ? AND (tool_name LIKE ? OR content LIKE ?) ORDER BY created_at DESC LIMIT ?",
            (thread_id, f"%{query}%", f"%{query}%", top_k),
        )
        return [
            {
                "tool_call_id": row["tool_call_id"],
                "tool_name": row["tool_name"],
                "content": row["content"][:500],
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in cursor.fetchall()
        ]

    USER_PROFILE_KEY = "_user_profile"

    def save_user_profile(self, profile: UserProfile) -> None:
        """保存用户画像到 memories 表"""
        ns = get_namespace(profile.tenant_id, profile.org_id, profile.user_id, "profile")
        ns_str = "|".join(ns)
        profile.last_updated = datetime.now().isoformat()
        value = json.dumps(asdict(profile), ensure_ascii=False)

        self._db_conn.execute("""
            INSERT INTO memories (namespace, memory_key, value, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(namespace, memory_key) DO UPDATE SET
                value = ?,
                updated_at = CURRENT_TIMESTAMP
        """, (ns_str, self.USER_PROFILE_KEY, value, value))
        self._db_conn.commit()
        logger.info(f"[Profile] Saved profile for user={profile.user_id}")

    def load_user_profile(
        self,
        user_id: str,
        tenant_id: str = "default",
        org_id: str = "default",
    ) -> UserProfile | None:
        """加载用户画像"""
        ns = get_namespace(tenant_id, org_id, user_id, "profile")
        ns_str = "|".join(ns)
        cursor = self._db_conn.execute(
            "SELECT value FROM memories WHERE namespace = ? AND memory_key = ?",
            (ns_str, self.USER_PROFILE_KEY),
        )
        row = cursor.fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["value"])
            return UserProfile(**data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"[Profile] Failed to load profile for user={user_id}: {e}")
            return None

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
        """归档 7 天前的会话和 30 天前的记忆，返回归档列表和通知"""
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

    def archive_old_memories(self, ttl_days: int = None) -> tuple[list[str], str]:
        """归档指定天数前的记忆条目（默认 memory_ttl_days）

        清理条件：
        - namespace 不包含 "profile" 和 "config"（保护用户画像和配置）
        - updated_at 早于 cutoff
        - 仅归档 JSONL session 文件中的旧记忆，不修改 memories 表

        Returns:
            (归档 ID 列表, 通知文本)
        """
        if ttl_days is None:
            ttl_days = self.config.memory_ttl_days

        cutoff = datetime.now() - timedelta(days=ttl_days)
        cursor = self._db_conn.execute("""
            SELECT id, namespace, memory_key, value, updated_at
            FROM memories
            WHERE updated_at < ?
              AND namespace NOT LIKE '%|profile'
              AND namespace NOT LIKE '%|config'
              AND namespace NOT LIKE '%|system'
        """, (cutoff.isoformat(),))

        archived_ids = []
        archived_memories = []
        for row in cursor.fetchall():
            row_id = str(row["id"])
            archived_ids.append(row_id)
            archived_memories.append({
                "id": row_id,
                "namespace": row["namespace"],
                "memory_key": row["memory_key"],
                "value": row["value"],
                "updated_at": row["updated_at"],
            })

        if not archived_ids:
            return [], ""

        archive_dir = self.config.memory_dir / "archive" / "memories"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = archive_dir / f"memories_{ts}.jsonl"
        with open(archive_file, "w", encoding="utf-8") as f:
            for mem in archived_memories:
                f.write(json.dumps(mem, ensure_ascii=False, default=str) + "\n")

        placeholders = ",".join("?" * len(archived_ids))
        self._db_conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", archived_ids)
        self._db_conn.commit()

        count = len(archived_ids)
        logger.info(f"[MemoryArchive] Archived {count} memories to {archive_file.name}")
        notification = f"记忆归档完成：{count} 条记忆已归档到 {archive_file.name}，保留目录：{archive_dir}"
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
