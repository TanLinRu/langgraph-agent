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
    3. 语义相似度 > 0.7
    """

    def __init__(
        self,
        token_threshold: float = 0.4,
        semantic_threshold: float = 0.7,
        token_encoding_name: str = "cl100k_base",
    ):
        self.token_threshold = token_threshold
        self.semantic_threshold = semantic_threshold

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
        # 维度1: Token 水位
        if self._check_token_threshold(state):
            return (True, "token_water_level")

        # 维度2: 任务类型
        trigger_type = self._check_task_type(state)
        if trigger_type:
            return (True, f"task_type:{trigger_type}")

        # 维度3: 语义相似度（需要 session_summary）
        if session_summary and self._check_semantic_similarity(state, session_summary):
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

    def _check_semantic_similarity(self, state: "AgentState", session_summary: str) -> bool:
        """检查语义相似度（简化版：Jaccard 关键词重叠）"""
        if not session_summary or not self._encoding:
            return False

        messages = state.get("messages", [])
        if not messages:
            return False

        current_input = ""
        for msg in reversed(messages):
            role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")
            if role == "user":
                content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
                current_input = content.lower()
                break

        if not current_input:
            return False

        summary_words = set(session_summary.lower().split())
        input_words = set(current_input.split())
        overlap = len(summary_words & input_words)
        union = len(summary_words | input_words)
        jaccard = overlap / union if union > 0 else 0

        if jaccard >= self.semantic_threshold:
            logger.debug(f"[RetrievalTrigger] Semantic similarity triggered: {jaccard:.2f}")
            return True
        return False

    def count_tokens(self, text: str) -> int:
        """计算 token 数量"""
        if not self._encoding:
            return len(text) // 4
        return len(self._encoding.encode(text))
