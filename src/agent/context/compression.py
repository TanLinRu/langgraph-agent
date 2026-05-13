from dataclasses import dataclass, field
from typing import Optional, Callable
import tiktoken
import logging
from langchain_core.language_models import BaseChatModel

from .tool_result_store import ToolResultStore, ToolResultSummary

logger = logging.getLogger(__name__)


def _msg_get(msg, key, default=None):
    """Get attribute from message, supports dict and LangChain BaseMessage"""
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


def _msg_content(msg) -> str:
    return _msg_get(msg, "content", "")


def _msg_role(msg) -> str:
    return _msg_get(msg, "role", "")


def _msg_id(msg) -> str:
    """Get message ID (tool_call_id for tool messages)"""
    if isinstance(msg, dict):
        return msg.get("tool_call_id", "") or msg.get("id", "")
    return getattr(msg, "tool_call_id", None) or getattr(msg, "id", "")


@dataclass
class CompressionConfig:
    """压缩配置"""
    max_tokens: int = 128000
    trigger_threshold: float = 0.7
    keep_recent: int = 5
    summary_max_tokens: int = 500
    hot_zone_size: int = 5


@dataclass
class CompressedTurn:
    """结构化压缩后的单轮对话

    设计参考: docs/context_design.md 7.1 节
    """
    turn_index: int
    user_intent: str
    key_facts: list[str] = field(default_factory=list)
    tool_actions: list[dict] = field(default_factory=list)  # [{name, params, status}]
    unresolved: list[str] = field(default_factory=list)
    compression_rationale: str = ""


@dataclass
class CompressionResult:
    """压缩结果"""
    compressed_messages: list
    compressed_turns: list[CompressedTurn]
    original_count: int
    compressed_count: int
    compression_ratio: float
    token_saved: int


class ContextCompressor:
    """上下文压缩器 - LLM 摘要策略 + Hot Zone 管理

    设计参考: docs/context_design.md 4.1 节
    """

    def __init__(self, config: CompressionConfig, llm: Optional[BaseChatModel] = None):
        self.config = config
        self.llm = llm
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self._tool_store = ToolResultStore(hot_zone_size=config.hot_zone_size)

    def should_compress(self, messages: list) -> bool:
        """判断是否需要压缩"""
        total_tokens = self._count_tokens(messages)
        ratio = total_tokens / self.config.max_tokens
        return ratio >= self.config.trigger_threshold

    def compress(self, messages: list) -> list:
        """执行 LLM 摘要压缩"""
        if not self.should_compress(messages):
            return messages

        system = [m for m in messages if _msg_role(m) == "system"]
        tools = [m for m in messages if _msg_role(m) == "tool"]
        user_assistant = [m for m in messages if _msg_role(m) in ("user", "assistant")]

        if not user_assistant:
            return messages

        # 先将 tool results 存入 Hot Zone store
        for tool_msg in tools:
            tool_call_id = _msg_id(tool_msg)
            tool_name = _msg_get(tool_msg, "name", "unknown")
            content = _msg_content(tool_msg)
            status = "success" if _msg_role(tool_msg) == "tool" else "failed"
            if tool_call_id:
                self._tool_store.store(tool_call_id, tool_name, content, status)

        # 生成结构化压缩
        compressed_turns = self._build_compressed_turns(user_assistant, tools)
        summary = self._llm_summarize_turns(compressed_turns)

        # 保留最近对话 + Hot Zone tools
        recent_conversations = user_assistant[-self.config.keep_recent:]
        hot_zone_summaries = self._tool_store.get_hot_zone()

        compressed = []
        compressed.extend(system)
        compressed.append({
            "role": "system",
            "content": f"【之前对话摘要】\n{summary[:self.config.summary_max_tokens * 4]}",
            "name": "context_summary",
            "compressed_turns": [self._turn_to_dict(ct) for ct in compressed_turns],
        })
        compressed.extend(recent_conversations)
        # Hot Zone 的 tool result 摘要作为结构化记录
        for hs in hot_zone_summaries:
            compressed.append({
                "role": "tool",
                "tool_call_id": hs.tool_call_id,
                "name": hs.tool_name,
                "content": hs.summary,
                "status": hs.status,
                "is_hot_zone": True,
            })

        original_tokens = self._count_tokens(messages)
        compressed_tokens = self._count_tokens(compressed)
        logger.info(
            f"[LLM Compress] Compressed: {len(messages)} msgs / {original_tokens} tokens"
            f" -> {len(compressed)} msgs / {compressed_tokens} tokens"
        )

        return compressed

    def _build_compressed_turns(
        self, user_assistant: list, tools: list
    ) -> list[CompressedTurn]:
        """将 user/assistant 对转换为 CompressedTurn 结构化记录"""
        turns = []
        tool_map: dict[str, list[dict]] = {}

        # 按 tool_call_id 聚合 tool results
        for tool_msg in tools:
            tc_id = _msg_id(tool_msg)
            if tc_id:
                tool_map.setdefault(tc_id, [])
                tool_map[tc_id].append({
                    "name": _msg_get(tool_msg, "name", "unknown"),
                    "content": _msg_content(tool_msg)[:200],
                    "status": "success" if _msg_role(tool_msg) == "tool" else "failed",
                })

        # 将 user/assistant pair 转换为 turn
        for i, msg in enumerate(user_assistant):
            if _msg_role(msg) == "user":
                turn = CompressedTurn(
                    turn_index=i // 2,
                    user_intent=_msg_content(msg)[:200],
                    key_facts=[],
                    tool_actions=tool_map.get(_msg_id(msg), []),
                    unresolved=[],
                    compression_rationale="超过保留轮次，压缩归档",
                )
                turns.append(turn)

        return turns

    def _turn_to_dict(self, turn: CompressedTurn) -> dict:
        return {
            "turn_index": turn.turn_index,
            "user_intent": turn.user_intent,
            "key_facts": turn.key_facts,
            "tool_actions": turn.tool_actions,
            "unresolved": turn.unresolved,
            "compression_rationale": turn.compression_rationale,
        }

    def _llm_summarize_turns(self, turns: list[CompressedTurn]) -> str:
        """基于结构化 turns 生成摘要"""
        if not self.llm:
            return self._fallback_summarize_turns(turns)

        turn_texts = []
        for t in turns:
            tool_info = ""
            if t.tool_actions:
                tool_info = f", 工具: {', '.join(a['name'] for a in t.tool_actions)}"
            turn_texts.append(f"Turn {t.turn_index}: {t.user_intent}{tool_info}")

        prompt = f"""请用 3-5 句话概括以下对话的关键信息。

要求：
- 保留关键决策和结论
- 记录未完成的任务
- 提取重要的技术和事实信息
- 不要包含详细的推理过程

对话：
{chr(10).join(turn_texts)}

摘要："""

        import time
        start_time = time.time()
        logger.info(f"[LLM Summarize] Starting summarization for {len(turns)} turns")

        try:
            response = self.llm.invoke(prompt)
            elapsed = time.time() - start_time
            logger.info(f"[LLM Summarize] Completed in {elapsed:.2f}s")
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[LLM Summarize] Failed after {elapsed:.2f}s: {e}")
            return self._fallback_summarize_turns(turns)

    def _fallback_summarize_turns(self, turns: list[CompressedTurn]) -> str:
        """回退摘要"""
        key_points = []
        for t in turns[-5:]:
            if t.user_intent:
                key_points.append(f"用户询问: {t.user_intent[:100]}")
        return " / ".join(key_points) if key_points else "对话已压缩"

    def _llm_summarize(self, messages: list) -> str:
        """调用 LLM 摘要（兼容旧接口）"""
        if not self.llm:
            return self._fallback_summarize(messages)

        formatted = []
        for m in messages:
            role = _msg_role(m)
            content = _msg_content(m)
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
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[LLM Summarize] Failed after {elapsed:.2f}s: {e}")
            return self._fallback_summarize(messages)

    def _fallback_summarize(self, messages: list) -> str:
        """回退摘要（简单实现）"""
        key_points = []
        for m in messages[-10:]:
            role = _msg_role(m)
            if role == "user":
                key_points.append(f"用户询问: {_msg_content(m)[:100]}")
            elif role == "assistant" and _msg_content(m):
                key_points.append(f"回复: {_msg_content(m)[:100]}")
        return " / ".join(key_points[:5]) if key_points else "对话已压缩"

    def _count_tokens(self, messages: list) -> int:
        """计算 token 数量"""
        return sum(
            len(self.encoding.encode(_msg_content(m) or ""))
            for m in messages
        )

    def access_tool(self, tool_call_id: str) -> dict | None:
        """访问 tool result 并提升热度"""
        return self._tool_store.access(tool_call_id)

    def get_hot_zone(self) -> list[ToolResultSummary]:
        """获取当前 Hot Zone"""
        return self._tool_store.get_hot_zone()

