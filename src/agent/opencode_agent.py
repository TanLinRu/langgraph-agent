"""
OpenCode Agent - 通过 ACP 协议调度外部 opencode 的通用代码开发 Agent
"""
import logging
import os
from datetime import datetime
from typing import Optional, Callable, Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

from .config import AgentConfig, DEFAULT_CONFIG
from .state import AgentState, create_initial_state
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
from .skills import SKILLS_INDEX, should_load_skill
from .acp_client import get_acp_client

logger = logging.getLogger(__name__)


def _msg_get(msg, key, default=None):
    """Get attribute from message, supports dict and LangChain BaseMessage"""
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


OPENCODE_SYSTEM_PROMPT = """你是一个通用代码开发 Agent，通过 ACP 协议调度外部 opencode 来完成任务。

核心能力：
1. 理解用户需求，将其转化为具体的编码任务
2. 通过 ACP 协议调用外部 opencode 执行编码任务
3. 解析 opencode 返回的结果，进行必要的处理和总结

工作流程：
1. 接收用户需求，分析任务类型和复杂度
2. 构建适合 opencode 执行的 prompt
3. 通过 ACP 协议发送请求到 opencode
4. 接收响应，解析结果，返回给用户

注意事项：
- 复杂任务需要分解为多个子任务逐步完成
- 保持与用户的沟通，及时反馈进度
- 处理 opencode 执行过程中的错误和异常

""" + SKILLS_INDEX


class OpenCodeAgent:
    """通用代码开发 Agent，通过 ACP 协议调度外部 opencode"""

    def __init__(
        self,
        config: AgentConfig = DEFAULT_CONFIG,
        callback: Optional[Callable[[str], None]] = None,
        acp_timeout: int = 300,
    ):
        self.config = config
        self.callback = callback
        self.acp_timeout = acp_timeout

        self.acp_client = get_acp_client(timeout=acp_timeout)

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
        self.compressor = ContextCompressor(compression_config, llm=None)

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
            "total_calls": 0,
            "total_errors": 0,
            "total_latency": 0.0,
        }

    def _build_graph(self):
        """构建状态图"""
        workflow = StateGraph(AgentState)

        workflow.add_node("init", self._node_init)
        workflow.add_node("think", self._node_think)
        workflow.add_node("execute", self._node_execute)
        workflow.add_node("compress", self._node_compress)
        workflow.add_node("save", self._node_save)

        workflow.set_entry_point("init")
        workflow.add_edge("init", "think")
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
        """判断是否需要调用 opencode"""
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
        should_continue = task_status == "in_progress" and compression_count < 3
        logger.info(
            f"[Route] _should_continue: status={task_status}, "
            f"compressions={compression_count}, continue={should_continue}"
        )
        return "think" if should_continue else "end"

    def _node_init(self, state: AgentState) -> AgentState:
        """初始化节点"""
        thread_id = state.get("thread_id", "default")
        context = self.initializer.initialize(thread_id)

        system_content = OPENCODE_SYSTEM_PROMPT
        messages = [{"role": "system", "content": system_content}]

        if context.get("metadata", {}).get("resumed"):
            messages.extend(context["messages"])

        return {"messages": messages, "task_status": "in_progress"}

    def _node_think(self, state: AgentState) -> AgentState:
        """思考节点 - 分析任务并决定是否需要调用 opencode"""
        import time
        start_time = time.time()

        messages = state.get("messages", [])
        user_input = None

        for msg in reversed(messages):
            role = _msg_get(msg, "role")
            if role == "user":
                user_input = _msg_get(msg, "content")
                break

        if not user_input:
            return {
                "messages": [{"role": "assistant", "content": "请提供具体的编码任务"}],
            }

        skill = should_load_skill(user_input)
        skill_arg = skill["name"] if skill else None

        logger.info(f"[Think] User input: {user_input[:100]}...")
        logger.info(f"[Think] Skill: {skill_arg}")

        prompt = self._build_opencode_prompt(user_input, messages)

        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.acp_client.call(
                        prompt=prompt,
                        system_prompt=OPENCODE_SYSTEM_PROMPT,
                        skill=skill_arg,
                    )
                )
            finally:
                loop.close()

            elapsed = time.time() - start_time
            self._metrics["total_requests"] += 1
            self._metrics["total_latency"] += elapsed

            logger.info(f"[OpenCode Response] Elapsed: {elapsed:.2f}s")
            logger.info(f"[OpenCode Response] Length: {len(result)}")

            if result.startswith("Error:"):
                self._metrics["total_errors"] += 1

            return {"messages": [{"role": "assistant", "content": result}]}

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[Think Error] Elapsed: {elapsed:.2f}s, Error: {str(e)}")
            self._metrics["total_errors"] += 1

            return {
                "messages": [{
                    "role": "assistant",
                    "content": f"执行出错: {str(e)}"
                }],
            }

    def _build_opencode_prompt(self, user_input: str, messages: list) -> str:
        """构建发送给 opencode 的 prompt"""
        history = []

        for msg in messages:
            role = _msg_get(msg, "role")
            if role in ("system", "user", "assistant"):
                content = _msg_get(msg, "content")
                if content and role != "system":
                    history.append(f"{role}: {content}")

        history_text = "\n".join(history[-10:]) if history else ""

        prompt = f"""任务: {user_input}

"""
        if history_text:
            prompt += f"""对话历史:
{history_text}

"""

        prompt += """请执行上述编码任务，完成后返回结果摘要。"""

        return prompt

    def _node_execute(self, state: AgentState) -> AgentState:
        """执行节点 - opencode 已在 think 节点执行，此处处理响应"""
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else {}

        tool_calls = _msg_get(last_msg, "tool_calls", [])
        results = []

        for call in tool_calls:
            tool_name = _msg_get(call, "name")
            tool_input = _msg_get(call, "arguments", {})
            tool_call_id = _msg_get(call, "id")

            logger.info(f"[Tool Execute] Tool: {tool_name}")

            results.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": f"Tool {tool_name} executed"
            })

        if not results:
            results.append({
                "role": "tool",
                "tool_call_id": "opencode_result",
                "content": _msg_get(last_msg, "content", "")
            })

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

            return {
                "messages": compressed,
                "compression_count": state.get("compression_count", 0) + 1
            }

        logger.info(f"[Compress] No compression needed")
        return state

    def _node_save(self, state: AgentState) -> AgentState:
        """保存节点"""
        thread_id = state.get("thread_id", "default")
        messages = state.get("messages", [])
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

    def run(self, input_text: str, thread_id: str = "default") -> dict:
        """运行 Agent"""
        if not self._graph:
            self._build_graph()

        initial_state = create_initial_state(thread_id)
        initial_state["messages"] = [{"role": "user", "content": input_text}]

        config = {"configurable": {"thread_id": thread_id}}

        checkpoint = self.checkpointer.get(config)
        if checkpoint and checkpoint.get("channel_values", {}).get("messages"):
            existing = checkpoint["channel_values"]["messages"]
            initial_state["messages"] = existing + [{"role": "user", "content": input_text}]
            logger.info(f"[Resume] Loaded {len(existing)} prior messages for thread={thread_id}")

        try:
            result = self._graph.invoke(initial_state, config)
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"Agent 运行错误: {e}")
            return {"status": "error", "error": str(e)}

    def run_simple(self, input_text: str, skill: Optional[str] = None) -> str:
        """简单模式 - 直接调用 opencode 并返回结果"""
        import time
        start_time = time.time()

        logger.info(f"[Run Simple] Input: {input_text[:100]}...")

        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.acp_client.call(
                        prompt=input_text,
                        system_prompt=OPENCODE_SYSTEM_PROMPT,
                        skill=skill,
                    )
                )
            finally:
                loop.close()

            elapsed = time.time() - start_time
            self._metrics["total_requests"] += 1
            self._metrics["total_calls"] += 1
            self._metrics["total_latency"] += elapsed

            logger.info(f"[Run Simple] Elapsed: {elapsed:.2f}s, Length: {len(result)}")

            if result.startswith("Error:"):
                self._metrics["total_errors"] += 1

            return result

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[Run Simple Error] Elapsed: {elapsed:.2f}s, Error: {str(e)}")
            self._metrics["total_errors"] += 1
            return f"Error: {str(e)}"

    def stream(self, input_text: str, thread_id: str = "default"):
        """流式运行 Agent"""
        if not self._graph:
            self._build_graph()

        initial_state = create_initial_state(thread_id)
        initial_state["messages"] = [{"role": "user", "content": input_text}]

        config = {"configurable": {"thread_id": thread_id}}

        checkpoint = self.checkpointer.get(config)
        if checkpoint and checkpoint.get("channel_values", {}).get("messages"):
            existing = checkpoint["channel_values"]["messages"]
            initial_state["messages"] = existing + [{"role": "user", "content": input_text}]

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
        self.acp_client.shutdown()

    def get_metrics(self) -> dict:
        """获取 Agent 指标"""
        avg_latency = 0.0
        if self._metrics["total_requests"] > 0:
            avg_latency = self._metrics["total_latency"] / self._metrics["total_requests"]

        return {
            "total_requests": self._metrics["total_requests"],
            "total_calls": self._metrics["total_calls"],
            "total_errors": self._metrics["total_errors"],
            "total_latency_sec": round(self._metrics["total_latency"], 2),
            "avg_latency_sec": round(avg_latency, 2),
            "success_rate": round(
                (self._metrics["total_requests"] - self._metrics["total_errors"]) /
                max(self._metrics["total_requests"], 1) * 100, 1
            ),
        }

    def reset_metrics(self):
        """重置指标"""
        self._metrics = {
            "total_requests": 0,
            "total_calls": 0,
            "total_errors": 0,
            "total_latency": 0.0,
        }


def create_opencode_agent(
    memory_dir: str = "./memory",
    session_ttl_days: int = 7,
    acp_timeout: int = 300,
    **kwargs
) -> OpenCodeAgent:
    """创建 OpenCode Agent 工厂函数"""
    config = DEFAULT_CONFIG.model_copy()
    config.long_term.memory_dir = memory_dir
    config.long_term.session_ttl_days = session_ttl_days

    return OpenCodeAgent(config=config, acp_timeout=acp_timeout, **kwargs)


__all__ = ["OpenCodeAgent", "create_opencode_agent"]