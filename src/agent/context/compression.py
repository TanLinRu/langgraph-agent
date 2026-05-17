from dataclasses import dataclass, field
from typing import Optional, Callable
import tiktoken
import logging
from langchain_core.language_models import BaseChatModel

from .tool_result_store import ToolResultStore, ToolResultSummary
from src.agent.schemas import ErrorEnvelope, ErrorType, ErrorLevel, structured_catch

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
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


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

    def _dump_messages_debug(self, messages: list, tag: str) -> None:
        """Dump full message content to DEBUG log"""
        logger.debug("")
        logger.debug(f"=== [{tag}] {len(messages)} messages ===")
        for i, msg in enumerate(messages):
            role = _msg_role(msg)
            content = _msg_content(msg)
            tokens = self._count_tokens([msg])
            logger.debug(f"  [{i}] {role} ({tokens} tokens):")
            if isinstance(content, str):
                for line in content.split("\n"):
                    if line.strip():
                        logger.debug(f"      {line}")
            else:
                logger.debug(f"      {content}")
            logger.debug(f"  [end msg {i}]")

    def compress(self, messages: list) -> "CompressionResult":
        """Execute LLM summary compression"""
        errors = []
        warnings = []

        logger.debug(f"")
        logger.debug(f"=== [COMPRESSION] compress() called with {len(messages)} messages ===")
        self._dump_messages_debug(messages, "COMPRESS_INPUT")

        if not self.should_compress(messages):
            logger.info(f"[COMPRESSION] Should not compress: {self._count_tokens(messages)} tokens < {self.config.max_tokens * self.config.trigger_threshold:.0f} threshold")
            return CompressionResult(
                compressed_messages=messages,
                compressed_turns=[],
                original_count=len(messages),
                compressed_count=len(messages),
                compression_ratio=1.0,
                token_saved=0,
                errors=errors,
                warnings=warnings,
            )

        system = [m for m in messages if _msg_role(m) == "system"]
        user_assistant = [m for m in messages if _msg_role(m) in ("user", "assistant")]

        logger.debug(f"[COMPRESSION] Partition: system={len(system)}, user_assistant={len(user_assistant)}")

        if not user_assistant:
            return CompressionResult(
                compressed_messages=messages,
                compressed_turns=[],
                original_count=len(messages),
                compressed_count=len(messages),
                compression_ratio=1.0,
                token_saved=0,
                errors=errors,
                warnings=warnings,
            )

        try:
            compressed_turns = self._build_compressed_turns(user_assistant)
            logger.debug(f"[COMPRESSION] Built {len(compressed_turns)} compressed turns")

            self._enrich_turns_with_llm(compressed_turns, errors, warnings)

            summary = self._llm_summarize_turns(compressed_turns, errors, warnings)
            logger.debug(f"[COMPRESSION] LLM summary length: {len(summary)} chars")

            recent_conversations = user_assistant[-self.config.keep_recent:]

            compressed = []
            if system:
                merged_content = "\n\n".join(m.get("content", "") for m in system)
                summary_content = f"\n\n【之前对话摘要】\n{summary[:self.config.summary_max_tokens * 4]}"
                merged_system = {
                    "role": "system",
                    "content": merged_content + summary_content,
                    "name": "context_summary",
                    "compressed_turns": [self._turn_to_dict(ct) for ct in compressed_turns],
                }
                compressed.append(merged_system)
            else:
                compressed.append({
                    "role": "system",
                    "name": "context_summary",
                    "content": f"【之前对话摘要】\n{summary[:self.config.summary_max_tokens * 4]}",
                    "compressed_turns": [self._turn_to_dict(ct) for ct in compressed_turns],
                })
            compressed.extend(recent_conversations)

            logger.debug(f"[COMPRESSION] Built compressed result: system={len(system)} merged, recent={len(recent_conversations)}")
            self._dump_messages_debug(compressed, "COMPRESS_OUTPUT")

            original_tokens = self._count_tokens(messages)
            compressed_tokens = self._count_tokens(compressed)
            logger.info(
                f"[LLM Compress] Compressed: {len(messages)} msgs / {original_tokens} tokens"
                f" -> {len(compressed)} msgs / {compressed_tokens} tokens"
            )

            return CompressionResult(
                compressed_messages=compressed,
                compressed_turns=compressed_turns,
                original_count=len(messages),
                compressed_count=len(compressed),
                compression_ratio=len(compressed) / max(len(messages), 1),
                token_saved=original_tokens - compressed_tokens,
                errors=errors,
                warnings=warnings,
            )
        except Exception as e:
            errors.append({"phase": "compression", "error": str(e), "type": type(e).__name__})
            logger.error(f"[COMPRESSION] Failed: {e}")
            return CompressionResult(
                compressed_messages=messages,
                compressed_turns=[],
                original_count=len(messages),
                compressed_count=len(messages),
                compression_ratio=1.0,
                token_saved=0,
                errors=errors,
                warnings=warnings,
            )

    def _enrich_turns_with_llm(self, turns: list[CompressedTurn], errors: list, warnings: list) -> None:
        """LLM 提取 key_facts 和 unresolved (OpenCode 模式)"""
        if not self.llm or not turns:
            return

        turn_texts = []
        for t in turns:
            tool_names = [a["name"] for a in t.tool_actions] if t.tool_actions else ["无"]
            turn_texts.append(
                f"Turn {t.turn_index}: 意图={t.user_intent[:100]} | "
                f"工具={', '.join(tool_names)}"
            )

        prompt = f"""分析以下对话轮次，提取关键信息。

对于每个轮次，请用 JSON 格式返回：
{{
  "turns": [
    {{
      "turn_index": 数字,
      "key_facts": ["关键事实1", "关键事实2"],
      "unresolved": ["待解决问题1", "待解决问题2"]
    }}
  ]
}}

对话：
{chr(10).join(turn_texts)}

JSON："""

        try:
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            import json
            import re

            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
                turn_map = {t["turn_index"]: t for t in data.get("turns", [])}
                for turn in turns:
                    if turn.turn_index in turn_map:
                        info = turn_map[turn.turn_index]
                        turn.key_facts = info.get("key_facts", [])
                        turn.unresolved = info.get("unresolved", [])
            logger.info(f"[LLM Enrich] Extracted facts/unresolved for {len(turns)} turns")
        except Exception as e:
            error_msg = f"LLM enrichment failed: {e}"
            logger.warning(f"[LLM Enrich] Failed: {e}, using empty fields")
            warnings.append({"phase": "llm_enrichment", "warning": error_msg, "type": type(e).__name__})

    def _build_compressed_turns(
        self, user_assistant: list
    ) -> list[CompressedTurn]:
        """将 user/assistant 对转换为 CompressedTurn 结构化记录

        工具名从 assistant 消息的 tool_calls 字段提取，不含结果内容。
        完整 tool result 已由 _node_cleanup_tools 持久化到 L3。
        """
        turns = []

        for i, msg in enumerate(user_assistant):
            if _msg_role(msg) == "user":
                # 找到紧随其后的 assistant 消息获取 tool_calls
                next_assistant = None
                if i + 1 < len(user_assistant) and _msg_role(user_assistant[i + 1]) == "assistant":
                    next_assistant = user_assistant[i + 1]

                tool_actions = []
                if next_assistant:
                    tool_calls = _msg_get(next_assistant, "tool_calls", [])
                    for tc in tool_calls:
                        tool_actions.append({
                            "name": _msg_get(tc, "name", "unknown"),
                            "arguments": str(_msg_get(tc, "arguments", {}))[:200],
                        })

                turn = CompressedTurn(
                    turn_index=i // 2,
                    user_intent=_msg_content(msg)[:200],
                    key_facts=[],
                    tool_actions=tool_actions,
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

    def _llm_summarize_turns(self, turns: list[CompressedTurn], errors: list, warnings: list) -> str:
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
            error_msg = f"LLM summarization failed: {e}"
            logger.error(f"[LLM Summarize] Failed after {elapsed:.2f}s: {e}")
            errors.append({"phase": "llm_summarization", "error": error_msg, "type": type(e).__name__})
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
            error_msg = f"LLM summarization failed: {e}"
            logger.error(f"[LLM Summarize] Failed after {elapsed:.2f}s: {e}")
            errors.append({"phase": "llm_summarization", "error": error_msg, "type": type(e).__name__})
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

