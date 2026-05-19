# TASK: ReAct Agent Migration — 自定义 StateGraph → 标准 LangGraph ReAct Agent

## Objective

将当前 `src/agent/agent.py` 中自定义的 9 节点 StateGraph 迁移到标准的 LangGraph `create_react_agent` 模式。新实现在 `src/rect-agent/` 下独立开发，不修改现有代码。

## Architecture (Target)

```
create_react_agent(
    model=model,
    tools=TOOLS,
    prompt=dynamic_system_prompt,         # init + profile + SOP
    pre_model_hook=pre_llm_pipeline,       # rate_limiter + breaker + compress + memory
    post_model_hook=post_llm_pipeline,     # cleanup + save
    state_schema=RectAgentState,
    checkpointer=SqliteSaver(conn),
    interrupt_before=["tools"],            # HITL
)
```

### Directory Structure

```
src/rect-agent/
├── __init__.py                  # create_rect_agent() 工厂
├── agent.py                     # RectAgent 类
├── graph.py                     # LangGraph Studio 兼容
├── state.py                     # RectAgentState (add_messages reducer)
├── config.py                    # 配置（复用 src.agent.config）
├── tools/
│   ├── __init__.py              # 重新导出 TOOLS
│   └── wrapper.py               # ToolNode + wrap_tool_call
├── hooks/
│   ├── __init__.py
│   ├── prompt.py                # 动态 system prompt
│   ├── pre_model.py             # pre_model_hook
│   └── post_model.py            # post_model_hook
└── middleware/
    ├── __init__.py
    └── tool_wrapper.py           # 重试/熔断/幂等/预算中间件
```

### Reuse Strategy

| Source Module | Reuse Method |
|--------------|-------------|
| `src.agent.tools.TOOLS` | Direct import — 12 tools unchanged |
| `src.agent.config` | Direct import — AgentConfig, ShortTermConfig, LongTermConfig |
| `src.agent.rate_limiter` | Direct import — RateLimiter, CircuitBreaker, ToolCircuitBreaker |
| `src.agent.context.long_term` | Direct import — LongTermManager |
| `src.agent.context.compression` | Direct import — ContextCompressor |
| `src.agent.schemas.agent_protocol` | Direct import — ErrorEnvelope, ERROR_CODES |
| `src.agent.audit_logger` | Direct import |
| `src.agent.state.AgentState` | Extend in state.py (switch to add_messages) |

## Progress

### Done
- TASK document created
- Full research on create_react_agent API, ToolNode, hooks, subgraph composition
- Migration strategy planned: 5 phases + 6 implementation phases

### In Progress
- (none)

### Next Steps
1. Phase 0: Create directory structure + state.py + import validation
2. Phase 1: tools/wrapper.py — ToolNode + wrap_tool_call
3. Phase 2: hooks/prompt.py — dynamic prompt
4. Phase 3: hooks/pre_model.py + hooks/post_model.py
5. Phase 4: agent.py — assemble create_react_agent
6. Phase 5: graph.py — Studio compatibility
7. Phase 6: Tests + verification

## Key Decisions

1. **Incremental, not big-bang**: Build new package alongside old code, then switch entry point
2. **`wrap_tool_call` over manual tool loop**: ToolNode handles parallel execution; retry/breaker/cache in callback
3. **`llm_input_messages` for pre_model_hook**: Avoid persisting intermediate message state into checkpoint
4. **No modification to `src/agent/`**: Zero risk to existing production code
5. **Shared infrastructure via import**: Reuse LongTermManager, ContextCompressor, rate_limiter, ErrorEnvelope — no duplication
6. **state.py switch to `add_messages`**: LangGraph standard reducer, required by create_react_agent
7. **`interrupt_before` replaces manual HITL node**: LangGraph native interrupt, no async event loop hack

## Key Differences from Current Architecture

| Aspect | Current (src/agent) | Target (src/rect-agent) |
|--------|-------------------|------------------------|
| Graph construction | Manual 9-node StateGraph | create_react_agent + hooks |
| Tool execution | Manual loop `for t in TOOLS` | ToolNode + wrap_tool_call |
| Message reducer | smart_message_reducer (custom) | add_messages (LangGraph std) |
| HITL | Dedicated _node_human_review | interrupt_before=["tools"] |
| Compression | Dedicated _node_compress node | pre_model_hook (before LLM) |
| Memory retrieval | Inline in _node_think | pre_model_hook (before LLM) |
| Profile/SOP injection | Dedicated nodes | prompt callable |
| LLM breaker/rate-limit | Inline in _node_think | pre_model_hook |
| Cleanup + save | Dedicated nodes | post_model_hook |
| Studio graph | 8-node simplified copy | create_react_agent with overrides |

## Risk Register

| Risk | Mitigation |
|------|-----------|
| add_messages reducer behavior differs from smart_message_reducer | Phase 0: verify dedup logic matches in unit test |
| ToolNode handle_tool_errors conflicts with custom error classification | Set handle_tool_errors=False, handle in wrap_tool_call |
| pre_model_hook message chain affects checkpoint integrity | Use llm_input_messages for transient modifications |
| interrupt_before async compatibility with existing code | New package, no compatibility needed |
| Long running tests (>2min) | Keep mock tests fast, real API tests optional |
