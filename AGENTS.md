# AGENTS.md

## Required Workflow

**每个新需求完成后，必须同步更新 README.md**
- 包含架构图、业务架构图、数据流图
- 更新 API 端点列表
- 更新项目结构

**任务文档规范**
- 每次确认任务后，必须生成 `TASK-{task_name}.md` 文档
- 文档放在 `docs/tasks/` 目录下
- 文档内容应包含：任务目标、当前进度、下一步计划、关键决策点
- 便于后续断点续传，避免重复劳动

## Quick Start

```bash
pip install -e .
pip install -e ".[dev]"           # pytest, ruff, mypy
pip install -e ".[automation]"     # optional: pyautogui, Pillow, pywin32
pip install -e ".[browser]"       # optional: browser-use (has dependency conflicts)
cp .env.example .env               # fill in OPENAI_API_KEY

python -m src.agent.main --input "write a quick sort"
python -m src.agent.main --interactive
python -m src.agent.main --archive   # run session archive cleanup
python -m src.agent.main --acp      # run ACP server (stdio JSON-RPC)
```

## Key Commands

| Command | Purpose |
|---------|---------|
| `python -m pytest tests/ -v` | Run all tests |
| `python -m pytest tests/test_file.py -v` | Run single file |
| `python -m pytest -k "name"` | Run by test name pattern |
| `ruff check . --fix` | Lint (line-length 100, ignores E501) |
| `mypy .` | Type check (strict mode) |
| `langgraph dev` | LangGraph Studio (loads `src/agent/graph.py`) |
| `python server.py` | Start HTTP + ACP server |
| `python server.py --http` | HTTP only |
| `python server.py --acp` | ACP only |

**Order**: lint → typecheck → test

## Environment Variables

| Variable | Source | Notes |
|---|---|---|
| `OPENAI_API_KEY` | `.env` or shell | Required, loaded directly (no prefix) |
| `OPENAI_BASE_URL` | `.env` or shell | Defaults to `https://api.openai.com/v1` |
| `AGENT_MODEL` | `.env` | Default `openai:gpt-4` |
| `AGENT_MEMORY_DIR` | `.env` | Default `./memory` |
| `AGENT_SESSION_TTL_DAYS` | `.env` | Default `7` |

**Critical**: Only `OPENAI_API_KEY` and `OPENAI_BASE_URL` are loaded directly. All other settings use `AGENT_` prefix via pydantic-settings.

## ⚠️ Critical Inconsistency

- `graph.py` (LangGraph Studio): **no checkpointer** → sessions not persisted
- `agent.py` (production): **SqliteSaver** → sessions persisted
- Both use different graph structures; resume behavior differs between modes

## Architecture

LangGraph state machine: **init → sop_resume → think → execute → compress → save** (loop).

### Core Modules

- `src/agent/graph.py` — LangGraph StateGraph; entry for `langgraph dev` (no checkpointer)
- `src/agent/agent.py` — Agent class + `create_agent()` factory (with SqliteSaver)
- `src/agent/orchestrator.py` — MultiAgentOrchestrator (legacy)
- `src/agent/orchestrator_v2.py` — DynamicOrchestrator with per-step approval
- `src/agent/registry.py` — agent/graph registry (includes OpenCode with `execution_mode: "acp"`)
- `src/agent/opencode_agent.py` — OpenCode wrapper (calls CLI externally)
- `src/agent/acp_server.py` — ACP server (JSON-RPC over stdio)
- `src/agent/main.py` — CLI entrypoint (`python -m src.agent.main`)
- `src/agent/config.py` — pydantic-settings config (env file: `.env`, prefix: `AGENT_`)
- `src/agent/state.py` — AgentState TypedDict + OrchestratorState
- `src/agent/context/` — long_term (SQLite+ChromaDB), compression (70% threshold, keep 5), initialization (resume), archive (7-day TTL)
- `src/agent/tools/` — tool registry (`TOOLS` list in `__init__.py`)
- `src/agent/skills/` — skill system (`SKILLS_INDEX` in `__init__.py`)
- `src/agent/prompts/` — system prompts (`SYSTEM_PROMPT` in `__init__.py`)
- `workflows.json` — predefined multi-step workflow definitions
- `ui/` — Vue 3 + Vite + TypeScript + Vue Flow chat frontend
- `server.py` — FastAPI backend (HTTP + optional ACP)

### Production Reliability

- `src/agent/rate_limiter.py` — RPM + cost circuit breaker
- `src/agent/retry_handler.py` — exponential backoff retry decorator
- `src/agent/graceful_degradation.py` — fallback handling and health checking
- `src/agent/human_in_loop.py` — approval gates for critical operations
- `src/agent/task_classifier.py` — complexity-based task routing
- `src/agent/orchestrator_checkpoint.py` — workflow state persistence

### PC Automation (optional, `pip install -e ".[automation]"`)

- `src/agent/automation/vision.py` — screenshot capture via Pillow
- `src/agent/automation/desktop.py` — pyautogui mouse/keyboard control
- `src/agent/automation/browser.py` — browser-use (fallback if not installed)
- `src/agent/sandbox/filesystem.py` — path allowlist + network restriction (software-level only, not container-grade)

## Context Design

### 4-Layer Memory Model
- **L1 Working Memory**: State.messages (in-memory)
- **L2 Session**: SqliteSaver + JSONL deltas (`./memory/sessions/`)
- **L3 Cross-session**: Store + ChromaDB (`./memory/chroma/`)
- **L4 Organizational**: external services

### Compression
- **Trigger**: 70% token threshold (128K max)
- **Keep recent**: last 5 user/assistant messages + last 5 tool results
- **Hot Zone**: LRU + 热度双因素淘汰 for tool results
- **Structured format**: `CompressedTurn` with user_intent, tool_actions, key_facts
- Token counting: tiktoken (cl100k_base)

### Storage Locations
- `./memory/sessions.db` — SQLite metadata
- `./memory/sessions/{thread_id}.jsonl` — message deltas (not full snapshots)
- `./memory/memory/MEMORY.md` — semantic memory
- `./memory/chroma/` — ChromaDB vectors
- `./memory/archive/` — 7-day TTL archives

## Multi-Turn & Resume Notes

- `_node_init` runs only on first `run()` — system prompt added once per session
- Subsequent `run()` calls resume from SqliteSaver checkpointer
- JSONL stores **delta** messages per turn (not full snapshot) to avoid duplication
- `_deduplicate_messages()` prevents duplicate system/user messages on resume
- Cost estimation in `get_metrics()` uses `MODEL_COSTS` dict (supports gpt-4, gpt-4o, gpt-4o-mini, gpt-3.5-turbo)
- Loop exits when: LLM replies directly (no tool_calls) OR compression_count >= 5

## Tool Execution

Tools are **manually iterated in `_node_execute`** (not LangGraph native `@tool` binding).

11 built-in tools: `execute_code`, `read_file`, `write_file`, `list_directory`, `data_processor`, `search_files`, `dispatch_to_cli`, `dispatch_via_acp`, `list_clis`, `list_serves`, `stop_serve_tool`

## Dependency Notes

- Core: `langchain`, `langgraph`, `langchain-openai`, `pydantic>=2.0`
- Optional `[dev]`: pytest, ruff, mypy
- Optional `[automation]`: pyautogui, Pillow, pywin32
- Optional `[browser]`: browser-use (has version conflicts with langchain deps — uses try/except fallback)

## Docs

- `README.md` — project overview (architecture/business/data flow diagrams)
- `docs/architecture/design-spec.md` — architecture spec
- `docs/langchain-langgraph-deepagents-guide.md` — technical guide
- `docs/agent-architecture-notes.md` — agent architecture principles
- `docs/context_design.md` — 4-layer memory model detail
- `docs/task-plan-product-operations.md` — product/ops implementation plan
- `docs/metrics-observability-plan.md` — metrics & observability plan
