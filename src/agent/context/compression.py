from dataclasses import dataclass
from typing import Optional, Callable
import tiktoken
import logging
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


def _msg_get(msg, key, default=None):
    """Get attribute from message, supports dict and LangChain BaseMessage"""
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


@dataclass
class CompressionConfig:
    """压缩配置"""
    max_tokens: int = 128000
    trigger_threshold: float = 0.7
    keep_recent: int = 5
    summary_max_tokens: int = 500


class ContextCompressor:
    """上下文压缩器 - LLM 摘要策略"""

    def __init__(self, config: CompressionConfig, llm: Optional[BaseChatModel] = None):
        self.config = config
        self.llm = llm
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def should_compress(self, messages: list) -> bool:
        """判断是否需要压缩"""
        total_tokens = self._count_tokens(messages)
        ratio = total_tokens / self.config.max_tokens
        return ratio >= self.config.trigger_threshold

    def compress(self, messages: list) -> list:
        """执行 LLM 摘要压缩"""
        if not self.should_compress(messages):
            return messages

        system = [m for m in messages if _msg_get(m, "role") == "system"]
        non_system = [m for m in messages if _msg_get(m, "role") != "system"]
        tools = [m for m in messages if _msg_get(m, "role") == "tool"]
        user_assistant = [m for m in messages if _msg_get(m, "role") in ("user", "assistant")]

        if not user_assistant:
            return messages

        summary = self._llm_summarize(user_assistant)

        recent_conversations = user_assistant[-self.config.keep_recent:]
        recent_tools = tools[-self.config.keep_recent:]

        compressed = []
        compressed.extend(system)
        compressed.append({
            "role": "system",
            "content": f"【之前对话摘要】\n{summary[:self.config.summary_max_tokens * 4]}",
            "name": "context_summary"
        })
        compressed.extend(recent_conversations)
        compressed.extend(recent_tools)

        logger.info(f"[LLM Compress] Compressed: {len(messages)} -> {len(compressed)} messages")

        return compressed

    def _llm_summarize(self, messages: list) -> str:
        """调用 LLM 摘要"""
        if not self.llm:
            return self._fallback_summarize(messages)

        formatted = []
        for m in messages:
            role = _msg_get(m, "role", "unknown")
            content = _msg_get(m, "content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            formatted.append(f"{role}: {content}")

        prompt = f"""请用 3-5 句话概括以下对话的关键信息。

要求：
- 保留关键决策和结论
- 记录未完成的任务
- 提取重要的技术和事实信息
- 不要包含详细的推理过程

对话：
{chr(10).join(formatted)}

摘要："""

        import time
        start_time = time.time()

        logger.info(f"[LLM Summarize] Starting summarization for {len(messages)} messages")

        try:
            response = self.llm.invoke(prompt)
            elapsed = time.time() - start_time
            logger.info(f"[LLM Summarize] Completed in {elapsed:.2f}s")

            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[LLM Summarize] Failed after {elapsed:.2f}s: {e}")
            return self._fallback_summarize(messages)

    def _fallback_summarize(self, messages: list) -> str:
        """回退摘要（简单实现）"""
        key_points = []
        for m in messages[-10:]:
            if _msg_get(m, "role") == "user":
                key_points.append(f"用户询问: {_msg_get(m, 'content', '')[:100]}")
            elif _msg_get(m, "role") == "assistant" and _msg_get(m, "content"):
                key_points.append(f"回复: {_msg_get(m, 'content', '')[:100]}")

        return " / ".join(key_points[:5]) if key_points else "对话已压缩"

    def _count_tokens(self, messages: list) -> int:
        """计算 token 数量"""
        return sum(
            len(self.encoding.encode(_msg_get(m, "content", "")))
            for m in messages
        )
