from typing import Optional, Callable
from datetime import datetime
import logging
import os

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
)
from .prompts import SYSTEM_PROMPT
from .skills import SKILLS_INDEX, get_skill_content, should_load_skill
from .tools import TOOLS

logger = logging.getLogger(__name__)


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
        workflow.add_node("sop_resume", self._node_sop_resume)
        workflow.add_node("think", self._node_think)
        workflow.add_node("execute", self._node_execute)
        workflow.add_node("compress", self._node_compress)
        workflow.add_node("save", self._node_save)

        workflow.set_entry_point("init")

        workflow.add_edge("init", "sop_resume")
        workflow.add_edge("sop_resume", "think")
        workflow.add_edge("execute", "compress")
        workflow.add_conditional_edges(
            "think",
            self._should_execute,
            {"execute": "execute", "end": END}
        )
        workflow.add_edge("compress", "save")
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
        return "execute" if has_tool_calls else "end"

    def _should_continue(self, state: AgentState) -> str:
        """判断是否继续循环"""
        task_status = state.get("task_status")
        compression_count = state.get("compression_count", 0)
        should_continue = task_status == "in_progress" and compression_count < 5
        logger.info(
            f"[Route] _should_continue: status={task_status}, "
            f"compressions={compression_count}, continue={should_continue}"
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
        """思考节点"""
        messages = state.get("messages", [])

        import time
        start_time = time.time()

        logger.debug(f"[LLM] Model={self.config.model}, Messages={len(messages)}")

        callbacks = [self.langsmith_handler] if self.langsmith_handler else []
        invoke_config = {"callbacks": callbacks} if callbacks else {}

        try:
            response = self.llm.invoke(messages, **invoke_config)

            elapsed = time.time() - start_time

            self._metrics["total_requests"] += 1
            self._metrics["total_latency"] += elapsed

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

            return {"messages": [response]}

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[LLM Error] Elapsed: {elapsed:.2f}s, Error: {str(e)}")
            raise

    def _node_execute(self, state: AgentState) -> AgentState:
        """执行节点"""
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else {}

        tool_calls = _msg_get(last_msg, "tool_calls", [])
        results = []

        logger.info(f"[Tool Execute] Total tools to execute: {len(tool_calls)}")

        for call in tool_calls:
            tool_name = _msg_get(call, "name")
            tool_input = _msg_get(call, "arguments", {})
            tool_call_id = _msg_get(call, "id")

            logger.info(f"[Tool Execute] Tool: {tool_name}")
            logger.info(f"[Tool Execute] Tool ID: {tool_call_id}")
            logger.info(f"[Tool Execute] Arguments: {tool_input}")

            for t in TOOLS:
                if t.name == tool_name:
                    import time
                    start_time = time.time()

                    try:
                        result = t.invoke(tool_input)
                        elapsed = time.time() - start_time

                        self._metrics["tool_calls"] += 1

                        logger.info(f"[Tool Result] Tool: {tool_name}, Elapsed: {elapsed:.2f}s")
                        logger.info(f"[Tool Result] Length: {len(str(result))}")

                        results.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": str(result)
                        })
                    except Exception as e:
                        elapsed = time.time() - start_time
                        logger.error(f"[Tool Error] Tool: {tool_name}, Elapsed: {elapsed:.2f}s, Error: {str(e)}")

                        self._metrics["tool_calls"] += 1

                        results.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": f"错误: {str(e)}"
                        })
                    break

        return {"messages": results}

    def _node_compress(self, state: AgentState) -> AgentState:
        """压缩节点"""
        messages = state.get("messages", [])
        msg_count = len(messages)

        should_compress = self.compressor.should_compress(messages)
        logger.info(f"[Compress Check] Should compress: {should_compress}, Messages: {msg_count}")

        if should_compress:
            compressed = self.compressor.compress(messages)
            new_count = len(compressed)
            logger.info(f"[Compress] Compressed: {msg_count} -> {new_count} messages")

            self._metrics["compressions"] += 1

            return {
                "messages": compressed,
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

    def run(self, input_text: str, thread_id: str = "default", sop_name: str = None) -> dict:
        """运行 Agent"""
        if not self._graph:
            self._build_graph()

        initial_state = create_initial_state(thread_id)
        new_user_msg = {"role": "user", "content": input_text}
        initial_state["messages"] = [new_user_msg]
        if sop_name:
            initial_state["sop_name"] = sop_name
            logger.info(f"[Run] SOP resume enabled: {sop_name}")

        config = {"configurable": {"thread_id": thread_id}}

        checkpoint = self.checkpointer.get(config)
        if checkpoint and checkpoint.get("channel_values", {}).get("messages"):
            existing = checkpoint["channel_values"]["messages"]
            existing = _deduplicate_messages(existing)
            initial_state["messages"] = existing + [new_user_msg]
            logger.info(f"[Resume] Loaded {len(existing)} prior messages for thread={thread_id}")

        try:
            result = self._graph.invoke(initial_state, config)
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"Agent 运行错误: {e}")
            return {"status": "error", "error": str(e)}

    def stream(self, input_text: str, thread_id: str = "default", sop_name: str = None):
        """流式运行 Agent"""
        if not self._graph:
            self._build_graph()

        initial_state = create_initial_state(thread_id)
        new_user_msg = {"role": "user", "content": input_text}
        initial_state["messages"] = [new_user_msg]
        if sop_name:
            initial_state["sop_name"] = sop_name

        config = {"configurable": {"thread_id": thread_id}}

        checkpoint = self.checkpointer.get(config)
        if checkpoint and checkpoint.get("channel_values", {}).get("messages"):
            existing = checkpoint["channel_values"]["messages"]
            existing = _deduplicate_messages(existing)
            initial_state["messages"] = existing + [new_user_msg]

        for event in self._graph.stream(initial_state, config, stream_mode="values"):
            yield event

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
