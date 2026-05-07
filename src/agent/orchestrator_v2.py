"""
Dynamic Orchestrator

LLM-driven task decomposition into a DAG of skill/agent steps.
Executes steps in topological order, supports rollback and adaptive replanning.
"""
import uuid
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional
from collections import defaultdict, deque

from .state import OrchestratorStep, OrchestratorState
from .event_bus import get_event_bus, ExecutionEvent, publish_workflow_event
from .skills import SKILLS_REGISTRY, get_skill_content

logger = logging.getLogger(__name__)

# In-memory orchestration state store
_orchestrations: dict[str, OrchestratorState] = {}
_replan_approvals: dict[str, asyncio.Event] = {}


def get_orchestration(orchestration_id: str) -> Optional[OrchestratorState]:
    return _orchestrations.get(orchestration_id)


def list_orchestrations() -> list[dict]:
    return [
        {
            "orchestration_id": oid,
            "thread_id": s.thread_id,
            "input_text": s.input_text[:80],
            "status": s.status,
            "step_count": len(s.steps),
            "created_at": s.created_at,
        }
        for oid, s in _orchestrations.items()
    ]


PLAN_SYSTEM_PROMPT = """你是一个任务规划器。根据用户任务，将其分解为多个步骤（DAG），每个步骤分配给最合适的专业 Agent 或 Skill。

可用 Agents（注册表中的代理）：
{agents_list}

可用 Skills（技能提示模板）：
{skills_list}

规则：
1. 输出严格的 JSON 格式，不要包含其他文本
2. 每个步骤必须有 step_id（如 "step-1"）、agent_id、description、depends_on
3. agent_id 格式：对于注册表 agent 使用其 ID，对于 skill 使用 "skill:<skill_name>"
4. depends_on 列出依赖的 step_id，步骤可以并行执行（无依赖关系的步骤）
5. 步骤数量建议 2-6 个，不要太细碎
6. plan_summary 用一句话概括计划

输出格式：
```json
{{
  "plan_summary": "我将执行以下步骤...",
  "steps": [
    {{
      "step_id": "step-1",
      "agent_id": "builtin-code_review",
      "description": "审查代码质量和潜在 bug",
      "depends_on": []
    }},
    {{
      "step_id": "step-2",
      "agent_id": "skill:security_audit",
      "description": "进行安全审计",
      "depends_on": ["step-1"]
    }}
  ]
}}
```"""

REPLAN_PROMPT = """你是一个任务规划器。用户正在执行一个多步骤任务，某个步骤完成后发现可能需要调整后续计划。

原始任务：{input_text}

已完成的步骤和结果：
{completed_info}

当前剩余计划：
{remaining_info}

请判断是否需要修改剩余计划。如果不需要修改，输出 {{"change": false}}。如果需要修改，输出：
```json
{{
  "change": true,
  "reason": "修改原因",
  "new_steps": [ ... 新的剩余步骤 ... ]
}}
```

只输出 JSON，不要包含其他文本。"""


class DynamicOrchestrator:
    """动态任务编排器：LLM 驱动的任务分解、DAG 执行、回退和自适应重规划。"""

    def __init__(self, llm, registry, available_tools: list):
        self.llm = llm
        self.registry = registry
        self.available_tools = available_tools
        self._agent_cache: dict = {}

    async def plan(
        self, orchestration_id: str, input_text: str, thread_id: str
    ) -> OrchestratorState:
        """LLM 调用将任务分解为 DAG 步骤。"""
        now = datetime.now().isoformat()
        state = OrchestratorState(
            orchestration_id=orchestration_id,
            thread_id=thread_id,
            input_text=input_text,
            status="planning",
            created_at=now,
            updated_at=now,
        )
        _orchestrations[orchestration_id] = state

        # Build agents and skills lists for the prompt
        agents_list = self._format_agents_list()
        skills_list = self._format_skills_list()

        system_prompt = PLAN_SYSTEM_PROMPT.format(
            agents_list=agents_list,
            skills_list=skills_list,
        )

        # Call LLM with retries
        plan_json = None
        last_error = ""
        for attempt in range(3):
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": input_text},
                ]
                response = await asyncio.to_thread(
                    self.llm.invoke, messages
                )
                content = response.content if hasattr(response, "content") else str(response)
                plan_json = self._parse_plan_json(content)
                break
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"[Orchestrator] Plan attempt {attempt + 1} failed: {e}"
                )

        if plan_json is None:
            # Fallback: single-step linear plan using the main agent
            logger.warning(
                f"[Orchestrator] All plan attempts failed ({last_error}), using fallback"
            )
            plan_json = {
                "plan_summary": "使用主代理直接处理任务",
                "steps": [
                    {
                        "step_id": "step-1",
                        "agent_id": "__main_agent__",
                        "description": input_text[:200],
                        "depends_on": [],
                    }
                ],
            }

        # Build steps
        state.plan_summary = plan_json.get("plan_summary", "")
        state.steps = []
        for i, step_data in enumerate(plan_json.get("steps", [])):
            agent_id = step_data.get("agent_id", "__main_agent__")
            step = OrchestratorStep(
                step_id=step_data.get("step_id", f"step-{i + 1}"),
                agent_id=agent_id,
                agent_name=self._resolve_agent_name(agent_id),
                description=step_data.get("description", ""),
                depends_on=step_data.get("depends_on", []),
            )
            state.steps.append(step)

        state.status = "running"
        state.updated_at = datetime.now().isoformat()

        # Publish workflow_plan event with Vue Flow data
        nodes, edges = self._to_vue_flow(state.steps)
        await publish_workflow_event("workflow_plan", orchestration_id, {
            "plan_summary": state.plan_summary,
            "steps": [self._step_to_dict(s) for s in state.steps],
            "vue_flow_nodes": nodes,
            "vue_flow_edges": edges,
        })

        logger.info(
            f"[Orchestrator] Plan created: {len(state.steps)} steps, "
            f"summary={state.plan_summary[:80]}"
        )
        return state

    async def execute(self, orchestration_id: str) -> OrchestratorState:
        """按拓扑顺序执行步骤。"""
        state = _orchestrations.get(orchestration_id)
        if not state:
            raise ValueError(f"Orchestration not found: {orchestration_id}")

        topo_order = self._topological_order(state.steps)
        step_map = {s.step_id: s for s in state.steps}

        for step_id in topo_order:
            step = step_map[step_id]
            if step.status in ("completed", "skipped"):
                continue

            # Wait for dependencies
            for dep_id in step.depends_on:
                dep = step_map.get(dep_id)
                if dep and dep.status not in ("completed", "skipped"):
                    logger.warning(
                        f"[Orchestrator] Step {step_id} dependency {dep_id} not completed"
                    )
                    step.status = "skipped"
                    step.error = f"Dependency {dep_id} not completed"
                    await self._publish_step_update(orchestration_id, step)
                    break
            else:
                # All dependencies met
                await self.execute_step(orchestration_id, step_id)

                # Check replan trigger
                if step.status == "completed" and state.replan_count < 2:
                    should_replan = await self._check_replan_trigger(
                        orchestration_id, step
                    )
                    if should_replan:
                        state.replan_count += 1
                        # Wait for approval
                        approved = await self._wait_for_approval(orchestration_id)
                        if not approved:
                            logger.info(
                                f"[Orchestrator] Replan rejected for {orchestration_id}"
                            )

        # Determine final status
        failed = [s for s in state.steps if s.status == "failed"]
        if failed:
            state.status = "failed"
        else:
            state.status = "completed"
            # Collect final output from last completed steps
            completed = [s for s in state.steps if s.status == "completed"]
            if completed:
                state.final_output = "\n\n".join(
                    f"**{s.agent_name}**: {s.result or ''}" for s in completed
                )

        state.updated_at = datetime.now().isoformat()

        # Publish completion event
        completed_count = len([s for s in state.steps if s.status == "completed"])
        failed_count = len(failed)
        total_ms = sum(s.duration_ms for s in state.steps)
        await publish_workflow_event("workflow_complete", orchestration_id, {
            "final_output": state.final_output or "",
            "total_steps": len(state.steps),
            "completed_steps": completed_count,
            "failed_steps": failed_count,
            "total_duration_ms": total_ms,
            "status": state.status,
        })

        return state

    async def execute_step(
        self, orchestration_id: str, step_id: str
    ) -> OrchestratorStep:
        """执行单个步骤。"""
        state = _orchestrations[orchestration_id]
        step = next((s for s in state.steps if s.step_id == step_id), None)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        state.current_step_id = step_id
        step.status = "running"
        step.started_at = datetime.now().isoformat()
        await self._publish_step_update(orchestration_id, step)

        try:
            # Build context from dependent steps
            context = self._build_step_context(state, step)

            # Route to appropriate agent/skill
            result = await self._invoke_step(step, context)

            step.result = result
            step.status = "completed"
        except Exception as e:
            logger.error(
                f"[Orchestrator] Step {step_id} failed: {e}", exc_info=True
            )
            step.error = str(e)
            step.status = "failed"

        step.completed_at = datetime.now().isoformat()
        if step.started_at:
            start = datetime.fromisoformat(step.started_at)
            end = datetime.fromisoformat(step.completed_at)
            step.duration_ms = int((end - start).total_seconds() * 1000)

        state.updated_at = datetime.now().isoformat()
        await self._publish_step_update(orchestration_id, step)
        return step

    async def rollback(
        self, orchestration_id: str, step_id: str, reason: str = ""
    ) -> OrchestratorState:
        """回退到指定步骤并重新执行。"""
        state = _orchestrations.get(orchestration_id)
        if not state:
            raise ValueError(f"Orchestration not found: {orchestration_id}")

        # Find downstream steps (including target)
        downstream = self._get_downstream_steps(state.steps, step_id)

        # Reset downstream steps
        for step in state.steps:
            if step.step_id in downstream:
                step.status = "pending"
                step.result = None
                step.error = None
                step.started_at = None
                step.completed_at = None
                step.duration_ms = 0
                await self._publish_step_update(orchestration_id, step)

        state.status = "running"
        state.updated_at = datetime.now().isoformat()

        logger.info(
            f"[Orchestrator] Rollback to {step_id}, reset {len(downstream)} steps"
        )

        # Re-execute from the target step
        asyncio.create_task(self._re_execute_from(orchestration_id, step_id))
        return state

    async def approve_replan(self, orchestration_id: str, approved: bool = True):
        """批准或拒绝重规划。"""
        event = _replan_approvals.get(orchestration_id)
        if event:
            event._approved = approved  # noqa: store approval decision
            event.set()

    def get_state(self, orchestration_id: str) -> Optional[OrchestratorState]:
        return _orchestrations.get(orchestration_id)

    # ========== Internal Methods ==========

    async def _invoke_step(
        self, step: OrchestratorStep, context: str
    ) -> str:
        """根据 agent_id 路由到合适的 agent/skill 执行。"""
        agent_id = step.agent_id

        if agent_id == "__main_agent__":
            # Use the main agent directly
            return await self._invoke_main_agent(step.description, context)

        if agent_id.startswith("skill:"):
            # Use skill prompt directly with LLM
            skill_name = agent_id[len("skill:"):]
            return await self._invoke_skill(skill_name, step.description, context)

        if agent_id.startswith("builtin-"):
            # Use registered agent via sub_agent_factory
            return await self._invoke_registered_agent(
                agent_id, step.description, context
            )

        # Try as a direct agent ID
        return await self._invoke_registered_agent(
            agent_id, step.description, context
        )

    async def _invoke_main_agent(self, task: str, context: str) -> str:
        """使用主代理执行任务。"""
        messages = [
            {
                "role": "system",
                "content": "你是一个通用 AI 助手。请根据上下文完成任务。",
            },
            {
                "role": "user",
                "content": f"任务：{task}\n\n上下文：\n{context}" if context else task,
            },
        ]
        response = await asyncio.to_thread(self.llm.invoke, messages)
        return response.content if hasattr(response, "content") else str(response)

    async def _invoke_skill(
        self, skill_name: str, task: str, context: str
    ) -> str:
        """使用 skill prompt 调用 LLM。"""
        skill_content = get_skill_content(skill_name)
        if not skill_content:
            raise ValueError(f"Skill not found: {skill_name}")

        user_content = f"任务：{task}"
        if context:
            user_content += f"\n\n前置步骤结果：\n{context}"

        messages = [
            {"role": "system", "content": skill_content},
            {"role": "user", "content": user_content},
        ]
        response = await asyncio.to_thread(self.llm.invoke, messages)
        return response.content if hasattr(response, "content") else str(response)

    async def _invoke_registered_agent(
        self, agent_id: str, task: str, context: str
    ) -> str:
        """使用注册表中的 agent 执行任务。"""
        from .sub_agent_factory import build_sub_agent

        agent_def = self.registry.get_agent(agent_id)
        if not agent_def:
            raise ValueError(f"Agent not found: {agent_id}")

        # Build or get cached agent
        if agent_id not in self._agent_cache:
            self._agent_cache[agent_id] = build_sub_agent(
                agent_def, self.llm, self.available_tools
            )
        agent = self._agent_cache[agent_id]

        user_content = f"任务：{task}"
        if context:
            user_content += f"\n\n前置步骤结果：\n{context}"

        result = await asyncio.to_thread(
            agent.invoke, {"messages": [{"role": "user", "content": user_content}]}
        )

        # Extract the last assistant message
        messages = result.get("messages", [])
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
                    return content
        return str(result)

    def _build_step_context(self, state: OrchestratorState, step: OrchestratorStep) -> str:
        """构建步骤执行的上下文（来自依赖步骤的结果）。"""
        if not step.depends_on:
            return ""
        step_map = {s.step_id: s for s in state.steps}
        parts = []
        for dep_id in step.depends_on:
            dep = step_map.get(dep_id)
            if dep and dep.result:
                parts.append(f"[{dep.agent_name}] {dep.result[:500]}")
        return "\n\n".join(parts)

    def _format_agents_list(self) -> str:
        """格式化可用 agents 列表。"""
        agents = self.registry.list_agents()
        if not agents:
            return "（无注册代理）"
        lines = []
        for a in agents:
            aid = a.get("id", "")
            name = a.get("name", "")
            desc = a.get("description", "")
            lines.append(f"- {aid}: {name} - {desc}")
        return "\n".join(lines)

    def _format_skills_list(self) -> str:
        """格式化可用 skills 列表。"""
        lines = []
        for name, skill in SKILLS_REGISTRY.items():
            desc = skill.get("description", "")
            use_when = ", ".join(skill.get("use_when", []))
            lines.append(f"- skill:{name}: {desc} (适用: {use_when})")
        return "\n".join(lines)

    def _resolve_agent_name(self, agent_id: str) -> str:
        """解析 agent_id 为人类可读名称。"""
        if agent_id == "__main_agent__":
            return "主代理"
        if agent_id.startswith("skill:"):
            skill_name = agent_id[len("skill:"):]
            skill = SKILLS_REGISTRY.get(skill_name, {})
            return skill.get("name", skill_name)
        agent_def = self.registry.get_agent(agent_id)
        if agent_def:
            return agent_def.get("name", agent_id)
        return agent_id

    def _parse_plan_json(self, content: str) -> dict:
        """从 LLM 响应中解析 JSON 计划。"""
        # Try to extract JSON from markdown code blocks
        import re
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1).strip()

        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in the text
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Failed to parse plan JSON from: {content[:200]}")

    def _topological_order(self, steps: list[OrchestratorStep]) -> list[str]:
        """返回拓扑排序后的 step_id 列表。"""
        step_ids = {s.step_id for s in steps}
        in_degree: dict[str, int] = {sid: 0 for sid in step_ids}
        graph: dict[str, list[str]] = defaultdict(list)

        for step in steps:
            for dep in step.depends_on:
                if dep in step_ids:
                    graph[dep].append(step.step_id)
                    in_degree[step.step_id] += 1

        queue = deque(sid for sid, deg in in_degree.items() if deg == 0)
        order = []

        while queue:
            sid = queue.popleft()
            order.append(sid)
            for neighbor in graph[sid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(steps):
            logger.warning("[Orchestrator] Cycle detected in step dependencies")

        return order

    def _get_downstream_steps(
        self, steps: list[OrchestratorStep], target_step_id: str
    ) -> set[str]:
        """获取目标步骤及其所有下游步骤（传递依赖）。"""
        step_map = {s.step_id: s for s in steps}
        downstream = {target_step_id}
        queue = deque([target_step_id])

        while queue:
            current = queue.popleft()
            for step in steps:
                if step.step_id not in downstream:
                    if current in step.depends_on:
                        downstream.add(step.step_id)
                        queue.append(step.step_id)

        return downstream

    def _to_vue_flow(
        self, steps: list[OrchestratorStep]
    ) -> tuple[list[dict], list[dict]]:
        """将步骤转换为 Vue Flow 节点和边。"""
        # Compute depth for layout
        depth_map = self._compute_depth(steps)
        depth_indices: dict[int, int] = {}

        nodes = []
        for step in steps:
            depth = depth_map.get(step.step_id, 0)
            row = depth_indices.get(depth, 0)
            depth_indices[depth] = row + 1

            nodes.append({
                "id": step.step_id,
                "type": "orchestrator",
                "position": {"x": depth * 280, "y": row * 140},
                "data": {
                    "step_id": step.step_id,
                    "agent_name": step.agent_name,
                    "description": step.description,
                    "status": step.status,
                    "result": step.result,
                    "error": step.error,
                    "duration_ms": step.duration_ms,
                },
            })

        edges = []
        for step in steps:
            for dep_id in step.depends_on:
                edges.append({
                    "id": f"{dep_id}-{step.step_id}",
                    "source": dep_id,
                    "target": step.step_id,
                    "type": "smoothstep",
                    "animated": False,
                })

        return nodes, edges

    def _compute_depth(self, steps: list[OrchestratorStep]) -> dict[str, int]:
        """计算每个步骤在 DAG 中的深度。"""
        step_ids = {s.step_id for s in steps}
        depth: dict[str, int] = {}

        def _dfs(sid: str) -> int:
            if sid in depth:
                return depth[sid]
            step = next((s for s in steps if s.step_id == sid), None)
            if not step or not step.depends_on:
                depth[sid] = 0
                return 0
            max_dep_depth = max(
                _dfs(d) for d in step.depends_on if d in step_ids
            )
            depth[sid] = max_dep_depth + 1
            return depth[sid]

        for step in steps:
            _dfs(step.step_id)

        return depth

    def _step_to_dict(self, step: OrchestratorStep) -> dict:
        return {
            "step_id": step.step_id,
            "agent_id": step.agent_id,
            "agent_name": step.agent_name,
            "description": step.description,
            "depends_on": step.depends_on,
            "status": step.status,
            "result": step.result,
            "error": step.error,
            "started_at": step.started_at,
            "completed_at": step.completed_at,
            "duration_ms": step.duration_ms,
        }

    async def _publish_step_update(
        self, orchestration_id: str, step: OrchestratorStep
    ):
        await publish_workflow_event("step_update", orchestration_id, self._step_to_dict(step))

    async def _check_replan_trigger(
        self, orchestration_id: str, completed_step: OrchestratorStep
    ) -> bool:
        """检查是否需要重规划。"""
        state = _orchestrations[orchestration_id]
        remaining = [s for s in state.steps if s.status == "pending"]
        if not remaining:
            return False

        completed_info = "\n".join(
            f"- [{s.agent_name}] {s.description}: {(s.result or '')[:200]}"
            for s in state.steps
            if s.status == "completed"
        )
        remaining_info = "\n".join(
            f"- {s.step_id} [{s.agent_name}] {s.description} (依赖: {s.depends_on})"
            for s in remaining
        )

        prompt = REPLAN_PROMPT.format(
            input_text=state.input_text,
            completed_info=completed_info,
            remaining_info=remaining_info,
        )

        try:
            response = await asyncio.to_thread(
                self.llm.invoke,
                [{"role": "user", "content": prompt}],
            )
            content = response.content if hasattr(response, "content") else str(response)

            import re
            json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
            if json_match:
                content = json_match.group(1).strip()
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(content[start:end])
                if result.get("change"):
                    # Publish replan event
                    new_steps = result.get("new_steps", [])
                    await publish_workflow_event(
                        "workflow_replan", orchestration_id, {
                            "reason": result.get("reason", "Plan adjustment needed"),
                            "new_steps": new_steps,
                            "requires_approval": True,
                        }
                    )
                    return True
        except Exception as e:
            logger.warning(f"[Orchestrator] Replan check failed: {e}")

        return False

    async def _wait_for_approval(self, orchestration_id: str) -> bool:
        """等待用户批准重规划。"""
        event = asyncio.Event()
        _replan_approvals[orchestration_id] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=300)  # 5 min timeout
            return getattr(event, "_approved", False)
        except asyncio.TimeoutError:
            logger.warning(
                f"[Orchestrator] Replan approval timeout for {orchestration_id}"
            )
            return False
        finally:
            _replan_approvals.pop(orchestration_id, None)

    async def _re_execute_from(
        self, orchestration_id: str, step_id: str
    ):
        """从指定步骤开始重新执行。"""
        state = _orchestrations.get(orchestration_id)
        if not state:
            return

        topo_order = self._topological_order(state.steps)
        step_map = {s.step_id: s for s in state.steps}

        # Find the index of the target step
        try:
            start_idx = topo_order.index(step_id)
        except ValueError:
            return

        for sid in topo_order[start_idx:]:
            step = step_map[sid]
            if step.status in ("completed", "skipped"):
                continue
            await self.execute_step(orchestration_id, sid)

        # Update final status
        failed = [s for s in state.steps if s.status == "failed"]
        state.status = "failed" if failed else "completed"
        state.updated_at = datetime.now().isoformat()
