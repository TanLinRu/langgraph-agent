from typing import TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ..state import AgentState

logger = logging.getLogger(__name__)

PLANNING_KEYWORDS = ["计划", "规划", "怎么实现", "如何做", "步骤", "方案"]
REFLECTION_KEYWORDS = ["反思", "回顾", "分析", "为什么", "原因是什么", "出了什么问题"]
COMPARISON_KEYWORDS = ["对比", "比较", "哪个好", "有什么区别", "差异", "优缺点"]


class RetrievalTrigger:
    """多维检索触发判断

    设计参考: docs/context_design.md 5.2 节
    触发条件（满足任一即触发）:
    1. token水位 > 40%
    2. 任务类型 in [planning, reflection, comparison]
    3. 向量语义相似度 > threshold (ChromaDB cosine)
    """

    def __init__(
        self,
        token_threshold: float = 0.4,
        semantic_threshold: float = 0.7,
        token_encoding_name: str = "cl100k_base",
        long_term_manager=None,
    ):
        self.token_threshold = token_threshold
        self.semantic_threshold = semantic_threshold
        self._long_term = long_term_manager

        try:
            import tiktoken
            self._encoding = tiktoken.get_encoding(token_encoding_name)
        except Exception:
            logger.warning("[RetrievalTrigger] tiktoken not available, token counting disabled")
            self._encoding = None

    def should_retrieve(
        self,
        state: "AgentState",
        session_summary: str = "",
    ) -> tuple[bool, str]:
        """
        判断是否需要触发跨会话检索

        Returns:
            (是否触发, 触发原因)
        """
        if self._check_token_threshold(state):
            return (True, "token_water_level")

        trigger_type = self._check_task_type(state)
        if trigger_type:
            return (True, f"task_type:{trigger_type}")

        if self._check_semantic_similarity(state):
            return (True, "semantic_similarity")

        return (False, "")

    def _check_token_threshold(self, state: "AgentState") -> bool:
        """检查 token 水位是否超过阈值"""
        token_usage = state.get("token_usage", {})
        percentage = token_usage.get("percentage", 0)
        if percentage and percentage / 100 >= self.token_threshold:
            logger.debug(f"[RetrievalTrigger] Token threshold triggered: {percentage}%")
            return True
        return False

    def _check_task_type(self, state: "AgentState") -> str | None:
        """检查任务类型是否需要检索"""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_user_msg = ""
        for msg in reversed(messages):
            role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")
            if role == "user":
                content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
                last_user_msg = content.lower()
                break

        if not last_user_msg:
            return None

        for kw in PLANNING_KEYWORDS:
            if kw in last_user_msg:
                logger.debug("[RetrievalTrigger] Planning task detected")
                return "planning"

        for kw in REFLECTION_KEYWORDS:
            if kw in last_user_msg:
                logger.debug("[RetrievalTrigger] Reflection task detected")
                return "reflection"

        for kw in COMPARISON_KEYWORDS:
            if kw in last_user_msg:
                logger.debug("[RetrievalTrigger] Comparison task detected")
                return "comparison"

        return None

    def _check_semantic_similarity(self, state: "AgentState") -> bool:
        """检查向量语义相似度（ChromaDB cosine similarity）

        使用 ChromaDB 向量检索替代 Jaccard 关键词匹配。
        当 long_term_manager 不可用时降级为 Jaccard（向后兼容）。
        """
        messages = state.get("messages", [])
        if not messages:
            return False

        current_input = ""
        for msg in reversed(messages):
            role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")
            if role == "user":
                content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
                current_input = content
                break

        if not current_input:
            return False

        if not self._long_term:
            if self._encoding and self.semantic_threshold < 1.0:
                return self._jaccard_fallback(state)
            return False

        tenant_id = state.get("tenant_id", "default")
        org_id = state.get("org_id", "default")
        user_id = state.get("user_id", "default")
        ns = (tenant_id, org_id, user_id, "memory")

        results = self._long_term.search_similar(
            query=current_input,
            top_k=3,
            namespace=ns,
        )
        if results and len(results) > 0:
            similarity = results[0].get("_distance", 0)
            if similarity is not None:
                score = 1.0 - similarity
                if score >= self.semantic_threshold:
                    logger.debug(f"[RetrievalTrigger] Vector similarity triggered: score={score:.3f}")
                    return True

        return False

    def _jaccard_fallback(self, state: "AgentState") -> bool:
        """Jaccard 降级：当无 long_term_manager 时使用"""
        if not self._encoding:
            return False

        messages = state.get("messages", [])
        if not messages:
            return False

        all_content = " ".join(
            _msg_content(m).lower()
            for m in messages
            if _msg_content(m) and isinstance(m, dict) and m.get("role") not in ("tool",)
        )

        if not all_content:
            return False

        current_words = set(all_content.split())
        last_user = ""
        for msg in reversed(messages):
            role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")
            if role == "user":
                last_user = (msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")).lower()
                break

        if not last_user:
            return False

        user_words = set(last_user.split())
        overlap = len(current_words & user_words)
        union = len(current_words | user_words)
        jaccard = overlap / union if union > 0 else 0

        if jaccard >= self.semantic_threshold:
            logger.debug(f"[RetrievalTrigger] Jaccard fallback triggered: {jaccard:.2f}")
            return True
        return False

    def count_tokens(self, text: str) -> int:
        """计算 token 数量"""
        if not self._encoding:
            return len(text) // 4
        return len(self._encoding.encode(text))


def _msg_content(msg):
    if isinstance(msg, dict):
        return msg.get("content", "")
    return getattr(msg, "content", str(msg))
