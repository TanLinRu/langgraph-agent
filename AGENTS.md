# AGENTS.md

## Quick Start

```bash
uv pip install -e .          # or pip install -e .
cp .env.example .env         # fill in OPENAI_API_KEY

python -m src.agent.main --input "write a quick sort"
python -m src.agent.main --interactive
python -m src.agent.main --archive   # run session archive cleanup
python -m src.agent.main --acp      # run ACP server (stdio JSON-RPC)
```

## ACP Server

Run as ACP server for editor integration (Zed, JetBrains, Neovim):

```bash
# 启动方式：
python server.py              # 默认：HTTP + ACP 同时运行
python server.py --http      # 仅 HTTP
python server.py --acp      # 仅 ACP
python server.py --both     # HTTP + ACP 同时运行
```

## Chat UI (Web)

Visual chat interface with request details per turn.

```bash
# Terminal 1: API server
python server.py

# Terminal 2: Frontend
cd ui && npm install && npm run dev
```

Open `http://localhost:3000` in browser.
Each reply has an **expand detail** button showing full messages, tool calls, and metrics.

## Key Facts

- **Python >= 3.11** required
- **Install**: `pip install -e ".[dev]"` for dev extras (pytest, ruff, mypy)
- **Tests**: `pytest tests/` — 70 tests; fixtures in `tests/conftest.py` (mock_config, mock_llm, mock_env_vars, agent); run single file: `pytest tests/test_compression.py -v`; run by name: `pytest -k "test_name"`
- **LangGraph Studio**: `langgraph dev` loads graph from `src/agent/graph.py`
- **No CI / pre-commit** configured
- **Lint**: `ruff check . --fix` (line-length 100, ignores E501)
- **Type check**: `mypy .` (strict mode)
- **Order**: lint → typecheck → test

## Environment Variables

| Variable | Source | Notes |
|---|---|---|
| `OPENAI_API_KEY` | `.env` or shell | Required, loaded directly (not via AGENT_ prefix) |
| `OPENAI_BASE_URL` | `.env` or shell | Defaults to `https://api.openai.com/v1` |
| `AGENT_MODEL` | `.env` | Default `openai:gpt-4` |
| `AGENT_MEMORY_DIR` | `.env` | Default `./memory` |
| `AGENT_SESSION_TTL_DAYS` | `.env` | Default `7` |

**Critical**: Only `OPENAI_API_KEY` and `OPENAI_BASE_URL` are loaded directly. All other settings use `AGENT_` prefix via pydantic-settings.

## Architecture

LangGraph state machine: **init → think → (execute → compress → save) → [should_continue] → think/END** (loop).

- `src/agent/graph.py` — LangGraph StateGraph; entry for `langgraph dev`
- `src/agent/agent.py` — Agent class + `create_agent()` factory
- `src/agent/orchestrator.py` — multi-agent orchestration
- `src/agent/registry.py` — agent/graph registry (includes OpenCode with `execution_mode: "acp"`)
- `src/agent/opencode_agent.py` — OpenCode wrapper (calls CLI externally)
- `src/agent/acp_server.py` — ACP server (JSON-RPC over stdio)
- `src/agent/main.py` — CLI entrypoint (`python -m src.agent.main`)
- `src/agent/config.py` — pydantic-settings config (env file: `.env`, prefix: `AGENT_`)
- `src/agent/state.py` — AgentState TypedDict
- `src/agent/context/` — long_term (SQLite+ChromaDB), compression (70% threshold, keep 5), initialization (resume), archive (7-day TTL)
- `src/agent/tools/` — tool registry (`TOOLS` list in `__init__.py`)
- `src/agent/skills/` — skill system (`SKILLS_INDEX` in `__init__.py`)
- `src/agent/prompts/` — system prompts (`SYSTEM_PROMPT` in `__init__.py`)
- `workflows.json` — predefined multi-step workflow definitions
- `ui/` — Vue 3 + Vite + TypeScript + Vue Flow chat frontend
- `server.py` — FastAPI backend (HTTP + optional ACP)

## Context Design

- **Compression trigger**: 70% token threshold (128K max)
- **Keep recent**: last 5 user/assistant messages + last 5 tool results
- **Archive TTL**: 7 days
- **Storage**: SQLite metadata + JSONL incremental deltas + ChromaDB vectors
- **Multi-turn**: `run()` appends to checkpointer state; system prompt added once at init

## Multi-Turn & Resume Notes

- `_node_init` runs only on first `run()` — system prompt added once per session
- Subsequent `run()` calls resume from MemorySaver checkpointer
- JSONL stores **delta** messages per turn (not full snapshot) to avoid duplication
- Cost estimation in `get_metrics()` uses `MODEL_COSTS` dict (supports gpt-4, gpt-4o, gpt-4o-mini, gpt-3.5-turbo)
- Loop exits when: LLM replies directly (no tool_calls) OR compression count >= 5

## Docs

- `docs/architecture/design-spec.md` — architecture spec
- `docs/langchain-langgraph-deepagents-guide.md` — technical guide
- `docs/agent-architecture-notes.md` — agent architecture principles
- `docs/task-plan-product-operations.md` — 产品/运营场景 + Chat UI 指标增强实施计划
