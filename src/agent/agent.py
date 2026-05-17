from typing import Optional, Callable
from datetime import datetime
import logging
import os
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

from .config import AgentConfig, DEFAULT_CONFIG
from .state import AgentState, create_initial_state
from .sop_state import load_sop_state, load_latest_in_progress, update_sop_step
from .context import (
    LongTermManager,
    LongTermConfig,
    ContextCompressor,
    CompressionConfig,
    ContextInitializer,
    InitConfig,
    ArchiveManager,
    ArchiveConfig,
    RetrievalTrigger,
)
from .prompts import SYSTEM_PROMPT
from .skills import SKILLS_INDEX, get_skill_content, should_load_skill
from .tools import TOOLS, set_tool_result_manager
from .rate_limiter import get_rate_limiter, get_tool_breakers
from .graceful_degradation import get_degradation, get_health_checker
from .human_in_loop import get_hitl, ApprovalType
from .retry_handler import LLMRetryConfig, ToolRetryConfig
from .audit_logger import log_error
from .schemas import (
    ErrorEnvelope,
    ErrorType,
    ErrorLevel,
    StructuredAgentError,
    ERROR_CODES,
    AgentOutput,
    AgentInput,
    _get_or_create_trace_id,
)


logger = logging.getLogger(__name__)


def make_thread_id(
    tenant_id: str = "default",
    org_id: str = "default",
    user_id: str = "default",
    session_id: str = "default",
) -> str:
    """生成带 namespace 的 thread_id (设计参考: context_design.md 8.2)"""
    return f"{tenant_id}:{org_id}:{user_id}:{session_id}"


def _msg_get(msg, key, default=None):
    """Get attribute from message, supports dict and LangChain BaseMessage"""
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


def _deduplicate_messages(messages: list) -> list:
    """去重消息列表，避免重复的 system/user 消息"""
    if not messages:
        return []

    seen = set()
    result = []
    system_count = 0

    for msg in messages:
        role = _msg_get(msg, "role", "")
        content = _msg_get(msg, "content", "")

        if not content:
            content = str(msg)

        content_normalized = content.strip()[:100]

        if role == "system":
            if system_count > 0:
                continue
            system_count += 1
        else:
            key = f"{role}:{content_normalized}"
            if key in seen:
                continue
            seen.add(key)

        result.append(msg)

    return result

MODEL_COSTS = {
    "gpt-4": {"prompt": 0.03, "completion": 0.06},
    "gpt-4o": {"prompt": 0.005, "completion": 0.015},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
}


def get_langsmith_handler(project_name: str = "langgraph-agent"):
    """获取 LangSmith handler"""
    try:
        from langchain_core.callbacks import LangSmithCallbackHandler

        api_key = os.getenv("LANGSMITH_API_KEY")
        if not api_key:
            logger.warning("LANGSMITH_API_KEY 未设置，跳过 LangSmith 集成")
            return None

        handler = LangSmithCallbackHandler(
            project_name=project_name,
            api_key=api_key,
            metadata={
                "agent_version": "0.1.0",
                "environment": os.getenv("AGENT_ENV", "development")
            }
        )
        logger.info(f"LangSmith 已启用，项目: {project_name}")
        return handler
    except ImportError:
        logger.warning("langchain_core 无 LangSmithCallbackHandler")
        return None
    except Exception as e:
        logger.warning(f"LangSmith 初始化失败: {e}")
        return None


class Agent:
    """生产级 Agent"""

    def __init__(
        self,
        config: AgentConfig = DEFAULT_CONFIG,
        llm=None,
        callback: Optional[Callable[[str], None]] = None,
        enable_tracing: bool = True
    ):
        self.config = config
        self.llm = llm
        self.callback = callback

        self.langsmith_handler = None
        if enable_tracing:
            self.langsmith_handler = get_langsmith_handler()

        long_term_config = LongTermConfig(
            memory_dir=config.long_term.memory_dir,
            session_ttl_days=config.long_term.session_ttl_days,
            vector_enabled=config.long_term.vector_enabled,
            chroma_persist_dir=config.long_term.chroma_persist_dir,
        )
        self.long_term = LongTermManager(long_term_config)
        set_tool_result_manager(self.long_term)

        compression_config = CompressionConfig(
            trigger_threshold=config.short_term.trigger_threshold,
            keep_recent=config.short_term.keep_recent,
        )
        self.compressor = ContextCompressor(compression_config, llm)

        init_config = InitConfig(
            resume_on_startup=config.initialization.resume_on_startup,
            load_recent_sessions=config.initialization.load_recent_sessions,
            load_memory=config.initialization.load_memory,
        )
        self.initializer = ContextInitializer(self.long_term, init_config)
        self.retrieval_trigger = RetrievalTrigger(long_term_manager=self.long_term)

        archive_config = ArchiveConfig(
            enabled=True,
            notification_callback=callback,
        )
        self.archive_manager = ArchiveManager(archive_config, self.long_term)

        db_path = os.path.join(self.config.long_term.memory_dir, "checkpoints.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._checkpointer_conn = sqlite3.connect(db_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self._checkpointer_conn)
        self._graph = None

        self._metrics = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_latency": 0.0,
            "tool_calls": 0,
            "compressions": 0,
        }
        self._turn_metrics = []

    def _build_graph(self):
        """构建状态图"""
        workflow = StateGraph(AgentState)

        workflow.add_node("init", self._node_init)
        workflow.add_node("inject_profile", self._node_inject_profile)
        workflow.add_node("sop_resume", self._node_sop_resume)
        workflow.add_node("think", self._node_think)
        workflow.add_node("execute", self._node_execute)
        workflow.add_node("compress", self._node_compress)
        workflow.add_node("save", self._node_save)
        workflow.add_node("cleanup_tools", self._node_cleanup_tools)
        workflow.add_node("human_review", self._node_human_review)

        workflow.set_entry_point("init")

        workflow.add_edge("init", "inject_profile")
        workflow.add_edge("inject_profile", "sop_resume")
        workflow.add_edge("sop_resume", "think")
        workflow.add_conditional_edges(
            "think",
            self._should_execute,
            {"execute": "execute", "cleanup_tools": "cleanup_tools"}
        )
        workflow.add_conditional_edges(
            "execute",
            self._should_human_review,
            {"human_review": "human_review", "compress": "compress"}
        )
        workflow.add_conditional_edges(
            "human_review",
            self._should_proceed_after_review,
            {"compress": "compress", "end": END}
        )
        workflow.add_edge("compress", "save")
        workflow.add_edge("cleanup_tools", END)
        workflow.add_conditional_edges(
            "save",
            self._should_continue,
            {"think": "think", "end": END}
        )

        self._graph = workflow.compile(checkpointer=self.checkpointer)

    def _should_execute(self, state: AgentState) -> str:
        """判断是否需要工具调用"""
        messages = state.get("messages", [])
        if not messages:
            return "execute"
        last = messages[-1]
        has_tool_calls = bool(_msg_get(last, "tool_calls"))
        logger.info(f"[Route] _should_execute: tool_calls={has_tool_calls}")
        return "execute" if has_tool_calls else "cleanup_tools"

    def _should_human_review(self, state: AgentState) -> str:
        """判断是否需要人工审批 (高风险操作)"""
        messages = state.get("messages", [])
        if not messages:
            return "compress"
        last_msg = messages[-1]
        tool_calls = _msg_get(last_msg, "tool_calls", [])
        if not tool_calls:
            return "compress"

        hitl = get_hitl()
        critical_tools = {"code_execution", "write_operation", "resource_access", "file_write", "file_read", "bash", "execute_code"}
        for call in tool_calls:
            tool_name = _msg_get(call, "name", "").lower()
            if any(ct in tool_name for ct in critical_tools):
                logger.info(f"[Route] _should_human_review: critical tool={tool_name}, requiring review")
                return "human_review"
        return "compress"

    def _should_proceed_after_review(self, state: AgentState) -> str:
        """审批后判断走向"""
        review_status = state.get("human_review_status")
        if review_status == "approved":
            return "compress"
        logger.info(f"[Route] _should_proceed_after_review: status={review_status}, ending")
        return "end"

    def _should_continue(self, state: AgentState) -> str:
        """判断是否继续循环"""
        task_status = state.get("task_status")
        compression_count = state.get("compression_count", 0)
        step_count = state.get("step_count", 0)
        max_steps = self.config.short_term.max_steps
        max_iterations = self.config.short_term.max_iterations

        if step_count >= max_steps:
            logger.warning(f"[Route] max_steps={max_steps} reached, forcing END")
            return "end"
        if step_count >= max_iterations:
            logger.warning(f"[Route] max_iterations={max_iterations} reached, forcing END")
            return "end"
        if compression_count >= 5:
            logger.warning(f"[Route] max_compressions=5 reached, forcing END")
            return "end"

        token_usage = state.get("token_usage", {})
        budget_pct = token_usage.get("percentage", 0)
        if budget_pct >= 90:
            logger.warning(f"[Route] token_budget={budget_pct}% (>=90%), forcing END")
            return "end"
        if budget_pct >= 75:
            logger.warning(f"[Route] token_budget={budget_pct}% (>=75%), triggering compression warning")
            # Allow one more step but signal compression soon

        should_continue = task_status == "in_progress"
        logger.info(
            f"[Route] _should_continue: status={task_status}, "
            f"step_count={step_count}/{max_steps}, "
            f"compressions={compression_count}, "
            f"budget={budget_pct}%, "
            f"continue={should_continue}"
        )
        return "think" if should_continue else "end"

    def _node_init(self, state: AgentState) -> AgentState:
        """初始化节点 - 避免重复添加 system 消息"""
        thread_id = state.get("thread_id", "default")
        existing_messages = state.get("messages", [])

        has_system = any(
            _msg_get(m, "role") == "system" for m in existing_messages
        )

        if has_system:
            return {"task_status": "in_progress"}

        context = self.initializer.initialize(thread_id)
        system_content = f"{SYSTEM_PROMPT}\n\n---\n\n{SKILLS_INDEX}"
        messages = [{"role": "system", "content": system_content}]

        if context.get("metadata", {}).get("resumed"):
            messages.extend(context["messages"])

        return {"messages": messages, "task_status": "in_progress"}

    def _node_inject_profile(self, state: AgentState) -> AgentState:
        """加载用户画像并注入到 system message"""
        user_id = state.get("user_id", "default")
        tenant_id = state.get("tenant_id", "default")
        org_id = state.get("org_id", "default")

        profile = self.long_term.load_user_profile(user_id, tenant_id, org_id)
        if not profile:
            logger.debug(f"[Profile] No profile for user={user_id}, skipping")
            return {}

        profile_block = profile.to_system_block()
        if not profile_block:
            return {}

        messages = list(state.get("messages", []))
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "system":
                msg["content"] = msg["content"] + "\n\n" + profile_block
                logger.info(f"[Profile] Injected profile for user={user_id} into system message")
                break

        return {"messages": messages}

    def _node_sop_resume(self, state: AgentState) -> AgentState:
        """SOP Resume 节点 - 检查并恢复 SOP 状态"""
        sop_name = state.get("sop_name")
        if not sop_name:
            return state

        sop_state = load_sop_state(sop_name)
        if not sop_state:
            logger.info(f"[SOP Resume] No state found for: {sop_name}")
            return state

        current_step = sop_state.get("current_step", 1)
        step_info = sop_state.get("steps", {})
        answers = sop_state.get("answers", {})

        sop_context = f"""
## Current SOP: {sop_name}
Step: {current_step}/{len(step_info)}
Status: {sop_state.get('status')}

### Completed Steps:
"""
        for step, info in step_info.items():
            if info.get("status") == "completed":
                sop_context += f"- {step}: {info.get('timestamp')}\n"

        if answers:
            sop_context += "\n### Step Answers:\n"
            for step, ans in answers.items():
                sop_context += f"**{step}**: {ans}\n"

        logger.info(f"[SOP Resume] Loaded {sop_name} at step {current_step}")

        messages = state.get("messages", [])
        for i, msg in enumerate(messages):
            if isinstance(msg, dict) and msg.get("role") == "system":
                msg["content"] += sop_context
                break

        return {
            "messages": messages,
            "sop_step": current_step,
        }

    def _node_think(self, state: AgentState) -> AgentState:
        """思考节点 (带重试 + 熔断)"""
        messages = state.get("messages", [])

        import time, json
        start_time = time.time()

        logger.debug("")
        logger.debug(f"=== [_node_think] {len(messages)} messages ===")
        for i, msg in enumerate(messages):
            role = _msg_get(msg, "role", "unknown")
            content = _msg_get(msg, "content", "") or ""
            tool_calls = _msg_get(msg, "tool_calls", [])
            logger.debug(f"  [{i}] {role}: {content[:80]}...")
            if tool_calls:
                logger.debug(f"      tool_calls: {len(tool_calls)}")
                for tc in tool_calls:
                    tc_name = _msg_get(tc, "name", "?")
                    tc_args = _msg_get(tc, "arguments", {})
                    logger.debug(f"        - {tc_name}({json.dumps(tc_args, ensure_ascii=False)[:100]})")
        logger.debug(f"=== [_node_think] END INPUT ===")

        callbacks = [self.langsmith_handler] if self.langsmith_handler else []
        invoke_config = {"callbacks": callbacks} if callbacks else {}

        # --- Rate limiter check ---
        rate_limiter = get_rate_limiter()
        if not rate_limiter.check_limit():
            raise StructuredAgentError(
                error_code="LLM_RATE_LIMIT",
                error_type=ErrorType.RECOVERABLE,
                message="Rate limit exceeded, throttling LLM call",
                retryable=True,
                error_level=ErrorLevel.HIGH,
                trace_id=state.get("trace_id", ""),
            )

        # --- LLM circuit breaker check ---
        llm_breaker = get_tool_breakers().get_breaker("_llm")
        if not llm_breaker.can_execute():
            raise StructuredAgentError(
                error_code="CIRCUIT_BREAKER_OPEN",
                error_type=ErrorType.RECOVERABLE,
                message="LLM circuit breaker is open, skipping call",
                retryable=True,
                error_level=ErrorLevel.HIGH,
                trace_id=state.get("trace_id", ""),
            )

        # --- Retry loop ---
        max_retries = LLMRetryConfig.max_retries
        delay = LLMRetryConfig.initial_delay
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                logger.debug(f"[LLM] Calling invoke attempt {attempt + 1}/{max_retries + 1}...")
                response = self.llm.invoke(messages, **invoke_config)
                logger.debug(f"[LLM] Response received")

                llm_breaker.record_success()
                rate_limiter.record_request()

                elapsed = time.time() - start_time

                self._metrics["total_requests"] += 1
                self._metrics["total_latency"] += elapsed

                resp_content = _msg_get(response, "content", "") or ""
                resp_tool_calls = _msg_get(response, "tool_calls", []) or []

                logger.debug(f"=== [_node_think] LLM Response ===")
                logger.debug(f"  content: {resp_content[:200]}...")
                logger.debug(f"  tool_calls: {len(resp_tool_calls)}")
                for tc in resp_tool_calls:
                    tc_name = _msg_get(tc, "name", "?")
                    logger.debug(f"    - {tc_name}")
                logger.debug(f"=== [_node_think] END RESPONSE ===")

                prompt_tokens = 0
                completion_tokens = 0
                if hasattr(response, 'response_metadata'):
                    meta = response.response_metadata
                    prompt_tokens = meta.get('prompt_tokens', 0)
                    completion_tokens = meta.get('completion_tokens', 0)

                logger.info(f"[LLM] elapsed={elapsed:.2f}s, prompt_tok={prompt_tokens}, comp_tok={completion_tokens}")

                tokens = prompt_tokens + completion_tokens
                if tokens > 0:
                    self._metrics["total_tokens"] += tokens
                    estimated_cost = self._estimate_cost(prompt_tokens, completion_tokens)
                    self._metrics["total_cost"] += estimated_cost

                    self._turn_metrics.append({
                        "turn": len(self._turn_metrics) + 1,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": tokens,
                        "cost_usd": round(estimated_cost, 4),
                        "elapsed_sec": round(elapsed, 2),
                    })

                # === Token usage tracking ===
                current_usage = state.get("token_usage", {})
                msg_tokens = current_usage.get("messages", 0) + tokens
                token_update = {
                    "token_usage": {
                        "model": self.config.model,
                        "messages": msg_tokens,
                        "hot_zone": current_usage.get("hot_zone", 0),
                        "budget": current_usage.get("budget", 128000),
                    }
                }

                # === Retrieval trigger check ===
                retrieved_context = ""
                should_trig, reason = self.retrieval_trigger.should_retrieve(
                    {"messages": messages, "token_usage": token_update["token_usage"]},
                    session_summary=""
                )
                if should_trig:
                    ns = (
                        state.get("tenant_id", "default"),
                        state.get("org_id", "default"),
                        state.get("user_id", "default"),
                        "memory",
                    )
                    memories = self.long_term.search_similar(
                        messages[-1].get("content", "") if messages else "",
                        top_k=3,
                        namespace=ns,
                    )
                    if memories:
                        retrieved_context = "\n\n【相关记忆】\n" + "\n".join(f"- {m}" for m in memories)
                        logger.info(f"[Retrieval] Triggered by {reason}, injected {len(memories)} memories")

                result_msg = [response]
                if retrieved_context:
                    result_msg = [{
                        "role": "system",
                        "content": f"[相关记忆检索: {reason}]{retrieved_context}",
                        "name": "retrieved_memory",
                    }, response]

                return {
                    "messages": result_msg,
                    **token_update,
                    "step_count": state.get("step_count", 0) + 1,
                    "current_action": "think",
                }

            except StructuredAgentError:
                raise
            except Exception as e:
                last_exception = e
                elapsed = time.time() - start_time
                error_msg = str(e)
                logger.error(f"[LLM Error] Attempt {attempt + 1}, Elapsed: {elapsed:.2f}s, Error: {error_msg}")

                # Classify error using central ERROR_CODES
                if "timeout" in error_msg.lower() or "timed" in error_msg.lower():
                    error_code = "LLM_TIMEOUT"
                elif "rate limit" in error_msg.lower():
                    error_code = "LLM_RATE_LIMIT"
                elif "invalid" in error_msg.lower() or "response" in error_msg.lower():
                    error_code = "LLM_INVALID_RESPONSE"
                else:
                    error_code = "LLM_API_ERROR"

                code_info = ERROR_CODES.get(error_code, {})
                is_retryable = code_info.get("retryable", True)
                err_type = code_info.get("error_type", ErrorType.RECOVERABLE)

                state["last_error"] = {
                    "error_code": error_code,
                    "error_type": err_type.value if isinstance(err_type, ErrorType) else str(err_type),
                    "message": error_msg,
                    "retryable": is_retryable,
                }

                # Non-retryable → fail fast
                if not is_retryable or attempt >= max_retries:
                    llm_breaker.record_failure()
                    break

                time.sleep(delay)
                delay = min(delay * LLMRetryConfig.backoff_factor, LLMRetryConfig.max_delay)

        # All retries exhausted
        llm_breaker.record_failure()
        raise StructuredAgentError(
            error_code=error_code,
            error_type=err_type,
            message=f"LLM call failed after {max_retries + 1} attempts: {last_exception}",
            retryable=False,
            error_level=ErrorLevel.HIGH,
            context={"step": "think", "elapsed": time.time() - start_time, "model": self.config.model},
            trace_id=state.get("trace_id", ""),
        )

    def _node_execute(self, state: AgentState) -> AgentState:
        """执行节点 (带重试 + 工具熔断)"""
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else {}

        tool_calls = _msg_get(last_msg, "tool_calls", [])
        results = []

        self._idempotent_cache: dict = getattr(self, "_idempotent_cache", {})

        logger.info(f"[Tool Execute] Total tools to execute: {len(tool_calls)}")

        tool_breakers = get_tool_breakers()

        for call in tool_calls:
            tool_name = _msg_get(call, "name")
            tool_input = _msg_get(call, "arguments", {})
            tool_call_id = _msg_get(call, "id")

            logger.info(f"[Tool Execute] Tool: {tool_name}")
            logger.info(f"[Tool Execute] Tool ID: {tool_call_id}")
            logger.info(f"[Tool Execute] Arguments: {tool_input}")

            import uuid
            idempotency_key = str(uuid.uuid4())

            if tool_call_id in self._idempotent_cache:
                cached = self._idempotent_cache[tool_call_id]
                results.append(cached)
                logger.info(f"[Tool Execute] Using cached result for {tool_call_id}")
                continue

            # Check SQLite for cross-session idempotency
            thread_id_val = state.get("thread_id", "default")
            try:
                persisted = self.long_term.load_tool_result(thread_id_val, tool_call_id)
                if persisted:
                    self._idempotent_cache[tool_call_id] = persisted
                    results.append(persisted)
                    logger.info(f"[Tool Execute] Using persisted result for {tool_call_id}")
                    continue
            except Exception:
                pass  # DB lookup failure is non-fatal

            # Tool circuit breaker check
            if not tool_breakers.can_execute(tool_name):
                results.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": f"错误: 工具 {tool_name} 熔断器开启，跳过执行",
                    "status": "skipped",
                })
                continue

            for t in TOOLS:
                if t.name == tool_name:
                    import time
                    start_time = time.time()

                    tool_input["idempotency_key"] = idempotency_key

                    # Retry loop per tool
                    max_retries = ToolRetryConfig.max_retries
                    retry_delay = ToolRetryConfig.initial_delay
                    last_error = None

                    for attempt in range(max_retries + 1):
                        try:
                            result = t.invoke(tool_input)
                            elapsed = time.time() - start_time

                            self._metrics["tool_calls"] += 1
                            tool_breakers.record_success(tool_name)

                            logger.info(f"[Tool Result] Tool: {tool_name}, Elapsed: {elapsed:.2f}s")

                            result_dict = result if isinstance(result, dict) else {"content": str(result), "status": "success"}
                            tool_status = result_dict.get("status", "success")
                            tool_content = result_dict.get("content", str(result))
                            tool_metadata = result_dict.get("metadata", {})

                            result_msg = {
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": tool_content,
                                "status": tool_status,
                            }
                            if tool_metadata:
                                result_msg["metadata"] = tool_metadata

                            if len(self._idempotent_cache) >= 1000:
                                oldest = next(iter(self._idempotent_cache))
                                del self._idempotent_cache[oldest]
                            self._idempotent_cache[tool_call_id] = result_msg

                            results.append(result_msg)
                            break

                        except Exception as e:
                            last_error = e
                            elapsed = time.time() - start_time
                            error_msg = str(e)
                            logger.error(f"[Tool Error] Tool: {tool_name}, Attempt {attempt + 1}, Elapsed: {elapsed:.2f}s, Error: {error_msg}")

                            self._metrics["tool_calls"] += 1

                            if "not found" in error_msg.lower():
                                error_code = "TOOL_NOT_FOUND"
                            elif "argument" in error_msg.lower() or "invalid" in error_msg.lower():
                                error_code = "TOOL_ARGUMENT_ERROR"
                            elif "timeout" in error_msg.lower():
                                error_code = "TOOL_EXEC_TIMEOUT"
                            else:
                                error_code = "TOOL_EXEC_ERROR"

                            code_info = ERROR_CODES.get(error_code, {})
                            is_retryable = code_info.get("retryable", True)

                            state["last_error"] = {
                                "error_code": error_code,
                                "error_type": code_info.get("error_type", ErrorType.RECOVERABLE).value if isinstance(code_info.get("error_type", ErrorType.RECOVERABLE), ErrorType) else str(code_info.get("error_type", ErrorType.RECOVERABLE)),
                                "message": error_msg,
                                "retryable": is_retryable,
                            }

                            if not is_retryable or attempt >= max_retries:
                                tool_breakers.record_failure(tool_name)
                                results.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": f"错误: {str(e)}",
                                    "status": "failed",
                                })
                                break

                            time.sleep(retry_delay)
                            retry_delay = min(retry_delay * ToolRetryConfig.backoff_factor, ToolRetryConfig.max_delay)

                    else:
                        # All retries exhausted (no break)
                        tool_breakers.record_failure(tool_name)
                        results.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": f"错误: {last_error}",
                            "status": "failed",
                        })

                    break  # outer for t in TOOLS

        return {"messages": results}

    def _node_human_review(self, state: AgentState) -> AgentState:
        """人机审批节点 - 等待高风险操作审批"""
        messages = state.get("messages", [])
        if not messages:
            return {"human_review_status": "skipped"}

        last_msg = messages[-1]
        tool_calls = _msg_get(last_msg, "tool_calls", [])
        if not tool_calls:
            return {"human_review_status": "skipped"}

        hitl = get_hitl()
        for call in tool_calls:
            tool_name = _msg_get(call, "name", "unknown")
            tool_input = _msg_get(call, "arguments", {})

            approval_type = ApprovalType.CODE_EXECUTION
            if "write" in tool_name.lower() or "file" in tool_name.lower():
                approval_type = ApprovalType.WRITE_OPERATION
            elif "resource" in tool_name.lower():
                approval_type = ApprovalType.RESOURCE_ACCESS

            request_id = f"hitl-{state.get('thread_id', 'default')}-{tool_name}"
            description = f"Tool: {tool_name}, Args: {str(tool_input)[:200]}"

            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    future = asyncio.ensure_future(
                        hitl.request_approval(
                            request_id=request_id,
                            approval_type=approval_type,
                            description=description,
                            timeout=300.0,
                        )
                    )
                    approved = future.result(timeout=310)
                else:
                    approved = loop.run_until_complete(
                        hitl.request_approval(
                            request_id=request_id,
                            approval_type=approval_type,
                            description=description,
                            timeout=300.0,
                        )
                    )
            except Exception as e:
                logger.warning(f"[HITL] Approval request failed: {e}, auto-rejecting")
                approved = False

            status = "approved" if approved else "rejected"
            logger.info(f"[HITL] Decision: {status} for tool={tool_name}")
            return {"human_review_status": status}

        return {"human_review_status": "skipped"}

    def _node_compress(self, state: AgentState) -> AgentState:
        """压缩节点"""
        messages = state.get("messages", [])
        msg_count = len(messages)

        should_compress = self.compressor.should_compress(messages)
        logger.info(f"[Compress Check] Should compress: {should_compress}, Messages: {msg_count}")

        if should_compress:
            result = self.compressor.compress(messages)
            new_count = len(result.compressed_messages)
            logger.info(f"[Compress] Compressed: {msg_count} -> {new_count} messages")

            self._metrics["compressions"] += 1

            return {
                "messages": result.compressed_messages,
                "compression_count": state.get("compression_count", 0) + 1
            }

        logger.info(f"[Compress] No compression needed")
        return state

    def _node_save(self, state: AgentState) -> AgentState:
        """保存节点 - 先去重再保存"""
        thread_id = state.get("thread_id", "default")
        messages = state.get("messages", [])
        messages = _deduplicate_messages(messages)
        task_status = state.get("task_status")

        logger.info(f"[Save] Thread: {thread_id}, Messages: {len(messages)}, Status: {task_status}")

        self.long_term.save_session(
            thread_id=thread_id,
            messages=messages,
            metadata={
                "task_status": task_status,
                "compression_count": state.get("compression_count", 0)
            }
        )

        logger.info(f"[Save] Session saved successfully")

        return {"updated_at": datetime.now().isoformat()}

    def _node_cleanup_tools(self, state: AgentState) -> AgentState:
        """清理已消费的 tool results: 持久化到 L3，从消息列表移除"""
        messages = state.get("messages", [])
        thread_id = state.get("thread_id", "default")

        tool_msgs = [m for m in messages if _msg_get(m, "role") == "tool"]
        if not tool_msgs:
            # 无 tool 消息时保持 hot_tool_results 但不返回新消息
            hot_results = state.get("hot_tool_results", [])
            return {"hot_tool_results": hot_results}

        # 保留最近 keep_recent 条在热区
        keep_count = self.config.short_term.keep_recent
        to_persist = tool_msgs[:-keep_count] if len(tool_msgs) > keep_count else []
        to_keep = tool_msgs if len(tool_msgs) <= keep_count else tool_msgs[-keep_count:]

        # 从 L3 已有的 tool_call_id 中识别哪些需要持久化
        persisted_ids = set()
        if to_persist:
            results = []
            for m in to_persist:
                tc_id = _msg_get(m, "tool_call_id", "")
                tool_name = _msg_get(m, "name", "unknown")
                content = _msg_get(m, "content", "")
                status = _msg_get(m, "status", "success")
                if tc_id:
                    results.append({
                        "tool_call_id": tc_id,
                        "tool_name": tool_name,
                        "content": content,
                        "status": status,
                        "metadata": str(_msg_get(m, "metadata", {})),
                    })
                    persisted_ids.add(tc_id)
            if results:
                self.long_term.save_tool_results(thread_id, results)
                logger.info(f"[CleanupTools] Persisted {len(results)} tool results to L3")

        # 更新消息列表（只保留热区内的 tool 结果）
        non_tool = [m for m in messages if _msg_get(m, "role") != "tool"]
        new_messages = non_tool + to_keep

        # 构建 hot_tool_results（含完整原文）
        existing_hot = {h.get("tool_call_id") for h in state.get("hot_tool_results", [])}
        hot_results = list(state.get("hot_tool_results", []))
        for m in to_keep:
            tc_id = _msg_get(m, "tool_call_id", "")
            if tc_id and tc_id not in existing_hot:
                hot_results.append({
                    "tool_call_id": tc_id,
                    "tool_name": _msg_get(m, "name", "unknown"),
                    "summary": _msg_get(m, "content", "")[:200],
                    "status": _msg_get(m, "status", "success"),
                    "timestamp": datetime.now().isoformat(),
                    "access_count": 0,
                    "full_content": _msg_get(m, "content", ""),
                    "is_hot": True,
                })
                existing_hot.add(tc_id)

        logger.info(
            f"[CleanupTools] Kept {len(to_keep)} hot, "
            f"persisted {len(to_persist)}, "
            f"messages: {len(messages)} -> {len(new_messages)}"
        )

        return {
            "messages": new_messages,
            "hot_tool_results": hot_results,
        }

    def _build_error_output(self, status: str, trace_id: str, trace_log: list, error: dict) -> AgentOutput:
        ended_at = __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ")
        return AgentOutput(
            status=status,
            result=None,
            trace_log=trace_log,
            token_usage={},
            cost_usd=0,
            error=error,
            trace_id=trace_id,
            steps_executed=0,
            iterations=0,
            ended_at=ended_at,
            task_status=None,
            compression_count=0,
        )

    def run(self, input_text: str = None, thread_id: str = "default", sop_name: str = None, input_obj: dict = None) -> dict:
        """运行 Agent

        支持两种调用方式:
            1. run("你好")                    # 向后兼容
            2. run(input_obj={"task": "...", ...})  # 结构化
        """
        import time
        start_time = time.time()
        trace_id = _get_or_create_trace_id()
        trace_log = []

        if not self._graph:
            self._build_graph()

        if input_obj is not None:
            task = input_obj.get("task", "")
            config_override = input_obj.get("config", {})
            session_id = input_obj.get("session_id", thread_id)
        else:
            task = input_text or ""
            config_override = {}
            session_id = thread_id

        initial_state = create_initial_state(session_id)
        initial_state["trace_id"] = trace_id
        initial_state["user_id"] = (
            input_obj.get("user_id", "default")
            if input_obj else os.getenv("AGENT_USER_ID", "default")
        )
        new_user_msg = {"role": "user", "content": task}
        initial_state["messages"] = [new_user_msg]
        if sop_name:
            initial_state["sop_name"] = sop_name
            logger.info(f"[Run] SOP resume enabled: {sop_name}")

        namespaced_id = make_thread_id(
            tenant_id=os.getenv("AGENT_TENANT_ID", "default"),
            org_id=os.getenv("AGENT_ORG_ID", "default"),
            user_id=os.getenv("AGENT_USER_ID", "default"),
            session_id=session_id,
        )
        config = {"configurable": {"thread_id": namespaced_id}}

        checkpoint = self.checkpointer.get(config)
        if checkpoint and checkpoint.get("channel_values", {}).get("messages"):
            existing = checkpoint["channel_values"]["messages"]
            existing = _deduplicate_messages(existing)
            initial_state["messages"] = existing + [new_user_msg]
            trace_log.append({
                "step": 0,
                "action": "resume",
                "observation": f"恢复 {len(existing)} 条消息",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            logger.info(f"[Resume] Loaded {len(existing)} prior messages for thread={session_id}")

        try:
            result = self._graph.invoke(initial_state, config)
            ended_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            metrics = self.get_metrics()
            return AgentOutput(
                status="success",
                result={"messages": result.get("messages", [])},
                trace_log=trace_log,
                token_usage=metrics,
                cost_usd=metrics.get("total_cost_usd", 0),
                error=None,
                trace_id=trace_id,
                steps_executed=result.get("step_count", 0),
                iterations=result.get("step_count", 0),
                ended_at=ended_at,
                task_status=result.get("task_status"),
                compression_count=result.get("compression_count", 0),
            )
        except StructuredAgentError as e:
            env = e.to_envelope()
            env_dict = env.to_dict()
            log_error(env_dict, trace_id=trace_id, thread_id=session_id, user_id=initial_state.get("user_id"))
            return self._build_error_output("failed", trace_id, trace_log, env_dict)
        except Exception as e:
            logger.error(f"Agent 运行错误: {e}")
            env = ErrorEnvelope.from_exception(e, error_code="INTERNAL_ERROR", trace_id=trace_id)
            env_dict = env.to_dict()
            log_error(env_dict, trace_id=trace_id, thread_id=session_id, user_id=initial_state.get("user_id"))
            return self._build_error_output("failed", trace_id, trace_log, env_dict)

    def stream(self, input_text: str, thread_id: str = "default", sop_name: str = None):
        """流式运行 Agent"""
        if not self._graph:
            self._build_graph()

        initial_state = create_initial_state(thread_id)
        new_user_msg = {"role": "user", "content": input_text}
        initial_state["messages"] = [new_user_msg]
        if sop_name:
            initial_state["sop_name"] = sop_name

        namespaced_id = make_thread_id(
            tenant_id=os.getenv("AGENT_TENANT_ID", "default"),
            org_id=os.getenv("AGENT_ORG_ID", "default"),
            user_id=os.getenv("AGENT_USER_ID", "default"),
            session_id=thread_id,
        )
        config = {"configurable": {"thread_id": namespaced_id}}

        checkpoint = self.checkpointer.get(config)
        if checkpoint and checkpoint.get("channel_values", {}).get("messages"):
            existing = checkpoint["channel_values"]["messages"]
            existing = _deduplicate_messages(existing)
            initial_state["messages"] = existing + [new_user_msg]

        for event in self._graph.stream(initial_state, config, stream_mode="values"):
            yield event

    def pause(self, thread_id: str = "default") -> dict:
        """暂停 Agent 执行"""
        namespaced_id = make_thread_id(session_id=thread_id)
        config = {"configurable": {"thread_id": namespaced_id}}
        checkpoint = self.checkpointer.get(config)
        if checkpoint:
            channel_values = checkpoint.get("channel_values", {})
            channel_values["task_status"] = "paused"
            self.checkpointer.put(config, channel_values)
            return {"status": "success", "action": "paused", "thread_id": thread_id}
        return {"status": "error", "message": "无可暂停的会话"}

    def abort(self, thread_id: str = "default") -> dict:
        """终止 Agent 执行"""
        namespaced_id = make_thread_id(session_id=thread_id)
        config = {"configurable": {"thread_id": namespaced_id}}
        checkpoint = self.checkpointer.get(config)
        if checkpoint:
            channel_values = checkpoint.get("channel_values", {})
            channel_values["task_status"] = "aborted"
            self.checkpointer.put(config, channel_values)
            return {"status": "success", "action": "aborted", "thread_id": thread_id}
        return {"status": "error", "message": "无可终止的会话"}

    def resume(self, thread_id: str = "default") -> dict:
        """恢复暂停的 Agent"""
        namespaced_id = make_thread_id(session_id=thread_id)
        config = {"configurable": {"thread_id": namespaced_id}}
        checkpoint = self.checkpointer.get(config)
        if checkpoint:
            channel_values = checkpoint.get("channel_values", {})
            status = channel_values.get("task_status", "")
            if status == "paused":
                channel_values["task_status"] = "in_progress"
                self.checkpointer.put(config, channel_values)
                return {"status": "success", "action": "resumed", "thread_id": thread_id}
            return {"status": "error", "message": f"当前状态不可恢复: {status}"}
        return {"status": "error", "message": "无可恢复的会话"}

    def archive(self) -> str:
        """执行归档"""
        return self.archive_manager.run_archive()

    def close(self):
        """关闭资源"""
        self.long_term.close()
        if hasattr(self, '_checkpointer_conn') and self._checkpointer_conn:
            self._checkpointer_conn.close()

    def get_metrics(self) -> dict:
        """获取 Agent 指标"""
        avg_latency = 0.0
        if self._metrics["total_requests"] > 0:
            avg_latency = self._metrics["total_latency"] / self._metrics["total_requests"]

        return {
            "total_requests": self._metrics["total_requests"],
            "total_tokens": self._metrics["total_tokens"],
            "total_cost_usd": round(self._metrics["total_cost"], 4),
            "total_latency_sec": round(self._metrics["total_latency"], 2),
            "avg_latency_sec": round(avg_latency, 2),
            "tool_calls": self._metrics["tool_calls"],
            "compressions": self._metrics["compressions"],
            "turns": self._turn_metrics,
        }

    def get_turn_metrics(self) -> list:
        """获取每次交互的详细指标"""
        return self._turn_metrics

    def reset_metrics(self):
        """重置指标"""
        self._metrics = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_latency": 0.0,
            "tool_calls": 0,
            "compressions": 0,
        }
        self._turn_metrics = []

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """估算 API 成本"""
        model_name = self.config.model.replace("openai:", "")
        pricing = MODEL_COSTS.get(model_name, MODEL_COSTS["gpt-4"])
        return (prompt_tokens / 1000 * pricing["prompt"]) + (completion_tokens / 1000 * pricing["completion"])


def create_agent(
    model: str = "openai:gpt-4",
    api_key: str = "",
    base_url: str = "https://api.openai.com/v1",
    **kwargs
) -> Agent:
    """创建 Agent 工厂函数"""
    from langchain_openai import ChatOpenAI

    config = DEFAULT_CONFIG.model_copy()
    config.model = model
    config.api_key = api_key
    config.base_url = base_url

    llm = ChatOpenAI(
        model=model.replace("openai:", ""),
        api_key=api_key,
        base_url=base_url,
        temperature=0
    )

    return Agent(config=config, llm=llm, **kwargs)


__all__ = ["Agent", "create_agent"]
