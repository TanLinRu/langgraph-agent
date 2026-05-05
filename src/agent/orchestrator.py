"""
⚠️ DEPRECATED: 此模块已废弃，请使用 SupervisorManager
移除时间: 2026-Q3

Multi-Agent 编排器（已废弃）

负责执行计划生成、执行调度、状态管理
"""
import json
import time
import uuid
import logging
from datetime import datetime
from typing import Optional, Callable
from dataclasses import dataclass, field

from .event_bus import get_event_bus, ExecutionEvent

logger = logging.getLogger(__name__)

# 简单的内存执行状态存储
_execution_states = {}


@dataclass
class ExecutionStep:
    """执行步骤"""
    step_id: int
    agent_id: str
    agent_name: str
    agent_description: str
    expected_tools: list = field(default_factory=list)
    depends_on: list = field(default_factory=list)
    is_parallel: bool = False
    estimated_calls: int = 1
    estimated_tokens: int = 0
    
    # 运行时状态
    status: str = "pending"
    llm_calls: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ExecutionPlan:
    """执行计划"""
    graph_id: str
    input_summary: str
    total_llm_calls: int
    estimated_cost_usd: float
    estimated_duration_sec: int
    steps: list
    
    parallel_opportunities: list = field(default_factory=list)
    optimization_suggestions: list = field(default_factory=list)


@dataclass
class ExecutionState:
    """执行状态"""
    execution_id: str
    graph_id: str
    input_text: str
    status: str = "pending"
    current_step: Optional[int] = None
    
    steps: list = field(default_factory=list)
    
    total_llm_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    elapsed_ms: int = 0
    
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    
    # 输出
    output: Optional[str] = None
    
    # 性能分析
    performance_insights: dict = field(default_factory=dict)


class MultiAgentOrchestrator:
    """多Agent编排器"""
    
    # 模型成本估算
    MODEL_COSTS = {
        "gpt-4": {"prompt": 0.03, "completion": 0.06, "avg_tokens": 2000},
        "gpt-4o": {"prompt": 0.005, "completion": 0.015, "avg_tokens": 1500},
        "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006, "avg_tokens": 1500},
    }
    
    def __init__(self, registry, llm=None):
        self.registry = registry
        self.llm = llm
    
    def generate_plan(self, graph_id: str, input_text: str) -> Optional[ExecutionPlan]:
        """生成执行计划"""
        graph = self.registry.get_graph(graph_id)
        if not graph:
            logger.error(f"Graph not found: {graph_id}")
            return None
        
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        
        if not nodes:
            return None
        
        # 构建依赖图
        step_map = {}  # node_id -> step_id
        steps = []
        
        # 简单拓扑排序 - 按顺序创建步骤
        # 实际应该根据 edges 做拓扑排序，这里简化处理
        parallel_groups = graph.get("parallel_groups", [])
        
        step_id = 1
        for node in nodes:
            if node.get("type") != "agent":
                continue
            
            agent_id = node.get("agent_id", node.get("data", {}).get("agent_id"))
            agent = self.registry.get_agent(agent_id) if agent_id else None
            
            # 检查依赖
            depends_on = []
            for edge in edges:
                if edge.get("target") == node.get("id"):
                    src_node_id = edge.get("source")
                    if src_node_id in step_map:
                        depends_on.append(step_map[src_node_id])
            
            # 检查是否可并行
            is_parallel = False
            for group in parallel_groups:
                if node.get("id") in group:
                    is_parallel = True
                    break
            
            # 估算
            estimated_tokens = 1500  # 简化估算
            
            step = {
                "step_id": step_id,
                "agent_id": agent_id or "unknown",
                "agent_name": agent.get("name", node.get("data", {}).get("label", "未知")),
                "agent_description": agent.get("description", "") if agent else "",
                "expected_tools": agent.get("tools", []) if agent else [],
                "depends_on": depends_on,
                "is_parallel": is_parallel,
                "estimated_calls": 1,
                "estimated_tokens": estimated_tokens,
            }
            steps.append(step)
            
            step_map[node.get("id")] = step_id
            step_id += 1
        
        # 计算总调用次数
        total_llm_calls = sum(s["estimated_calls"] for s in steps)
        
        # 估算成本（简化）
        estimated_cost_usd = total_llm_calls * 0.02  # 简化估算
        
        # 检测并行机会
        parallel_opportunities = self._detect_parallel_opportunities(steps, edges, nodes)
        
        # 生成优化建议
        optimization_suggestions = self._generate_optimization_suggestions(
            steps, parallel_opportunities, graph
        )
        
        return ExecutionPlan(
            graph_id=graph_id,
            input_summary=input_text[:100],
            total_llm_calls=total_llm_calls,
            estimated_cost_usd=round(estimated_cost_usd, 4),
            estimated_duration_sec=total_llm_calls * 5,  # 简化估算
            steps=steps,
            parallel_opportunities=parallel_opportunities,
            optimization_suggestions=optimization_suggestions,
        )
    
    def _detect_parallel_opportunities(self, steps: list, edges: list, nodes: list) -> list:
        """检测并行执行机会"""
        opportunities = []
        
        # 简单检测：没有依赖关系的步骤可以并行
        # 实际应该用更复杂的图算法
        for i, step in enumerate(steps):
            if step.get("depends_on"):
                continue
            
            # 找同样没有依赖的后续步骤
            parallel_group = [step["step_id"]]
            for j in range(i+1, len(steps)):
                other = steps[j]
                if not other.get("depends_on"):
                    # 检查是否在同一并行组
                    for group in nodes:
                        pass  # 简化
            
            if len(parallel_group) > 1:
                opportunities.append({
                    "group": parallel_group,
                    "reason": "无依赖关系，可并行执行",
                    "saved_calls": len(parallel_group) - 1,
                })
        
        return opportunities
    
    def _generate_optimization_suggestions(self, steps: list, parallels: list, graph: dict) -> list:
        """生成优化建议"""
        suggestions = []
        
        # 并行优化建议
        if parallels:
            for p in parallels:
                if p.get("saved_calls", 0) > 0:
                    suggestions.append({
                        "type": "parallel",
                        "description": f"步骤 {p['group']} 可并行执行",
                        "impact": "high",
                        "detail": f"可节省 {p['saved_calls']} 次 LLM 调用",
                    })
        
        # 步骤过多建议
        if len(steps) > 5:
            suggestions.append({
                "type": "combine",
                "description": "步骤数量较多",
                "impact": "medium",
                "detail": f"当前有 {len(steps)} 个步骤，考虑合并相关 Agent",
            })
        
        # 工具配置建议
        for step in steps:
            tools = step.get("expected_tools", [])
            if len(tools) > 5:
                suggestions.append({
                    "type": "reduce",
                    "description": f"Agent {step['agent_name']} 工具过多",
                    "impact": "medium",
                    "detail": f"配置了 {len(tools)} 个工具，可能导致选择困难",
                })
        
        return suggestions
    
    def create_execution(self, graph_id: str, input_text: str) -> Optional[ExecutionState]:
        """创建执行实例"""
        graph = self.registry.get_graph(graph_id)
        if not graph:
            return None
        
        plan = self.generate_plan(graph_id, input_text)
        if not plan:
            return None
        
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"
        
        # 初始化步骤状态
        steps = []
        for step_data in plan.steps:
            step = ExecutionStep(
                step_id=step_data["step_id"],
                agent_id=step_data["agent_id"],
                agent_name=step_data["agent_name"],
                agent_description=step_data.get("agent_description", ""),
                expected_tools=step_data.get("expected_tools", []),
                depends_on=step_data.get("depends_on", []),
                is_parallel=step_data.get("is_parallel", False),
                estimated_calls=step_data.get("estimated_calls", 1),
                estimated_tokens=step_data.get("estimated_tokens", 0),
            )
            steps.append(step)
        
        state = ExecutionState(
            execution_id=execution_id,
            graph_id=graph_id,
            input_text=input_text,
            steps=steps,
        )
        
        _execution_states[execution_id] = {
            "state": state,
            "plan": plan,
            "graph": graph,
        }
        
        logger.info(f"创建执行: {execution_id}, 步骤数: {len(steps)}")
        return state
    
    def get_execution(self, execution_id: str) -> Optional[dict]:
        """获取执行状态"""
        return _execution_states.get(execution_id)
    
    def list_executions(self) -> list:
        """列出所有执行"""
        result = []
        for exec_id, data in _execution_states.items():
            state = data["state"]
            result.append({
                "execution_id": exec_id,
                "graph_id": state.graph_id,
                "input_text": state.input_text[:50],
                "status": state.status,
                "total_llm_calls": state.total_llm_calls,
                "total_cost_usd": state.total_cost_usd,
                "created_at": state.start_time,
            })
        return result
    
    async def execute_step(self, step: ExecutionStep, llm, tools, input_context: str = "", user_input: str = "") -> ExecutionStep:
        """执行单个步骤"""
        from datetime import datetime
        import logging
        logger = logging.getLogger(__name__)
        
        step.status = "running"
        step.start_time = datetime.now().isoformat()

        bus = get_event_bus()
        await bus.publish(ExecutionEvent(
            event_type="agent_status",
            data={"agent_id": step.agent_id, "agent_name": step.agent_name, "status": "running"},
        ))

        # 获取agent配置
        agent = self.registry.get_agent(step.agent_id)
        system_prompt = agent.get("system_prompt", "") if agent else ""
        execution_mode = agent.get("execution_mode", "sync") if agent else "sync"
        
        # 构建消息 - 使用用户输入的任务，而不是 agent 固定描述
        user_task = user_input or step.agent_description or "执行任务"
        user_content = f"直接执行：{user_task}\n直接开始，不要问问题。"
        
        if input_context:
            user_content += f"\n\n上下文信息：\n{input_context}"
        
        logger.info(f"[execute_step] agent_id={step.agent_id}, agent_name={step.agent_name}, execution_mode={execution_mode}")
        logger.info(f"[execute_step] user_content={user_content[:200]}...")
        
        try:
            start_time = time.time()
            
            # 根据 execution_mode 决定调用方式
            if execution_mode == "acp":
                # 通过 opencode run CLI 调用 OpenCode
                from .opencode_client import get_opencode_client
                client = get_opencode_client(timeout=agent.get("timeout", 180))
                skill = agent.get("skill")
                logger.info(f"[execute_step] Calling OpenCode CLI with skill={skill}")
                result = client.call(user_content, system_prompt, skill)
                logger.info(f"[execute_step] OpenCode result={result[:200] if result else 'empty'}...")
                
                # 记录调用
                step.llm_calls.append({
                    "call_index": len(step.llm_calls) + 1,
                    "timestamp": datetime.now().isoformat(),
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_usd": 0,
                })
                step.result = result
                
            else:
                # 通过 LLM 调用
                logger.info(f"[execute_step] Using LLM mode (not ACP)")
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
                
                logger.info(f"[execute_step] Invoking LLM with messages count={len(messages)}")
                response = llm.invoke(messages)
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.info(f"[execute_step] LLM response elapsed={elapsed_ms}ms, content={response.content[:200] if hasattr(response, 'content') else str(response)[:200]}...")
                
                # 记录LLM调用
                prompt_tokens = response.response_metadata.get('prompt_tokens', 0) if hasattr(response, 'response_metadata') else 0
                completion_tokens = response.response_metadata.get('completion_tokens', 0) if hasattr(response, 'response_metadata') else 0
                
                step.llm_calls.append({
                    "call_index": len(step.llm_calls) + 1,
                    "timestamp": datetime.now().isoformat(),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "cost_usd": (prompt_tokens / 1000 * 0.03) + (completion_tokens / 1000 * 0.06),
                })
                
                step.result = response.content if hasattr(response, 'content') else str(response)
            
            step.status = "completed"
            step.end_time = datetime.now().isoformat()
            await bus.publish(ExecutionEvent(
                event_type="agent_status",
                data={"agent_id": step.agent_id, "agent_name": step.agent_name, "status": "completed"},
            ))
            await bus.publish(ExecutionEvent(
                event_type="step_complete",
                data={"step_id": step.step_id, "agent_id": step.agent_id, "status": "completed"},
            ))

        except Exception as e:
            step.status = "failed"
            step.error = str(e)
            step.end_time = datetime.now().isoformat()
            await bus.publish(ExecutionEvent(
                event_type="agent_status",
                data={"agent_id": step.agent_id, "agent_name": step.agent_name, "status": "failed", "error": str(e)},
            ))
        
        return step
    
    async def run_execution(self, execution_id: str, llm, available_tools) -> Optional[ExecutionState]:
        """执行整个Graph"""
        import logging
        logger = logging.getLogger(__name__)
        
        exec_data = self.get_execution(execution_id)
        if not exec_data:
            logger.error(f"[run_execution] Execution not found: {execution_id}")
            return None
        
        logger.info(f"[run_execution] Starting execution_id={execution_id}, graph_id={exec_data['state'].graph_id}")
        
        state = exec_data["state"]
        state.status = "running"
        state.start_time = datetime.now().isoformat()
        
        # 按顺序执行步骤（简化版，实际应该根据依赖图）
        results = {}
        
        bus = get_event_bus()
        for step in state.steps:
            logger.info(f"[run_execution] Processing step {step.step_id}: agent_id={step.agent_id}, agent_name={step.agent_name}")
            await bus.publish(ExecutionEvent(
                event_type="task_progress",
                data={
                    "execution_id": execution_id,
                    "current_step": step.step_id,
                    "total_steps": len(state.steps),
                    "agent_name": step.agent_name,
                },
            ))
            # 检查依赖是否完成
            deps = step.depends_on
            input_context = ""
            for dep_step_id in deps:
                if dep_step_id in results:
                    input_context += f"\n\n--- 上一步 {dep_step_id} 结果 ---\n{results[dep_step_id]}"
            
            # 执行步骤 - 传入用户输入
            step_tools = available_tools
            await self.execute_step(step, llm, step_tools, input_context, state.input_text)
            
            # 记录结果
            if step.result:
                results[step.step_id] = step.result
            
            # 更新统计
            state.total_llm_calls += len(step.llm_calls)
            for call in step.llm_calls:
                state.total_cost_usd += call.get("cost_usd", 0)
                state.total_tokens += call.get("total_tokens", 0)
            
            state.current_step = step.step_id
            
            # 如果失败，停止
            if step.status == "failed":
                logger.error(f"[run_execution] Step {step.step_id} FAILED: {step.error}")
                state.status = "failed"
                break
        
        logger.info(f"[run_execution] Execution {execution_id} completed with status={state.status}")
        
        if state.status == "running":
            state.status = "completed"
        
        state.end_time = datetime.now().isoformat()
        
        # 生成输出
        if results:
            state.output = "\n\n---\n\n".join(f"Step {k}: {v[:500]}" for k, v in results.items())
        
        # 性能分析
        state.performance_insights = {
            "slowest_step": None,
            "most_expensive_step": None,
            "tool_call_count": sum(len(s.tool_calls) for s in state.steps),
        }
        
        return state


# 全局编排器实例
_orchestrator: Optional[MultiAgentOrchestrator] = None


def get_orchestrator(registry=None, llm=None) -> MultiAgentOrchestrator:
    """获取全局编排器"""
    global _orchestrator
    if _orchestrator is None:
        if registry is None:
            from .registry import get_registry
            registry = get_registry()
        _orchestrator = MultiAgentOrchestrator(registry, llm)
    return _orchestrator