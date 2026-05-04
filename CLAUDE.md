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
- `orchestrator.py` — multi-agent orchestration (dispatches to registered agents)
- `registry.py` — agent/graph registry; stores agent definitions including OpenCode agents with `execution_mode: "acp"`
- `opencode_agent.py` — OpenCode agent wrapper (calls OpenCode CLI externally)
- `opencode_client.py` / `acp_client.py` / `acp_stdio_client.py` — ACP protocol clients
- `config.py` — pydantic-settings config; env prefix `AGENT_`, reads from `.env`
- `state.py` — `AgentState` TypedDict (messages, thread_id, task_status, compression_count, sop_name/step)
- `sop_state.py` — SOP workflow state persistence (save/load/delete)
- `main.py` — CLI entrypoint (`python -m src.agent.main`)

### Context management (`src/agent/context/`)

- `compression.py` — LLM-based summary compression; triggers at 70% token threshold (128K max), keeps last 5 messages
- `long_term.py` — SQLite metadata + ChromaDB vectors for long-term memory
- `initialization.py` — session resume on startup
- `archive.py` — 7-day TTL session archival

### Other subsystems

- `tools/__init__.py` — tool registry (`TOOLS` list)
- `skills/__init__.py` — skill system (`SKILLS_INDEX`, `SKILLS_REGISTRY`)
- `prompts/system_prompt.py` — system prompt (`SYSTEM_PROMPT`)
- `cli/` — CLI dispatcher for external tool execution (OpenCode integration)

### Server (`server.py`)

FastAPI backend serving the Vue chat UI. Endpoints for chat, streaming, skill management, workflow execution, and SOP state management. Supports CORS for frontend dev.

### Frontend (`ui/`)

Vue 3 + Vite + TypeScript + Vue Flow (for visual workflow graph). Chat interface with expandable request details per turn.

### Workflows (`workflows.json`)

Predefined multi-step workflow definitions (nodes of type `skill` or `dispatch`, connected by edges). Used by the workflow execution engine.

## Key Design Decisions

- **Config**: All settings via `AGENT_` env prefix through pydantic-settings. `OPENAI_API_KEY` and `OPENAI_BASE_URL` are loaded directly (no prefix).
- **State messages**: Uses `Annotated[list, operator.add]` for LangGraph message accumulation.
- **Compression**: LLM summarizes old messages when context hits 70% of 128K tokens; keeps last 5 user/assistant + last 5 tool results.
- **Multi-turn resume**: `_node_init` runs only on first `run()`; subsequent calls resume from MemorySaver checkpointer. JSONL stores delta messages per turn.
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
