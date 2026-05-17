# TASK: Doc-Alignment — Align Implementation with agent-flow-design.md

## Objective
Close the 5 gaps identified in the architecture audit against `agent-flow-design.md`:

1. **Standardized AgentOutput schema** — always return `AgentOutput` TypedDict from `run()`
2. **Retry mechanism** — wire `retry_with_backoff` into `_node_think` and `_node_execute`
3. **Circuit breaker** — wire `rate_limiter` + `tool_breakers` into graph nodes
4. **Centralized error classification** — `_node_think`/`_node_execute` must use central `ERROR_CODES`
5. **Run test suite** — verify no regressions

## Progress

### Done
- Audit of 5 gaps against design doc
- `TASK-doc-alignment.md` created

### In Progress
- Fix `run()` return schema — always return `AgentOutput`

### Next Steps
1. `run()` → `AgentOutput` schema, fix `steps_executed`
2. `_node_think`: retry loop + circuit breaker + centralized error codes
3. `_node_execute`: retry per tool + tool circuit breaker
4. Full test suite

## Key Decisions
- Use existing `AgentOutput` TypedDict from `schemas/agent_protocol.py`
- Use `retry_with_backoff` decorator from `retry_handler.py` for LLM/tool retry
- Use `get_rate_limiter()` / `get_tool_breakers()` singleton from `rate_limiter.py`
- Retry on `recoverable` errors only; `fatal` errors skip retry immediately
