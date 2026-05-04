"""
FastAPI 后端 - 为 Vue Chat UI 提供 HTTP 接口
"""
import os
import sys
import logging
import time
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from src.agent.agent import create_agent as create_main_agent
from src.agent.config import DEFAULT_CONFIG
from src.agent.skills import SKILLS_REGISTRY, get_skill, SKILLS_INDEX
from src.agent.tools import TOOLS
from src.agent.registry import get_registry
from src.agent.orchestrator import get_orchestrator
from src.agent.event_bus import get_event_bus, ExecutionEvent
from src.agent.sop_state import (
    list_state_files,
    load_sop_state,
    load_latest_in_progress,
    save_sop_state,
    delete_sop_state,
    get_state_dir,
)
from src.agent.cli import get_available_clis, get_cli, init as init_cli
from src.agent.cli.dispatcher import dispatch_run, dispatch_run_stream, start_serve, stop_serve, get_active_serves

agent = None


# LangChain message type to OpenAI role mapping
_TYPE_TO_ROLE = {
    "ai": "assistant",
    "human": "user",
    "system": "system",
    "tool": "tool",
}


def _get_role(m):
    """Extract role from message (handles both dict and LangChain BaseMessage)"""
    if isinstance(m, dict):
        return m.get("role", "unknown")
    # Try role attribute first, then type attribute
    role = getattr(m, "role", None)
    if role:
        return role
    msg_type = getattr(m, "type", None)
    return _TYPE_TO_ROLE.get(msg_type, "unknown")


def _get_content(obj):
    """Extract string content from a message object"""
    if isinstance(obj, dict):
        content = obj.get("content", "")
    else:
        content = getattr(obj, "content", "")
    # Handle content that might be a list (e.g., [{"type": "text", "text": "..."}])
    if isinstance(content, list):
        return " ".join(
            item.get("text", str(item)) if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content) if content else ""


def _extract_msg(m):
    """Extract dict-like representation from a message"""
    if isinstance(m, dict):
        return m
    return {
        "role": _get_role(m),
        "content": _get_content(m),
        "tool_calls": getattr(m, "tool_calls", None),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    config = DEFAULT_CONFIG.model_copy(update={
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.getenv("AGENT_MODEL", "openai:gpt-4"),
    })
    agent = create_main_agent(config.model, config.api_key, config.base_url)
    
    if not agent.config.api_key:
        logger.error("OPENAI_API_KEY not set")
    
    # 初始化 Agent 注册表
    registry = get_registry(memory_dir=config.long_term.memory_dir)
    orchestrator = get_orchestrator(registry, agent.llm)
    logger.info("Agent Registry 和 Orchestrator 已初始化")
    
    yield
    if agent:
        agent.close()


app = FastAPI(title="LangGraph Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


@app.post("/chat")
async def chat(req: ChatRequest):
    global agent
    if not agent:
        return {
            "status": "error",
            "reply": "Agent not initialized",
            "messages": [],
            "tool_calls": None,
            "metrics": {},
            "compression_count": None,
            "elapsed_sec": 0,
        }
    start = time.time()

    result = agent.run(req.message, thread_id=req.thread_id)
    elapsed = time.time() - start

    if result["status"] == "error":
        return {
            "status": "error",
            "reply": result.get("error", "Unknown error"),
            "messages": [],
            "tool_calls": None,
            "metrics": {},
            "compression_count": None,
            "elapsed_sec": round(elapsed, 2),
        }

    graph_result = result["result"]
    messages_raw = graph_result.get("messages", [])

    messages = [_extract_msg(m) for m in messages_raw]

    # Collect tool calls and results
    tool_calls_list = []
    bus = get_event_bus()
    for m in messages:
        if m.get("tool_calls"):
            for tc in m["tool_calls"]:
                tool_calls_list.append(tc)
                await bus.publish(ExecutionEvent(
                    event_type="skill_trigger",
                    data={"tool_name": tc.get("name", "unknown"), "thread_id": req.thread_id},
                ))
        if m.get("role") == "tool":
            tool_calls_list.append({
                "name": "tool_result",
                "result": m.get("content", ""),
            })

    # Find the last assistant reply
    reply = ""
    for m in reversed(messages_raw):
        role = _get_role(m)
        if role == "assistant":
            reply = _get_content(m)
            break

    logger.info(f"[Chat] Reply extracted: {len(reply)} chars")

    metrics = agent.get_metrics()
    compression_count = graph_result.get("compression_count")

    return {
        "status": "success",
        "reply": reply,
        "messages": messages,
        "tool_calls": tool_calls_list if tool_calls_list else None,
        "metrics": metrics,
        "compression_count": compression_count,
        "elapsed_sec": round(elapsed, 2),
    }


@app.post("/archive")
async def archive():
    global agent
    result = agent.archive()
    return {"result": result}


@app.get("/metrics")
async def get_metrics():
    global agent
    if not agent:
        return {}
    return agent.get_metrics()


@app.get("/api/skills")
async def list_skills():
    skills = []
    for name, info in SKILLS_REGISTRY.items():
        skills.append({
            "name": info["name"],
            "description": info["description"],
            "use_when": info["use_when"],
            "dont_use_when": info["dont_use_when"],
        })
    return {"skills": skills, "count": len(skills)}


@app.get("/api/skills/{skill_name}")
async def get_skill_detail(skill_name: str):
    skill = get_skill(skill_name)
    if not skill:
        return {"error": f"Skill '{skill_name}' not found"}
    return {
        "name": skill["name"],
        "description": skill["description"],
        "use_when": skill["use_when"],
        "dont_use_when": skill["dont_use_when"],
        "full_content": skill["full_content"],
    }


@app.get("/api/sessions")
async def list_sessions():
    global agent
    if not agent:
        return {"sessions": [], "count": 0}
    sessions = agent.long_term.load_recent_sessions(limit=50)
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/api/sessions/{thread_id}")
async def get_session(thread_id: str):
    global agent
    if not agent:
        return {"thread_id": thread_id, "messages": [], "count": 0}
    messages = agent.long_term.load_session_messages(thread_id)
    return {"thread_id": thread_id, "messages": messages, "count": len(messages)}


@app.get("/api/tools")
async def list_tools():
    tools = []
    for t in TOOLS:
        tools.append({
            "name": t.name,
            "description": t.description,
        })
    return {"tools": tools, "count": len(tools)}


WORKFLOWS_FILE = os.path.join(os.path.dirname(__file__), "workflows.json")


def _load_workflows():
    if os.path.exists(WORKFLOWS_FILE):
        with open(WORKFLOWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_workflows(workflows):
    with open(WORKFLOWS_FILE, "w", encoding="utf-8") as f:
        json.dump(workflows, f, indent=2, ensure_ascii=False)


class WorkflowCreateRequest(BaseModel):
    name: str
    description: str = ""
    nodes: list = []
    edges: list = []


@app.get("/api/workflows")
async def list_workflows():
    workflows = _load_workflows()
    return {"workflows": workflows, "count": len(workflows)}


@app.post("/api/workflows")
async def create_workflow(req: WorkflowCreateRequest):
    workflows = _load_workflows()
    workflow = {
        "id": str(int(time.time() * 1000)),
        "name": req.name,
        "description": req.description,
        "nodes": req.nodes,
        "edges": req.edges,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    workflows.append(workflow)
    _save_workflows(workflows)
    return {"status": "success", "workflow": workflow}


@app.put("/api/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, req: WorkflowCreateRequest):
    workflows = _load_workflows()
    for w in workflows:
        if w["id"] == workflow_id:
            w["name"] = req.name
            w["description"] = req.description
            w["nodes"] = req.nodes
            w["edges"] = req.edges
            w["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _save_workflows(workflows)
            return {"status": "success", "workflow": w}
    return {"status": "error", "error": "Workflow not found"}


@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str):
    workflows = _load_workflows()
    workflows = [w for w in workflows if w["id"] != workflow_id]
    _save_workflows(workflows)
    return {"status": "success"}


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    workflows = _load_workflows()
    for w in workflows:
        if w["id"] == workflow_id:
            return {"workflow": w}
    return {"status": "error", "error": "Workflow not found"}


CLI_TASKS_FILE = os.path.join(os.path.dirname(__file__), "cli_tasks.json")


def _load_cli_tasks():
    if os.path.exists(CLI_TASKS_FILE):
        with open(CLI_TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_cli_tasks(tasks):
    with open(CLI_TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)


class DispatchRequest(BaseModel):
    cli_name: str = "opencode"
    task: str
    working_dir: str = "."
    mode: str = "run"
    auto_approve: bool = True
    timeout: int = 600


@app.get("/api/cli")
async def list_clis():
    init_cli()
    return {"clis": get_available_clis(), "count": len(get_available_clis())}


@app.post("/api/cli/dispatch")
async def dispatch_task(req: DispatchRequest):
    init_cli()
    cli = get_cli(req.cli_name)
    if not cli:
        raise HTTPException(status_code=404, detail=f"CLI '{req.cli_name}' not found")
    if not cli.get("available"):
        raise HTTPException(status_code=400, detail=f"CLI '{req.cli_name}' is not installed")

    result = dispatch_run(
        cli_name=req.cli_name,
        cli_path=cli["path"],
        task=req.task,
        working_dir=req.working_dir,
        auto_approve=req.auto_approve,
        timeout=req.timeout,
    )

    task_record = {
        "id": f"task-{int(time.time() * 1000)}",
        "cli_name": req.cli_name,
        "task": req.task,
        "working_dir": req.working_dir,
        "mode": req.mode,
        "result": result,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    tasks = _load_cli_tasks()
    tasks.append(task_record)
    _save_cli_tasks(tasks)

    return {"task": task_record}


def _sse_generator(cli_name, cli_path, task, working_dir=".", auto_approve=True, timeout=600):
    """将 dispatch_run_stream 的输出包装为 SSE 格式"""
    for event in dispatch_run_stream(
        cli_name=cli_name,
        cli_path=cli_path,
        task=task,
        working_dir=working_dir,
        auto_approve=auto_approve,
        timeout=timeout,
    ):
        event_type = event.get("type", "message")
        data = json.dumps(event, ensure_ascii=False)
        yield f"event: {event_type}\ndata: {data}\n\n"


@app.post("/api/cli/dispatch/stream")
async def dispatch_task_stream(req: DispatchRequest):
    init_cli()
    cli = get_cli(req.cli_name)
    if not cli:
        raise HTTPException(status_code=404, detail=f"CLI '{req.cli_name}' not found")
    if not cli.get("available"):
        raise HTTPException(status_code=400, detail=f"CLI '{req.cli_name}' is not installed")

    return StreamingResponse(
        _sse_generator(
            cli_name=req.cli_name,
            cli_path=cli["path"],
            task=req.task,
            working_dir=req.working_dir,
            auto_approve=req.auto_approve,
            timeout=req.timeout,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/cli/tasks")
async def list_cli_tasks():
    tasks = _load_cli_tasks()
    return {"tasks": list(reversed(tasks)), "count": len(tasks)}


@app.get("/api/cli/tasks/{task_id}")
async def get_cli_task(task_id: str):
    tasks = _load_cli_tasks()
    for t in tasks:
        if t["id"] == task_id:
            return {"task": t}
    return {"status": "error", "error": "Task not found"}


@app.get("/api/cli/serves")
async def list_active_serves():
    return {"serves": get_active_serves()}


@app.post("/api/cli/serves/{serve_id}/stop")
async def stop_cli_serve(serve_id: str):
    result = stop_serve(serve_id)
    return result


@app.get("/api/sop/state")
async def list_sop_states():
    files = list_state_files()
    states = []
    for f in files:
        parts = f.replace(".json", "").split("-")
        sop_name = parts[0]
        date = parts[-1] if len(parts) > 1 else ""
        states.append({"file": f, "sop": sop_name, "date": date})
    return {"states": states, "count": len(states)}


@app.get("/api/sop/state/{sop_name}")
async def get_sop_state(sop_name: str, date: str = None):
    state = load_sop_state(sop_name, date)
    if not state:
        return {"error": f"No in_progress state found for SOP: {sop_name}"}
    return {"state": state}


@app.post("/api/sop/state/{sop_name}/resume")
async def resume_sop(sop_name: str, message: str = None):
    state = load_sop_state(sop_name)
    if not state:
        return {"error": f"No in_progress state found for SOP: {sop_name}"}
    return {
        "status": "ready",
        "sop": sop_name,
        "current_step": state.get("current_step"),
        "steps": state.get("steps"),
        "answers": state.get("answers"),
    }


@app.delete("/api/sop/state/{sop_name}")
async def delete_sop_state_endpoint(sop_name: str, date: str = None):
    deleted = delete_sop_state(sop_name, date)
    return {"deleted": deleted, "sop": sop_name, "date": date}


@app.get("/api/sop/config")
async def get_sop_config():
    return {"state_dir": str(get_state_dir())}


# ========== Agent Registry APIs ==========

@app.get("/api/agents")
async def list_agents():
    """列出所有 Agent"""
    registry = get_registry()
    return {"agents": registry.list_agents(), "count": len(registry.list_agents())}


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    """获取 Agent 详情"""
    registry = get_registry()
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return {"agent": agent}


class AgentCreateRequest(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    llm_model: str = "openai:gpt-4"
    system_prompt: str = ""
    tools: list[str] = []
    execution_mode: str = "sync"
    timeout: int = 60


@app.post("/api/agents")
async def create_agent(req: AgentCreateRequest):
    """创建新 Agent"""
    registry = get_registry()
    agent = registry.create_agent(req.model_dump())
    return {"status": "success", "agent": agent}


@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, req: AgentCreateRequest):
    """更新 Agent"""
    registry = get_registry()
    agent = registry.update_agent(agent_id, req.model_dump())
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found or cannot update: {agent_id}")
    return {"status": "success", "agent": agent}


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """删除 Agent"""
    registry = get_registry()
    success = registry.delete_agent(agent_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"Agent not found or cannot delete: {agent_id}")
    return {"status": "success"}


# ========== Agent Graph APIs ==========

@app.get("/api/agent-graphs")
async def list_agent_graphs():
    """列出所有 Agent Graph"""
    registry = get_registry()
    graphs = registry.list_graphs()
    return {"graphs": graphs, "count": len(graphs)}


@app.get("/api/agent-graphs/{graph_id}")
async def get_agent_graph(graph_id: str):
    """获取 Graph 详情"""
    registry = get_registry()
    graph = registry.get_graph(graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_id}")
    return {"graph": graph}


class GraphCreateRequest(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    nodes: list = []
    edges: list = []
    parallel_groups: list = []
    config: dict = {}


@app.post("/api/agent-graphs")
async def create_agent_graph(req: GraphCreateRequest):
    """创建 Graph"""
    registry = get_registry()
    graph = registry.create_graph(req.model_dump())
    return {"status": "success", "graph": graph}


@app.put("/api/agent-graphs/{graph_id}")
async def update_agent_graph(graph_id: str, req: GraphCreateRequest):
    """更新 Graph"""
    registry = get_registry()
    graph = registry.update_graph(graph_id, req.model_dump())
    if not graph:
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_id}")
    return {"status": "success", "graph": graph}


@app.delete("/api/agent-graphs/{graph_id}")
async def delete_agent_graph(graph_id: str):
    """删除 Graph"""
    registry = get_registry()
    success = registry.delete_graph(graph_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Graph not found: {graph_id}")
    return {"status": "success"}


# ========== Execution APIs ==========

class ExecutionPlanRequest(BaseModel):
    graph_id: str
    input_text: str


@app.post("/api/execution/plan")
async def generate_execution_plan(req: ExecutionPlanRequest):
    """生成执行计划"""
    orchestrator = get_orchestrator()
    plan = orchestrator.generate_plan(req.graph_id, req.input_text)
    if not plan:
        raise HTTPException(status_code=400, detail="Failed to generate plan")
    
    return {
        "graph_id": plan.graph_id,
        "input_summary": plan.input_summary,
        "total_llm_calls": plan.total_llm_calls,
        "estimated_cost_usd": plan.estimated_cost_usd,
        "estimated_duration_sec": plan.estimated_duration_sec,
        "steps": plan.steps,
        "parallel_opportunities": plan.parallel_opportunities,
        "optimization_suggestions": plan.optimization_suggestions,
    }


class ExecutionRunRequest(BaseModel):
    graph_id: str
    input_text: str
    approved: bool = False


@app.post("/api/execution/run")
async def run_execution(req: ExecutionRunRequest):
    """执行 Graph"""
    global agent
    if not req.approved:
        return {
            "status": "pending_approval",
            "message": "等待用户批准执行计划"
        }
    
    orchestrator = get_orchestrator()
    execution = orchestrator.create_execution(req.graph_id, req.input_text)
    if not execution:
        raise HTTPException(status_code=400, detail="Failed to create execution")
    
    # 执行
    if agent and agent.llm:
        await orchestrator.run_execution(execution.execution_id, agent.llm, TOOLS)
    
    # 返回更新后的状态
    state = orchestrator.get_execution(execution.execution_id)["state"]
    
    return {
        "execution_id": execution.execution_id,
        "status": state.status,
        "output": state.output,
    }


# Legacy workflow execution (for backwards compatibility)
class LegacyWorkflowRequest(BaseModel):
    nodes: list
    edges: list
    input: str = "默认输入"


@app.post("/api/execute-workflow")
async def execute_legacy_workflow(req: LegacyWorkflowRequest):
    """Legacy workflow execution (backwards compatibility)"""
    global agent
    if not agent:
        return {"error": "Agent not initialized", "status": "error"}
    
    result = agent.run(req.input)
    raw_result = result.get("result", {})
    messages = raw_result.get("messages", []) if hasattr(raw_result, 'get') else []
    
    # Handle both dict and AIMessage objects
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, 'content'):
            content = last_msg.content
        elif isinstance(last_msg, dict):
            content = last_msg.get("content", "")
        else:
            content = str(last_msg)
    else:
        content = ""
    
    response_data = {
        "status": result.get("status"),
        "result": content,
    }
    print(f"[execute-workflow] Response: {response_data}")
    return response_data


@app.get("/api/execution/{execution_id}/state")
async def get_execution_state(execution_id: str):
    """获取执行状态"""
    orchestrator = get_orchestrator()
    exec_data = orchestrator.get_execution(execution_id)
    if not exec_data:
        raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}")
    
    state = exec_data["state"]
    return {
        "execution_id": state.execution_id,
        "graph_id": state.graph_id,
        "status": state.status,
        "current_step": state.current_step,
        "total_llm_calls": state.total_llm_calls,
        "total_cost_usd": state.total_cost_usd,
        "elapsed_ms": state.elapsed_ms,
        "steps": [
            {
                "step_id": s.step_id,
                "agent_id": s.agent_id,
                "agent_name": s.agent_name,
                "status": s.status,
                "llm_calls": len(s.llm_calls),
                "tool_calls": len(s.tool_calls),
            }
            for s in state.steps
        ]
    }


@app.get("/api/executions")
async def list_executions():
    """列出所有执行"""
    orchestrator = get_orchestrator()
    return {"executions": orchestrator.list_executions()}


@app.get("/api/execution/{execution_id}/report")
async def get_execution_report(execution_id: str):
    """获取执行完成后的详细报告"""
    orchestrator = get_orchestrator()
    exec_data = orchestrator.get_execution(execution_id)
    if not exec_data:
        raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}")
    
    state = exec_data["state"]
    plan = exec_data["plan"]
    
    # 计算统计数据
    total_llm_calls = sum(len(s.llm_calls) for s in state.steps)
    total_tokens = sum(sum(c.get("total_tokens", 0) for c in s.llm_calls) for s in state.steps)
    total_cost = sum(sum(c.get("cost_usd", 0) for c in s.llm_calls) for s in state.steps)
    
    # 成本分析
    step_costs = []
    for s in state.steps:
        cost = sum(c.get("cost_usd", 0) for c in s.llm_calls)
        pct = (cost / total_cost * 100) if total_cost > 0 else 0
        step_costs.append({"step_id": s.step_id, "cost_usd": round(cost, 4), "percentage": round(pct, 1)})
    
    # 工具使用分析
    tool_usage = {}
    for s in state.steps:
        for tc in s.tool_calls:
            tool_name = tc.get("tool_name", "unknown")
            tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1
    
    # 生成优化建议
    suggestions = []
    if state.status == "completed":
        if step_costs:
            max_cost_step = max(step_costs, key=lambda x: x["cost_usd"])
            suggestions.append({
                "priority": "medium",
                "category": "cost",
                "description": f"步骤 {max_cost_step['step_id']} 消耗成本最高",
                "action": "考虑优化该步骤的prompt或使用更便宜的模型"
            })
        
        if total_llm_calls > 5:
            suggestions.append({
                "priority": "high",
                "category": "parallel",
                "description": f"执行了 {total_llm_calls} 次 LLM 调用",
                "action": "考虑优化为并行执行"
            })
    
    return {
        "execution_id": execution_id,
        "graph_id": state.graph_id,
        "status": state.status,
        "input": state.input_text[:100],
        "output": state.output[:500] if state.output else None,
        
        "summary": {
            "total_steps": len(state.steps),
            "completed_steps": sum(1 for s in state.steps if s.status == "completed"),
            "failed_steps": sum(1 for s in state.steps if s.status == "failed"),
            "total_llm_calls": total_llm_calls,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 4),
            "total_duration_ms": state.elapsed_ms,
        },
        
        "step_details": [
            {
                "step_id": s.step_id,
                "agent_name": s.agent_name,
                "status": s.status,
                "llm_calls": len(s.llm_calls),
                "tokens": sum(c.get("total_tokens", 0) for c in s.llm_calls),
                "cost_usd": round(sum(c.get("cost_usd", 0) for c in s.llm_calls), 4),
                "duration_ms": 0,  # Simplified duration
                "result": s.result[:200] if s.result else None,
                "error": s.error,
            }
            for s in state.steps
        ],
        
        "optimization_insights": {
            "cost_breakdown": step_costs,
            "tool_usage": tool_usage,
            "suggestions": suggestions,
        }
    }


# ========== 实时事件 SSE 端点 ==========

@app.get("/api/events/stream")
async def events_stream():
    """SSE 实时事件流 - 推送 Agent 状态、技能触发、任务进度"""
    bus = get_event_bus()
    return StreamingResponse(
        bus.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/events/snapshot")
async def events_snapshot():
    """获取当前事件状态快照"""
    bus = get_event_bus()
    return bus.get_snapshot()


if __name__ == "__main__":
    import argparse
    import asyncio
    import threading
    import uvicorn
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="Run HTTP server only")
    parser.add_argument("--acp", action="store_true", help="Run ACP server only")
    parser.add_argument("--both", action="store_true", help="Run both HTTP and ACP")
    args, _ = parser.parse_known_args()
    
    if args.http:
        # 仅 HTTP
        uvicorn.run(app, host="0.0.0.0", port=8000)
    elif args.acp:
        # 仅 ACP
        from src.agent.acp_server import main as acp_main
        asyncio.run(acp_main())
    elif args.both:
        # HTTP + ACP 同时运行
        def run_acp():
            from src.agent.acp_server import main as acp_main
            asyncio.run(acp_main())
        
        threading.Thread(target=run_acp, daemon=True).start()
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        # 默认：全部运行
        def run_acp():
            from src.agent.acp_server import main as acp_main
            asyncio.run(acp_main())
        
        threading.Thread(target=run_acp, daemon=True).start()
        uvicorn.run(app, host="0.0.0.0", port=8000)
