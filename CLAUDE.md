# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A production-grade AI agent built on LangGraph with multi-agent orchestration, OpenCode integration (as an external execution engine via ACP/CLI), context compression, long-term memory (SQLite + ChromaDB), and a Vue 3 chat UI.

## Commands

```bash
# Install
pip install -e .              # or uv pip install -e .
pip install -e ".[dev]"       # dev extras: pytest, ruff, mypy

# Run
python -m src.agent.main --input "write a quick sort"
python -m src.agent.main --interactive

# Server (FastAPI backend + optional ACP)
python server.py              # HTTP + ACP simultaneously
python server.py --http       # HTTP only
python server.py --acp        # ACP only (stdio JSON-RPC)

# Dynamic Orchestrator API
curl -X POST http://localhost:8000/api/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"message": "analyze this codebase", "thread_id": "default"}'
curl http://localhost:8000/api/orchestrate/{id}/state
curl -X POST http://localhost:8000/api/orchestrate/{id}/rollback \
  -H "Content-Type: application/json" -d '{"step_id": "step-1"}'
curl -X POST http://localhost:8000/api/orchestrate/{id}/approve -d '{"approved": true}'

# Frontend
cd ui && npm install && npm run dev   # Vite dev server at localhost:3000

# Quality (in this order)
ruff check . --fix            # lint (line-length 100, ignores E501)
mypy .                        # strict type checking
pytest tests/                 # 42+ tests
pytest tests/test_compression.py -v   # run single test file
pytest -k "test_name"                  # run single test by name

# LangGraph Studio
langgraph dev                 # loads graph from src/agent/graph.py
```

## Architecture

**LangGraph state machine** with this loop:
`init → think → (execute → compress → save) → [should_continue] → think/END`

### Core modules (`src/agent/`)

- `graph.py` — LangGraph StateGraph definition; entry point for `langgraph dev` Studio
- `agent.py` — `Agent` class + `create_agent()` factory; the main agent with tool calling, compression, and checkpointing via MemorySaver
- `supervisor.py` — `SupervisorManager` using `langgraph_supervisor.create_supervisor` for multi-agent graphs defined in the registry
- `orchestrator_v2.py` — `DynamicOrchestrator`; LLM-driven task decomposition into a DAG, with execution, rollback, and adaptive replanning. Stores state in `_orchestrations` dict.
- `orchestrator_checkpoint.py` — checkpoint persistence for DynamicOrchestrator; saves/loads state to JSON files in `memory/`
- `sub_agent_factory.py` — `build_sub_agent()` converts registry agent definitions into `create_react_agent` instances; handles both `sync` mode (LLM+tools) and `acp` mode (external CLI as a single tool)
- `registry.py` — `AgentRegistry` CRUD for agents and graphs stored as JSON in `memory/`
- `state.py` — `AgentState` TypedDict (with `token_usage` Annotated dict + `token_budget_reducer`), `SubAgentState`, plus `OrchestratorStep` and `OrchestratorState` dataclasses
- `event_bus.py` — `EventBus` async pub/sub; `publish_workflow_event()` helper for orchestrator SSE events
- `event_callback.py` — `EventBusCallbackHandler` bridges LangGraph callbacks → EventBus
- `opencode_agent.py` — OpenCode agent wrapper (calls OpenCode CLI externally)
- `opencode_client.py` / `acp_client.py` / `acp_stdio_client.py` — ACP protocol clients
- `config.py` — pydantic-settings config; env prefix `AGENT_`, reads from `.env`
- `sop_state.py` — SOP workflow state persistence (save/load/delete)
- `main.py` — CLI entrypoint (`python -m src.agent.main`)
- `human_in_loop.py` — human approval for step-level and replanning gates
- `rate_limiter.py` / `retry_handler.py` / `graceful_degradation.py` — resilience utilities
- `task_classifier.py` — classifies task complexity to decide orchestration strategy

### Context management (`src/agent/context/`)

- `compression.py` — LLM-based summary compression with Hot Zone; triggers at 70% token threshold (128K max), keeps last 5 messages + Hot Zone tool results
- `tool_result_store.py` — `ToolResultStore`: LRU + heat-based dual-factor eviction for tool results (Hot Zone size 3-5)
- `conflict_resolver.py` — `ConflictType` enum + `resolve_memory_conflict()`: handles contradiction/evolution/specification memory conflicts with history tracking
- `retrieval_trigger.py` — `RetrievalTrigger`: multi-dimensional retrieval triggers (token >40% OR planning/reflection/comparison task type OR semantic similarity >0.7)
- `long_term.py` — SQLite metadata + ChromaDB vectors; supports 4-tuple namespace isolation `(tenant_id, org_id, user_id, memory_type)`; `get_namespace()` helper
- `initialization.py` — session resume on startup
- `archive.py` — 7-day TTL session archival

### Other subsystems

- `tools/__init__.py` — tool registry (`TOOLS` list)
- `skills/__init__.py` — skill system (`SKILLS_INDEX`, `SKILLS_REGISTRY`)
- `prompts/system_prompt.py` — system prompt (`SYSTEM_PROMPT`)
- `cli/` — CLI dispatcher for external tool execution (OpenCode integration)

### Server (`server.py`)

FastAPI backend serving the Vue chat UI. Key endpoint groups:
- `/chat` — single-agent chat
- `/api/orchestrate` — DynamicOrchestrator (plan, execute, rollback, approve)
- `/api/execution/*` — SupervisorManager execution (plan, run, stream, state)
- `/api/agents`, `/api/agent-graphs` — registry CRUD
- `/api/workflows` — workflow JSON CRUD
- `/api/events/stream` — SSE via EventBus
- `/api/cli/*` — external CLI dispatch

### Frontend (`ui/src/`)

Vue 3 + Vite + TypeScript + Pinia + Vue Flow. No router — tab navigation via `useAppStore`. 6 tabs: Chat, Agents, Skills, Workflows, CLI, SOP.

- `components/ChatTab.vue` — 4-column layout: session sidebar | chat | WorkflowSidebar | DashboardSidebar
- `components/WorkflowSidebar.vue` — collapsible (400px) Vue Flow DAG for DynamicOrchestrator; step detail panel + replan approval
- `components/ExecutionFlow.vue` — read-only Vue Flow for supervisor execution graphs
- `components/dashboard/DashboardSidebar.vue` — collapsible (360px) real-time SSE observation panel
- `components/nodes/` — custom Vue Flow node types (`agent`, `trigger`, `condition`, `loop`, `output`, `orchestrator`)
- `stores/` — 8 Pinia stores: `app`, `chat`, `agents`, `workflows`, `skills`, `cli`, `sop`, `dashboard`, `orchestrator`

### Workflows (`workflows.json`)

Predefined multi-step workflow definitions (nodes of type `skill` or `dispatch`, connected by edges). Used by the SupervisorManager.

## Key Design Decisions

- **Two-tier agent system**: Single-agent (`Agent.run()` via `/chat`) vs multi-agent (`DynamicOrchestrator` via `/api/orchestrate` or `SupervisorManager` via `/api/execution/*`). DynamicOrchestrator generates DAGs dynamically via LLM; SupervisorManager executes pre-defined registry graphs.
- **Skills are prompts, not agents**: Skills in `SKILLS_REGISTRY` are system prompt templates concatenated into the system message at init time. The LLM self-selects which skill guidance to follow.
- **Execution modes**: Sub-agents can be `sync` (direct LLM + tools via `create_react_agent`) or `acp` (external CLI wrapped as a single tool).
- **Config**: All settings via `AGENT_` env prefix through pydantic-settings. `OPENAI_API_KEY` and `OPENAI_BASE_URL` are loaded directly (no prefix).
- **State messages**: Uses `Annotated[list, operator.add]` for LangGraph message accumulation.
- **Compression**: LLM summarizes old messages when context hits 70% of 128K tokens; keeps last 5 user/assistant + last 5 tool results.
- **Multi-turn resume**: `_node_init` runs only on first `run()`; subsequent calls resume from MemorySaver checkpointer. JSONL stores delta messages per turn.
- **Event-driven observability**: `EventBus` + `EventBusCallbackHandler` provide real-time SSE streaming of agent lifecycle events to the frontend.
- **Cost estimation**: `MODEL_COSTS` dict in agent.py supports gpt-4, gpt-4o, gpt-4o-mini, gpt-3.5-turbo.
- **No CI/pre-commit** configured.

## Environment Variables

| Variable | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | (required) | Loaded directly, not via AGENT_ prefix |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Loaded directly |
| `AGENT_MODEL` | `openai:gpt-4` | |
| `AGENT_MEMORY_DIR` | `./memory` | |
| `AGENT_SESSION_TTL_DAYS` | `7` | |

## Conventions

- Python >= 3.11 required
- Ruff for linting (line-length 100, select E/F/I/N/W/UP, ignore E501)
- mypy strict mode
- pytest for tests; fixtures in `tests/conftest.py` provide mock_config, mock_llm, mock_env_vars, and agent instances
