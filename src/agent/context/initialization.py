from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import logging

from .long_term import LongTermManager
from ..config import InitializationConfig, ShortTermConfig

logger = logging.getLogger(__name__)


class ContextInitializer:
    """上下文初始化器 - 服务重启时恢复状态"""

    def __init__(
        self,
        long_term_manager: LongTermManager,
        config: InitializationConfig
    ):
        self.long_term = long_term_manager
        self.config = config

    def initialize(self, thread_id: Optional[str] = None) -> dict:
        """初始化上下文"""
        context = {
            "system": [],
            "messages": [],
            "metadata": {}
        }

        context["system"].append(self._load_system_prompt())
        context["system"].append(self._load_skills_index())

        if self.config.load_memory:
            memory = self.long_term.load_memory()
            if memory:
                context["system"].append({
                    "type": "system",
                    "content": f"【长期记忆】\n{memory}",
                    "source": "memory"
                })

        if self.config.search_similar and thread_id:
            similar = self.long_term.search_similar(
                query=f"thread:{thread_id}",
                top_k=3
            )
            if similar:
                context["system"].append({
                    "type": "system",
                    "content": f"【相关记忆】\n" + "\n---\n".join(similar),
                    "source": "vector_search"
                })

        if self.config.resume_on_startup:
            if thread_id:
                session_messages = self.long_term.load_session_messages(thread_id)
            else:
                latest_thread = self.long_term.get_latest_thread()
                if latest_thread:
                    thread_id = latest_thread
                    session_messages = self.long_term.load_session_messages(thread_id)
                else:
                    session_messages = []

            if session_messages:
                context["messages"] = session_messages
                context["metadata"]["resumed"] = True
                context["metadata"]["thread_id"] = thread_id

        context["system"].append({
            "type": "system",
            "content": self._build_runtime_context(context["metadata"].get("thread_id")),
            "source": "runtime"
        })

        return context

    def _load_system_prompt(self) -> dict:
        """加载系统提示"""
        try:
            from ..prompts.system_prompt import SYSTEM_PROMPT
            return {
                "type": "system",
                "content": SYSTEM_PROMPT,
                "source": "system_prompt"
            }
        except ImportError:
            return {
                "type": "system",
                "content": "You are a helpful assistant.",
                "source": "system_prompt"
            }

    def _load_skills_index(self) -> dict:
        """加载 Skills 索引"""
        try:
            from ..skills import SKILLS_INDEX
            return {
                "type": "system",
                "content": SKILLS_INDEX,
                "source": "skills_index"
            }
        except ImportError:
            return {
                "type": "system",
                "content": "No skills available.",
                "source": "skills_index"
            }

    def _build_runtime_context(self, thread_id: Optional[str]) -> str:
        """构建运行时上下文"""
        return f"""
## 运行时信息
- 初始化时间: {datetime.now().isoformat()}
- 会话ID: {thread_id or 'new'}
- 服务状态: 已重启恢复
"""
