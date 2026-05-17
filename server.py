"""
FastAPI 后端 - 为 Vue Chat UI 提供 HTTP 接口
"""
import os
import sys
import uuid
import logging
import time
import json
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from src.agent.schemas.agent_protocol import StructuredAgentError, ErrorLevel
from pydantic import BaseModel, Field
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
from src.agent.orchestrator_v2 import DynamicOrchestrator, get_orchestration, list_orchestrations, restore_orchestrations
from src.agent.task_classifier import classify_task, get_routing_decision, should_orchestrate
from src.agent.supervisor import get_supervisor_manager, SupervisorManager
from src.agent.event_bus import get_event_bus, ExecutionEvent
from src.agent.metrics_collector import get_metrics_collector
from src.agent.metrics_store import get_metrics_store
from src.agent.system_metrics import get_system_collector
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
from src.agent.trace_context import generate_trace_id, set_trace_id
from src.agent.audit_log import write_audit, AuditAction

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

    # 初始化 Supervisor Manager
    supervisor_mgr = get_supervisor_manager(registry, agent.llm, TOOLS)
    app.state.supervisor_mgr = supervisor_mgr

    # 初始化 Dynamic Orchestrator
    dynamic_orchestrator = DynamicOrchestrator(agent.llm, registry, TOOLS)
    app.state.dynamic_orchestrator = dynamic_orchestrator

    restored = restore_orchestrations(config.long_term.memory_dir)
    if restored > 0:
        logger.info(f"[Startup] Restored {restored} incomplete orchestrations from checkpoints")
    
    # 初始化 Metrics
    metrics_collector = get_metrics_collector()
    metrics_store = get_metrics_store()
    system_collector = get_system_collector()
    app.state.metrics_collector = metrics_collector
    app.state.metrics_store = metrics_store
    
    # 启动系统指标采集
    await system_collector.start()
    
    logger.info("Agent Registry, SupervisorManager 和 Metrics 已初始化")
    
    yield
    if agent:
        agent.close()


app = FastAPI(title="LangGraph Agent API", lifespan=lifespan)


@app.exception_handler(StructuredAgentError)
async def structured_agent_error_handler(request: Request, exc: StructuredAgentError):
    env = exc.to_envelope()
    status_code = 500
    if env.error_level in (ErrorLevel.HIGH, ErrorLevel.CRITICAL):
        status_code = 500
    elif env.error_level == ErrorLevel.MEDIUM:
        status_code = 400
    else:
        status_code = 422
    return JSONResponse(
        status_code=status_code,
        content=env.to_dict(),
    )


cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100000)
    thread_id: str = "default"


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100000)
    thread_id: str = "default"
    force_mode: str | None = None  # "direct" | "orchestrator" | None


@app.post("/chat")
async def chat(req: ChatRequest):
    global agent
    tid = generate_trace_id()
    set_trace_id(tid)
    if not agent:
        return {
            "status": "error",
            "reply": "Agent not initialized",
            "messages": [],
            "tool_calls": None,
            "metrics": {},
            "compression_count": None,
            "elapsed_sec": 0,
            "trace_id": tid,
        }
    start = time.time()

    classification = classify_task(req.message, llm=agent.llm)
    routing = get_routing_decision(classification)

    if routing["route_to"] == "orchestrator":
        orchestrator = app.state.dynamic_orchestrator
        orchestration_id = f"chat-{req.thread_id}-{int(time.time())}"
        await orchestrator.plan(orchestration_id, req.message, req.thread_id)
        state = await orchestrator.execute(orchestration_id)

        all_results = []
        for step in state.steps:
            if step.status == "completed" and step.result:
                all_results.append({
                    "step_id": step.step_id,
                    "description": step.description,
                    "agent_id": step.agent_id,
                    "result": step.result,
                    "status": step.status,
                })

        combined_reply = "\n\n---\n\n".join([
            f"### Step: {s['description']}\n**Agent**: {s['agent_id']}\n**Result**: {s['result']}"
            for s in all_results
        ]) if all_results else "任务已完成"

        return {
            "status": "success",
            "reply": combined_reply,
            "messages": [],
            "tool_calls": None,
            "metrics": {},
            "compression_count": None,
            "elapsed_sec": round(time.time() - start, 2),
            "orchestration": {
                "id": orchestration_id,
                "steps": len(state.steps),
                "routing": routing,
            }
        }

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

    from src.agent.agent import _deduplicate_messages
    messages_raw = _deduplicate_messages(messages_raw)
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
        "trace_id": tid,
        "routing": routing,
    }


@app.post("/api/agent/run")
async def agent_run(req: AgentRunRequest):
    """Unified agent entry point - automatically routes to direct or orchestrator based on task complexity."""
    global agent
    tid = generate_trace_id()
    set_trace_id(tid)

    if not agent:
        return {
            "status": "error",
            "reply": "Agent not initialized",
            "trace_id": tid,
            "route": None,
            "classification": None,
        }

    start = time.time()
    classification = classify_task(req.message, llm=agent.llm)
    routing = get_routing_decision(classification)

    if req.force_mode == "orchestrator" or (req.force_mode is None and routing["route_to"] == "orchestrator"):
        orchestrator = app.state.dynamic_orchestrator
        orchestration_id = f"run-{req.thread_id}-{int(time.time())}"
        write_audit(AuditAction.ORCHESTRATION_START, f"user:{req.thread_id}", orchestration_id, {"message": req.message[:200]})
        await orchestrator.plan(orchestration_id, req.message, req.thread_id)
        state = await orchestrator.execute(orchestration_id)

        all_results = []
        for step in state.steps:
            if step.status == "completed" and step.result:
                all_results.append({
                    "step_id": step.step_id,
                    "description": step.description,
                    "agent_id": step.agent_id,
                    "result": step.result,
                    "status": step.status,
                })

        combined_reply = "\n\n---\n\n".join([
            f"### Step: {s['description']}\n**Agent**: {s['agent_id']}\n**Result**: {s['result']}"
            for s in all_results
        ]) if all_results else "任务已完成"

        write_audit(AuditAction.ORCHESTRATION_COMPLETE, f"user:{req.thread_id}", orchestration_id, {"step_count": len(state.steps)})

        return {
            "status": "success",
            "reply": combined_reply,
            "trace_id": tid,
            "route": "orchestrator",
            "classification": {
                "complexity": classification.complexity,
                "confidence": classification.confidence,
                "reason": classification.reason,
                "estimated_steps": classification.estimated_steps,
                "keywords_found": classification.keywords_found,
            },
            "orchestration_id": orchestration_id,
            "steps": [
                {
                    "step_id": s.step_id,
                    "agent_id": s.agent_id,
                    "description": s.description,
                    "status": s.status,
                    "result": s.result,
                }
                for s in state.steps
            ],
            "elapsed_sec": round(time.time() - start, 2),
        }

    # Direct agent execution
    result = agent.run(req.message, thread_id=req.thread_id)
    elapsed = time.time() - start

    if result["status"] == "error":
        return {
            "status": "error",
            "reply": result.get("error", "Unknown error"),
            "trace_id": tid,
            "route": "direct",
            "classification": {
                "complexity": classification.complexity,
                "confidence": classification.confidence,
                "reason": classification.reason,
                "estimated_steps": classification.estimated_steps,
                "keywords_found": classification.keywords_found,
            },
            "elapsed_sec": round(elapsed, 2),
        }

    graph_result = result["result"]
    messages_raw = graph_result.get("messages", [])

    from src.agent.agent import _deduplicate_messages
    messages_raw = _deduplicate_messages(messages_raw)
    messages = [_extract_msg(m) for m in messages_raw]

    tool_calls_list = []
    bus = get_event_bus()
    for m in messages:
        if m.get("tool_calls"):
            for tc in m["tool_calls"]:
                tool_calls_list.append(tc)
                await bus.publish(ExecutionEvent(
                    event_type="skill_trigger",
                    data={"tool_name": tc.get("name", "unknown"), "thread_id": req.thread_id, "trace_id": tid},
                ))
        if m.get("role") == "tool":
            tool_calls_list.append({
                "name": "tool_result",
                "result": m.get("content", ""),
            })

    reply = ""
    for m in reversed(messages_raw):
        role = _get_role(m)
        if role == "assistant":
            reply = _get_content(m)
            break

    metrics = agent.get_metrics()
    compression_count = graph_result.get("compression_count")

    return {
        "status": "success",
        "reply": reply,
        "messages": messages,
        "tool_calls": tool_calls_list if tool_calls_list else None,
        "metrics": metrics,
        "compression_count": compression_count,
        "trace_id": tid,
        "route": "direct",
        "classification": {
            "complexity": classification.complexity,
            "confidence": classification.confidence,
            "reason": classification.reason,
            "estimated_steps": classification.estimated_steps,
            "keywords_found": classification.keywords_found,
        },
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


@app.get("/api/v1/metrics/snapshot")
async def get_metrics_snapshot():
    """Get current metrics snapshot."""
    collector = get_metrics_collector()
    return collector.get_snapshot()


@app.get("/api/v1/metrics/counters")
async def get_metrics_counters():
    """Get counter metrics."""
    collector = get_metrics_collector()
    return {"counters": collector.get_counters()}


@app.get("/api/v1/metrics/gauges")
async def get_metrics_gauges():
    """Get gauge metrics."""
    collector = get_metrics_collector()
    return {"gauges": collector.get_gauges()}


@app.get("/api/v1/metrics/histograms")
async def get_metrics_histograms():
    """Get histogram metrics with percentiles."""
    collector = get_metrics_collector()
    return {"histograms": collector.get_histograms()}


@app.get("/api/v1/metrics/system-health")
async def get_system_health():
    """Get system health metrics."""
    collector = get_metrics_collector()
    return {
        "memory_rss_mb": collector.get_gauges().get("memory_rss_mb{}", 0),
        "memory_vms_mb": collector.get_gauges().get("memory_vms_mb{}", 0),
        "cpu_percent": collector.get_gauges().get("cpu_percent{}", 0),
        "thread_count": collector.get_gauges().get("thread_count{}", 0),
    }


@app.get("/api/v1/traces")
async def get_traces(limit: int = 100):
    """Get completed trace spans."""
    collector = get_metrics_collector()
    spans = collector.get_completed_spans()
    return {
        "traces": [
            {
                "span_id": s.span_id,
                "name": s.name,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "duration": s.end_time - s.start_time if s.end_time else None,
                "status": s.status,
                "attributes": s.attributes,
            }
            for s in spans[-limit:]
        ]
    }


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
    messages = agent.long_term.load_session_messages(thread_id, max_messages=20)
    return {"thread_id": thread_id, "messages": messages, "count": len(messages)}


@app.delete("/api/sessions/{thread_id}")
async def delete_session(thread_id: str):
    """删除指定会话"""
    global agent
    if not agent:
        return {"status": "error", "error": "Agent not initialized"}
    try:
        session_file = agent.long_term.config.memory_dir / "sessions" / f"{thread_id}.jsonl"
        if session_file.exists():
            session_file.unlink()
        agent.long_term._db_conn.execute("DELETE FROM sessions WHERE thread_id = ?", (thread_id,))
        agent.long_term._db_conn.commit()
        return {"status": "success", "thread_id": thread_id}
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/api/tools")
async def list_tools():
    tools = []
    for t in TOOLS:
        tools.append({
            "name": t.name,
            "description": t.description,
        })
    return {"tools": tools, "count": len(tools)}


@app.get("/api/registry/tools")
async def list_registry_tools():
    """返回所有已注册的 tools、skills、agents"""
    registry = get_registry()

    tools = []
    for t in TOOLS:
        tools.append({
            "name": t.name,
            "description": t.description,
            "category": "system",
        })

    skills = []
    for name, info in SKILLS_REGISTRY.items():
        skills.append({
            "name": info["name"],
            "description": info["description"],
            "use_when": info.get("use_when", ""),
            "category": "skill",
        })

    agents = []
    for agent_def in registry.list_agents():
        agents.append({
            "id": agent_def.get("id"),
            "name": agent_def.get("name"),
            "description": agent_def.get("description", ""),
            "category": "agent",
        })

    return {
        "tools": tools,
        "skills": skills,
        "agents": agents,
        "total": len(tools) + len(skills) + len(agents),
    }


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
    write_audit(AuditAction.WORKFLOW_CREATE, "user", workflow["id"], {"name": req.name, "node_count": len(req.nodes)})
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
    write_audit(AuditAction.WORKFLOW_DELETE, "user", workflow_id, {})
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
    write_audit(AuditAction.AGENT_REGISTER, "user", agent.get("id", ""), {"name": req.name})
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
    write_audit(AuditAction.AGENT_DELETE, "user", agent_id, {})
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
    """生成执行计划（使用 SupervisorManager）"""
    supervisor_mgr = getattr(app.state, "supervisor_mgr", None)
    if not supervisor_mgr:
        raise HTTPException(status=400, detail="SupervisorManager not available")

    plan = supervisor_mgr.generate_plan(req.graph_id, req.input_text)
    if not plan:
        raise HTTPException(status=400, detail="Failed to generate plan")

    return plan


class ExecutionRunRequest(BaseModel):
    graph_id: str
    input_text: str
    approved: bool = False


@app.post("/api/execution/run")
async def run_execution(req: ExecutionRunRequest):
    """执行 Graph（使用 SupervisorManager）"""
    if not req.approved:
        return {
            "status": "pending_approval",
            "message": "等待用户批准执行计划"
        }

    supervisor_mgr = getattr(app.state, "supervisor_mgr", None)
    if not supervisor_mgr:
        raise HTTPException(status=400, detail="SupervisorManager not available")

    try:
        result = await supervisor_mgr.run(
            req.graph_id, req.input_text, thread_id="default"
        )
        return {
            "execution_id": result["execution_id"],
            "status": result["status"],
            "output": result.get("output"),
        }
    except Exception as e:
        logger.error(f"[Execution] Failed: {e}")
        raise HTTPException(status=500, detail=str(e))


@app.post("/api/execution/run/stream")
async def run_execution_stream(req: ExecutionRunRequest):
    """流式执行 Graph（SSE）"""
    if not req.approved:
        return {
            "status": "pending_approval",
            "message": "等待用户批准执行计划"
        }

    supervisor_mgr = getattr(app.state, "supervisor_mgr", None)
    if not supervisor_mgr:
        raise HTTPException(status_code=400, detail="SupervisorManager not available")

    async def sse_generator():
        async for event in supervisor_mgr.stream_run(
            req.graph_id, req.input_text, thread_id="default"
        ):
            event_type = event.get("type", "message")
            data = json.dumps(event, ensure_ascii=False)
            yield f"event: {event_type}\ndata: {data}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    """获取执行状态（使用 SupervisorManager）"""
    supervisor_mgr = getattr(app.state, "supervisor_mgr", None)
    if not supervisor_mgr:
        raise HTTPException(status=400, detail="SupervisorManager not available")

    sup_state = supervisor_mgr.get_execution(execution_id)
    if not sup_state:
        raise HTTPException(status=404, detail=f"Execution not found: {execution_id}")

    return {
        "execution_id": sup_state.execution_id,
        "graph_id": sup_state.graph_id,
        "status": sup_state.status,
        "current_step": None,
        "total_llm_calls": sup_state.total_llm_calls,
        "total_cost_usd": sup_state.total_cost_usd,
        "elapsed_ms": sup_state.elapsed_ms,
        "interrupted": sup_state.interrupted,
        "can_resume": sup_state.can_resume,
        "steps": [
            {
                "step_id": i + 1,
                "agent_id": name,
                "agent_name": name,
                "status": sup_state.status,
                "llm_calls": 0,
                "tool_calls": 0,
            }
            for i, name in enumerate(sup_state.agent_names)
        ],
    }


@app.post("/api/execution/{execution_id}/interrupt")
async def interrupt_execution(execution_id: str):
    """中断执行"""
    supervisor_mgr = getattr(app.state, "supervisor_mgr", None)
    if not supervisor_mgr:
        raise HTTPException(status=400, detail="SupervisorManager not available")

    result = supervisor_mgr.interrupt(execution_id)
    if result.get("status") == "error":
        raise HTTPException(status=404, detail=result.get("error"))
    return result


@app.post("/api/execution/{execution_id}/resume")
async def resume_execution(execution_id: str):
    """恢复执行"""
    supervisor_mgr = getattr(app.state, "supervisor_mgr", None)
    if not supervisor_mgr:
        raise HTTPException(status=400, detail="SupervisorManager not available")

    result = supervisor_mgr.resume(execution_id)
    if result.get("status") == "error":
        raise HTTPException(status=404, detail=result.get("error"))
    return result


@app.get("/api/execution/current")
async def get_current_execution():
    """获取当前活跃的执行状态"""
    supervisor_mgr = getattr(app.state, "supervisor_mgr", None)
    if not supervisor_mgr:
        return {"status": "no_execution", "execution": None}

    executions = supervisor_mgr.list_executions()
    if not executions:
        return {"status": "no_execution", "execution": None}

    for exec in reversed(executions):
        if exec.get("status") == "running":
            execution_id = exec.get("execution_id")
            sup_state = supervisor_mgr.get_execution(execution_id)
            return {
                "status": "running",
                "execution": {
                    "execution_id": sup_state.execution_id,
                    "graph_id": sup_state.graph_id,
                    "status": sup_state.status,
                    "input_text": sup_state.input_text[:100] if sup_state.input_text else "",
                    "progress": {
                        "current_step": len(sup_state.agent_names),
                        "completed": sup_state.status == "completed",
                    },
                    "metrics": {
                        "total_tokens": sup_state.total_tokens,
                        "total_cost_usd": sup_state.total_cost_usd,
                        "elapsed_ms": sup_state.elapsed_ms,
                    },
                },
            }

    latest = executions[-1]
    return {
        "status": "idle",
        "execution": latest,
    }


@app.get("/api/executions")
async def list_executions():
    """列出所有执行"""
    supervisor_mgr = getattr(app.state, "supervisor_mgr", None)
    if not supervisor_mgr:
        return {"executions": []}

    executions = supervisor_mgr.list_executions()
    return {"executions": executions}


@app.get("/api/execution/{execution_id}/report")
async def get_execution_report(execution_id: str):
    """获取执行完成后的详细报告"""
    supervisor_mgr = getattr(app.state, "supervisor_mgr", None)
    if not supervisor_mgr:
        raise HTTPException(status=400, detail="SupervisorManager not available")

    sup_state = supervisor_mgr.get_execution(execution_id)
    if not sup_state:
        raise HTTPException(status=404, detail=f"Execution not found: {execution_id}")

    return {
        "execution_id": sup_state.execution_id,
        "graph_id": sup_state.graph_id,
        "status": sup_state.status,
        "input": sup_state.input_text[:100],
        "output": sup_state.output[:500] if sup_state.output else None,
        "summary": {
            "total_steps": len(sup_state.agent_names),
            "completed_steps": len(sup_state.agent_names) if sup_state.status == "completed" else 0,
            "failed_steps": 1 if sup_state.status == "failed" else 0,
            "total_llm_calls": sup_state.total_llm_calls,
            "total_tokens": sup_state.total_tokens,
            "total_cost_usd": sup_state.total_cost_usd,
            "total_duration_ms": sup_state.elapsed_ms,
        },
        "step_details": [
            {
                "step_id": i + 1,
                "agent_name": name,
                "status": sup_state.status,
                "llm_calls": 0,
                "tokens": 0,
                "cost_usd": 0,
                "duration_ms": 0,
                "result": sup_state.output[:200] if sup_state.output and i == len(sup_state.agent_names) - 1 else None,
                "error": sup_state.error if sup_state.status == "failed" else None,
            }
            for i, name in enumerate(sup_state.agent_names)
        ],
        "optimization_insights": {
            "cost_breakdown": [],
            "tool_usage": {},
            "suggestions": [],
        },
    }


@app.get("/api/execution/{execution_id}/graph")
async def get_execution_graph(execution_id: str):
    """获取执行图结构（Vue Flow 兼容格式）"""
    supervisor_mgr = getattr(app.state, "supervisor_mgr", None)
    if not supervisor_mgr:
        raise HTTPException(status=400, detail="SupervisorManager not available")

    sup_state = supervisor_mgr.get_execution(execution_id)
    if not sup_state:
        raise HTTPException(status=404, detail=f"Execution not found: {execution_id}")

    # 从注册表获取 graph 定义
    registry = get_registry()
    graph_def = registry.get_graph(sup_state.graph_id)
    if not graph_def:
        raise HTTPException(status=404, detail=f"Graph not found: {sup_state.graph_id}")

    # 构建 Vue Flow 兼容的节点和边
    nodes = []
    edges = []

    # 获取 graph 中的 agent 节点
    graph_nodes = graph_def.get("nodes", [])
    graph_edges = graph_def.get("edges", [])

    # 映射执行状态到节点
    status_map = {}
    if sup_state.status == "running":
        # 如果正在运行，当前节点是执行中的
        for i, name in enumerate(sup_state.agent_names):
            status_map[name] = "running" if i == len(sup_state.agent_names) - 1 else "completed"
    else:
        for i, name in enumerate(sup_state.agent_names):
            if sup_state.status == "completed":
                status_map[name] = "completed"
            elif sup_state.status == "failed":
                status_map[name] = "failed" if i == len(sup_state.agent_names) - 1 else "completed"

    # 创建节点
    for i, node in enumerate(graph_nodes):
        if node.get("type") != "agent":
            continue

        agent_id = node.get("agent_id") or node.get("data", {}).get("agent_id")
        agent_def = registry.get_agent(agent_id) if agent_id else None

        node_status = status_map.get(agent_id or "", "pending")
        if sup_state.status == "pending":
            node_status = "pending"

        nodes.append({
            "id": agent_id or f"agent-{i}",
            "type": "agent",
            "position": {"x": i * 250, "y": 100},
            "data": {
                "label": agent_def.get("name", node.get("data", {}).get("label", "Agent")) if agent_def else node.get("data", {}).get("label", "Agent"),
                "status": node_status,
                "agent_id": agent_id,
            },
            "style": {
                "background": "#1f2937" if node_status == "pending" else "#1a4a2a" if node_status == "completed" else "#4a1a1a" if node_status == "failed" else "#1a3a5c",
                "border": "#3fb950" if node_status == "completed" else "#f85149" if node_status == "failed" else "#58a6ff" if node_status == "running" else "#6e7681",
            },
        })

    # 创建边
    for edge in graph_edges:
        source = None
        target = None

        for node in graph_nodes:
            if node.get("id") == edge.get("source"):
                source = node.get("agent_id") or node.get("data", {}).get("agent_id")
            if node.get("id") == edge.get("target"):
                target = node.get("agent_id") or node.get("data", {}).get("agent_id")

        if source and target:
            edge_status = "animated" if status_map.get(source) == "running" else "solid"
            edges.append({
                "id": f"e-{source}-{target}",
                "source": source,
                "target": target,
                "type": "smoothstep",
                "animated": edge_status == "animated",
                "style": {
                    "stroke": "#58a6ff" if status_map.get(source) == "running" else "#3fb950" if status_map.get(source) == "completed" else "#f85149" if status_map.get(source) == "failed" else "#6e7681",
                },
            })

    # 如果没有边，按顺序生成线性边
    if not edges and len(nodes) > 1:
        for i in range(len(nodes) - 1):
            edges.append({
                "id": f"e-{nodes[i]['id']}-{nodes[i+1]['id']}",
                "source": nodes[i]["id"],
                "target": nodes[i+1]["id"],
                "type": "smoothstep",
                "animated": nodes[i+1]["data"]["status"] == "running",
                "style": {
                    "stroke": "#3fb950" if nodes[i+1]["data"]["status"] == "completed" else "#58a6ff" if nodes[i+1]["data"]["status"] == "running" else "#6e7681",
                },
            })

    return {
        "execution_id": execution_id,
        "graph_id": sup_state.graph_id,
        "status": sup_state.status,
        "nodes": nodes,
        "edges": edges,
    }


# ========== 实时事件 SSE 端点 ==========


# ========== Dynamic Orchestrator 端点 ==========

class OrchestrateRequest(BaseModel):
    message: str
    thread_id: str = "default"


class RollbackRequest(BaseModel):
    step_id: str
    reason: str = ""


class ApproveRequest(BaseModel):
    approved: bool = True


@app.post("/api/orchestrate")
async def start_orchestration(req: OrchestrateRequest):
    """启动动态编排：LLM 分析任务 → 生成 DAG → 异步执行"""
    import asyncio as _asyncio
    orch: DynamicOrchestrator = app.state.dynamic_orchestrator
    orchestration_id = f"orch-{uuid.uuid4().hex[:8]}"

    async def _run():
        try:
            await orch.plan(orchestration_id, req.message, req.thread_id)
            await orch.execute(orchestration_id)
        except Exception as e:
            logger.error(f"[Orchestrate] Background execution failed: {e}", exc_info=True)
            state = get_orchestration(orchestration_id)
            if state:
                state.status = "failed"
                state.updated_at = datetime.now().isoformat()

    _asyncio.create_task(_run())
    return {
        "orchestration_id": orchestration_id,
        "status": "planning",
        "thread_id": req.thread_id,
    }


@app.get("/api/orchestrate/{orchestration_id}/state")
async def get_orchestration_state(orchestration_id: str):
    """获取编排状态"""
    state = get_orchestration(orchestration_id)
    if not state:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    return {
        "orchestration_id": state.orchestration_id,
        "thread_id": state.thread_id,
        "input_text": state.input_text,
        "plan_summary": state.plan_summary,
        "steps": [
            {
                "step_id": s.step_id,
                "agent_id": s.agent_id,
                "agent_name": s.agent_name,
                "description": s.description,
                "depends_on": s.depends_on,
                "status": s.status,
                "result": s.result,
                "error": s.error,
                "started_at": s.started_at,
                "completed_at": s.completed_at,
                "duration_ms": s.duration_ms,
            }
            for s in state.steps
        ],
        "status": state.status,
        "current_step_id": state.current_step_id,
        "final_output": state.final_output,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "replan_count": state.replan_count,
    }


@app.post("/api/orchestrate/{orchestration_id}/rollback")
async def rollback_orchestration(orchestration_id: str, req: RollbackRequest):
    """回退到指定步骤并重新执行"""
    orch: DynamicOrchestrator = app.state.dynamic_orchestrator
    state = get_orchestration(orchestration_id)
    if not state:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    try:
        result = await orch.rollback(orchestration_id, req.step_id, req.reason)
        downstream = orch._get_downstream_steps(result.steps, req.step_id)
        return {
            "orchestration_id": orchestration_id,
            "status": "running",
            "rolled_back_to": req.step_id,
            "steps_reset": list(downstream),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/orchestrate/{orchestration_id}/approve")
async def approve_orchestration_replan(orchestration_id: str, req: ApproveRequest):
    """批准或拒绝重规划"""
    orch: DynamicOrchestrator = app.state.dynamic_orchestrator
    state = get_orchestration(orchestration_id)
    if not state:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    await orch.approve_replan(orchestration_id, req.approved)
    return {
        "orchestration_id": orchestration_id,
        "approved": req.approved,
    }


class StepApproveRequest(BaseModel):
    step_id: str
    approved: bool = True


@app.post("/api/orchestrate/{orchestration_id}/step/approve")
async def approve_orchestration_step(
    orchestration_id: str, req: StepApproveRequest
):
    """批准或拒绝步骤继续执行"""
    orch: DynamicOrchestrator = app.state.dynamic_orchestrator
    state = get_orchestration(orchestration_id)
    if not state:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    await orch.approve_step(orchestration_id, req.step_id, req.approved)
    return {
        "orchestration_id": orchestration_id,
        "step_id": req.step_id,
        "approved": req.approved,
    }


@app.get("/api/orchestrations")
async def list_all_orchestrations():
    """列出所有编排"""
    return {"orchestrations": list_orchestrations(), "count": len(list_orchestrations())}


@app.post("/api/orchestrate/{orchestration_id}/resume")
async def resume_orchestration(orchestration_id: str):
    """恢复并继续执行工作流"""
    state = get_orchestration(orchestration_id)
    if not state:
        raise HTTPException(status_code=404, detail="Orchestration not found")

    if state.status not in ("planning", "running"):
        return {
            "status": "error",
            "message": f"Cannot resume: current status is {state.status}",
        }

    orch: DynamicOrchestrator = app.state.dynamic_orchestrator
    result = await orch.execute(orchestration_id)
    return {
        "orchestration_id": orchestration_id,
        "status": result.status,
        "steps": len(result.steps),
    }


@app.get("/api/orchestrations/checkpoints")
async def list_checkpointed_orchestrations():
    """列出检查点中的工作流"""
    from src.agent.orchestrator_checkpoint import get_checkpoint
    checkpoint = get_checkpoint()
    return {"orchestrations": checkpoint.list_all(), "count": len(checkpoint.list_all())}

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
