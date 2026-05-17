"""
Supervisor Manager

使用 langgraph-supervisor 构建和管理多代理 supervisor 图。
替代原有的 MultiAgentOrchestrator，提供 LLM 驱动的智能路由。
"""
import uuid
import time
import logging
import os
from datetime import datetime
from typing import Optional, AsyncGenerator, Union
from dataclasses import dataclass, field

from langgraph_supervisor import create_supervisor

from .sub_agent_factory import build_sub_agent, _sanitize_agent_name
from .event_bus import get_event_bus, ExecutionEvent
from .event_callback import EventBusCallbackHandler
from .schemas import ErrorEnvelope, ErrorType
from .audit_logger import log_error

logger = logging.getLogger(__name__)

# 内存执行状态存储
_supervisor_executions: dict = {}


@dataclass
class SupervisorExecutionState:
    """Supervisor 执行状态"""
    execution_id: str
    graph_id: str
    input_text: str
    status: str = "pending"
    output: Optional[str] = None
    messages: list = field(default_factory=list)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    total_llm_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    elapsed_ms: int = 0
    error: Optional[Union[str, dict]] = None
    agent_names: list = field(default_factory=list)
    interrupted: bool = False
    can_resume: bool = False


class SupervisorManager:
    """管理 supervisor 图的构建、执行和状态。"""

    def __init__(self, registry, llm, available_tools: list):
        self.registry = registry
        self.llm = llm
        self.available_tools = available_tools
        self._agent_cache: dict = {}  # agent_id -> create_react_agent instance

    def _build_sub_agents(self, graph_def: dict) -> list:
        """从图定义构建所有 sub-agent 实例。"""
        nodes = graph_def.get("nodes", [])
        agents = []

        for node in nodes:
            if node.get("type") != "agent":
                continue

            agent_id = node.get("agent_id") or node.get("data", {}).get("agent_id")
            if not agent_id:
                logger.warning(f"[Supervisor] Node missing agent_id: {node}")
                continue

            agent_def = self.registry.get_agent(agent_id)
            if not agent_def:
                logger.warning(f"[Supervisor] Agent not found: {agent_id}")
                continue

            # 使用缓存避免重复构建
            if agent_id not in self._agent_cache:
                self._agent_cache[agent_id] = build_sub_agent(
                    agent_def, self.llm, self.available_tools
                )

            agents.append(self._agent_cache[agent_id])

        return agents

    def _build_supervisor_prompt(self, graph_def: dict, agents: list) -> str:
        """根据图定义和 agent 信息构建 supervisor 的系统提示。"""
        lines = ["你是一个多代理调度器，负责将用户任务分配给最合适的专业代理。\n"]
        lines.append("可用代理：\n")

        for node in graph_def.get("nodes", []):
            if node.get("type") != "agent":
                continue
            agent_id = node.get("agent_id") or node.get("data", {}).get("agent_id")
            agent_def = self.registry.get_agent(agent_id)
            if not agent_def:
                continue

            name = _sanitize_agent_name(agent_id)
            desc = agent_def.get("description", "")
            skill_source = agent_def.get("skill_source")

            # 从 skills 注册表获取 use_when 关键词
            use_when = []
            if skill_source:
                from .skills import get_skill
                skill = get_skill(skill_source)
                if skill:
                    use_when = skill.get("use_when", [])

            line = f"- **{name}**: {desc}"
            if use_when:
                line += f"\n  适用场景: {', '.join(use_when)}"
            lines.append(line)

        # 添加图边的路由提示
        edges = graph_def.get("edges", [])
        if edges:
            lines.append("\n执行顺序提示：")
            for edge in edges:
                src = edge.get("source", "")
                tgt = edge.get("target", "")
                src_def = self.registry.get_agent(
                    self._get_agent_id_from_node(graph_def, src)
                )
                tgt_def = self.registry.get_agent(
                    self._get_agent_id_from_node(graph_def, tgt)
                )
                if src_def and tgt_def:
                    src_name = _sanitize_agent_name(src_def["id"])
                    tgt_name = _sanitize_agent_name(tgt_def["id"])
                    lines.append(f"- 先调用 {src_name}，再将结果传给 {tgt_name}")

        lines.append("\n根据用户请求选择最合适的代理。如果任务需要多个代理协作，按顺序处理。")
        return "\n".join(lines)

    def _get_agent_id_from_node(self, graph_def: dict, node_id: str) -> str:
        """从节点 ID 获取 agent_id。"""
        for node in graph_def.get("nodes", []):
            if node.get("id") == node_id:
                return node.get("agent_id") or node.get("data", {}).get("agent_id", "")
        return ""

    def build_supervisor(self, graph_id: str):
        """构建 supervisor 图并编译。

        Returns:
            CompiledStateGraph 或 None
        """
        graph_def = self.registry.get_graph(graph_id)
        if not graph_def:
            logger.error(f"[Supervisor] Graph not found: {graph_id}")
            return None

        agents = self._build_sub_agents(graph_def)
        if not agents:
            logger.error(f"[Supervisor] No agents found in graph: {graph_id}")
            return None

        prompt = self._build_supervisor_prompt(graph_def, agents)

        # 检查 supervisor_config
        config = graph_def.get("config", {})
        supervisor_config = config.get("supervisor_config", {})
        custom_prompt = supervisor_config.get("supervisor_prompt")
        if custom_prompt:
            prompt = custom_prompt

        max_iterations = supervisor_config.get("max_iterations", 10)

        logger.info(
            f"[Supervisor] Building supervisor for graph={graph_id}, "
            f"agents={[a.name for a in agents]}, max_iterations={max_iterations}"
        )

        workflow = create_supervisor(
            agents,
            model=self.llm,
            prompt=prompt,
        )

        return workflow.compile()

    def generate_plan(self, graph_id: str, input_text: str) -> Optional[dict]:
        """生成执行计划（保持与旧 API 兼容的格式）。"""
        graph_def = self.registry.get_graph(graph_id)
        if not graph_def:
            return None

        nodes = graph_def.get("nodes", [])
        steps = []
        step_id = 1

        for node in nodes:
            if node.get("type") != "agent":
                continue

            agent_id = node.get("agent_id") or node.get("data", {}).get("agent_id")
            agent_def = self.registry.get_agent(agent_id) if agent_id else None

            steps.append({
                "step_id": step_id,
                "agent_id": agent_id or "unknown",
                "agent_name": agent_def.get("name", "未知") if agent_def else "未知",
                "agent_description": agent_def.get("description", "") if agent_def else "",
                "expected_tools": agent_def.get("tools", []) if agent_def else [],
                "depends_on": [],  # supervisor 自动处理依赖
                "is_parallel": False,
                "estimated_calls": 1,
                "estimated_tokens": 1500,
            })
            step_id += 1

        total_llm_calls = len(steps)

        return {
            "graph_id": graph_id,
            "input_summary": input_text[:100],
            "total_llm_calls": total_llm_calls,
            "estimated_cost_usd": round(total_llm_calls * 0.02, 4),
            "estimated_duration_sec": total_llm_calls * 5,
            "steps": steps,
            "parallel_opportunities": [],
            "optimization_suggestions": [],
        }

    async def run(self, graph_id: str, input_text: str, thread_id: str = "default") -> dict:
        """执行 supervisor 图。

        Returns:
            {"execution_id", "status", "output", "messages"}
        """
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()

        state = SupervisorExecutionState(
            execution_id=execution_id,
            graph_id=graph_id,
            input_text=input_text,
            status="running",
            start_time=start_time.isoformat(),
        )
        _supervisor_executions[execution_id] = state

        bus = get_event_bus()
        await bus.publish(ExecutionEvent(
            event_type="task_progress",
            data={
                "execution_id": execution_id,
                "stage": "start",
                "graph_id": graph_id,
            },
        ))

        try:
            app = self.build_supervisor(graph_id)
            if not app:
                state.status = "failed"
                state.error = "Failed to build supervisor"
                state.end_time = datetime.now().isoformat()
                return {
                    "execution_id": execution_id,
                    "status": "failed",
                    "output": None,
                    "error": state.error,
                }

            # 记录 agent 名称
            graph_def = self.registry.get_graph(graph_id)
            for node in graph_def.get("nodes", []):
                if node.get("type") == "agent":
                    agent_id = node.get("agent_id") or node.get("data", {}).get("agent_id")
                    if agent_id:
                        state.agent_names.append(_sanitize_agent_name(agent_id))

            # 构建回调
            callback = EventBusCallbackHandler(execution_id=execution_id)

            # 执行
            result = await app.ainvoke(
                {"messages": [{"role": "user", "content": input_text}]},
                config={
                    "configurable": {"thread_id": thread_id},
                    "callbacks": [callback],
                },
            )

            # 提取输出
            messages = result.get("messages", [])
            output = ""
            for msg in reversed(messages):
                role = getattr(msg, "role", None) or getattr(msg, "type", None)
                if role in ("assistant", "ai"):
                    content = getattr(msg, "content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            item.get("text", str(item)) if isinstance(item, dict) else str(item)
                            for item in content
                        )
                    if content:
                        output = content
                        break

            state.status = "completed"
            state.output = output
            state.messages = [
                {
                    "role": getattr(m, "role", None) or getattr(m, "type", "unknown"),
                    "content": getattr(m, "content", ""),
                }
                for m in messages
            ]

            # 执行后审查（可选）
            review_enabled = os.getenv("AGENT_REVIEW_ENABLED", "false").lower() == "true"
            if review_enabled and state.agent_names:
                for agent_name in state.agent_names:
                    review_result = await self.review_agent_response(
                        agent_name=agent_name,
                        task=input_text,
                        output=state.output or ""
                    )
                    if review_result.get("review") == "retry":
                        logger.warning(f"[Supervisor] Review flagged retry for {agent_name}: {review_result.get('reason')}")
                        state.status = "needs_retry"
                        break

        except Exception as e:
            logger.error(f"[Supervisor] Execution failed: {e}", exc_info=True)
            env = ErrorEnvelope.from_exception(
                e,
                error_code="SUPERVISOR_ERROR",
                error_type=ErrorType.RECOVERABLE,
                tool_name="supervisor",
            )
            state.error = env.to_dict()
            log_error(state.error, trace_id=getattr(state, "execution_id", ""),
                      context={"graph_id": getattr(state, "graph_id", "")})

        end_time = datetime.now()
        state.end_time = end_time.isoformat()
        state.elapsed_ms = int((end_time - start_time).total_seconds() * 1000)

        await bus.publish(ExecutionEvent(
            event_type="agent_status",
            data={
                "execution_id": execution_id,
                "status": state.status,
                "agent_names": state.agent_names,
            },
        ))

        return {
            "execution_id": execution_id,
            "status": state.status,
            "output": state.output,
            "error": state.error,
        }

    async def stream_run(
        self, graph_id: str, input_text: str, thread_id: str = "default"
    ) -> AsyncGenerator[dict, None]:
        """流式执行 supervisor 图，产出事件。"""
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"

        yield {"type": "start", "execution_id": execution_id, "graph_id": graph_id}

        try:
            app = self.build_supervisor(graph_id)
            if not app:
                yield {"type": "error", "error": "Failed to build supervisor"}
                return

            callback = EventBusCallbackHandler(execution_id=execution_id)

            async for event in app.astream(
                {"messages": [{"role": "user", "content": input_text}]},
                config={
                    "configurable": {"thread_id": thread_id},
                    "callbacks": [callback],
                },
                stream_mode="updates",
            ):
                yield {"type": "update", "data": event}

            yield {"type": "done", "execution_id": execution_id}

        except Exception as e:
            logger.error(f"[Supervisor] Stream failed: {e}", exc_info=True)
            env_dict = ErrorEnvelope.from_exception(
                e,
                error_code="SUPERVISOR_STREAM_ERROR",
                error_type=ErrorType.RECOVERABLE,
                tool_name="supervisor",
            ).to_dict()
            log_error(env_dict, trace_id=execution_id, context={"graph_id": graph_id})
            yield {"type": "error", "error": env_dict}

    def get_execution(self, execution_id: str) -> Optional[SupervisorExecutionState]:
        """获取执行状态。"""
        return _supervisor_executions.get(execution_id)

    def list_executions(self) -> list:
        """列出所有执行。"""
        return [
            {
                "execution_id": eid,
                "graph_id": s.graph_id,
                "input_text": s.input_text[:50],
                "status": s.status,
                "agent_names": s.agent_names,
                "start_time": s.start_time,
                "interrupted": s.interrupted,
                "can_resume": s.can_resume,
            }
            for eid, s in _supervisor_executions.items()
        ]

    def interrupt(self, execution_id: str) -> dict:
        """中断指定执行"""
        state = _supervisor_executions.get(execution_id)
        if not state:
            return {"status": "error", "error": f"Execution not found: {execution_id}"}

        if state.status == "completed":
            return {"status": "error", "error": "Execution already completed"}

        state.interrupted = True
        state.status = "interrupted"
        logger.info(f"[Supervisor] Interrupted execution: {execution_id}")

        return {"status": "success", "execution_id": execution_id}

    def resume(self, execution_id: str) -> dict:
        """恢复指定执行"""
        state = _supervisor_executions.get(execution_id)
        if not state:
            return {"status": "error", "error": f"Execution not found: {execution_id}"}

        if not state.can_resume:
            return {"status": "error", "error": "Execution cannot be resumed"}

        state.interrupted = False
        state.status = "running"
        state.can_resume = False
        logger.info(f"[Supervisor] Resumed execution: {execution_id}")

        return {"status": "success", "execution_id": execution_id}

    async def review_agent_response(
        self, agent_name: str, task: str, output: str
    ) -> dict:
        """审查子Agent的响应，返回审查结果"""
        if not self.llm:
            return {"review": "pass", "reason": "No LLM available, auto-pass"}

        review_prompt = f"""请审查以下子Agent的输出是否满足要求：

任务: {task}
Agent: {agent_name}
输出: {output[:1000]}

请判断：
- 是否有错误或遗漏？
- 是否需要重试？
- 是否可以直接继续？

请返回JSON格式：
{{"review": "pass"|"retry"|"fix", "reason": "具体原因", "suggestion": "如果需要修正，具体建议"}}
"""
        try:
            response = await self.llm.ainvoke([{"role": "user", "content": review_prompt}])
            content = response.content if hasattr(response, 'content') else str(response)

            import json
            import re
            match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if match:
                result = json.loads(match.group())
                return {
                    "review": result.get("review", "pass"),
                    "reason": result.get("reason", ""),
                    "suggestion": result.get("suggestion", "")
                }
        except Exception as e:
            logger.warning(f"[Supervisor] Review failed: {e}")

        return {"review": "pass", "reason": "Review error, default pass"}


# 全局实例
_supervisor_manager: Optional[SupervisorManager] = None


def get_supervisor_manager(
    registry=None, llm=None, available_tools=None
) -> SupervisorManager:
    """获取全局 SupervisorManager 实例。"""
    global _supervisor_manager
    if _supervisor_manager is None:
        if registry is None:
            from .registry import get_registry
            registry = get_registry()
        _supervisor_manager = SupervisorManager(
            registry, llm, available_tools or []
        )
    return _supervisor_manager
