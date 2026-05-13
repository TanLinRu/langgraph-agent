# TASK: Context Design Gap Fix

**Task**: 修复 `context_design.md` 与实际实现的差距  
**Created**: 2025-05-13  
**Status**: In Progress

---

## 背景

根据 `docs/context_design.md` 设计与实际实现的对比分析，发现以下关键差距需要修复。

---

## 差距清单

### Critical 优先级

| # | 差距 | 设计来源 | 影响 |
|---|------|---------|------|
| 1 | `hot_tool_results` 不在 AgentState 中 | Section 3.1 | Hot Zone 状态无法跨 checkpoint 持久化 |
| 2 | 无 `read_memory`/`write_memory` 节点 | Section 5.1 | 跨会话记忆无法动态注入 |
| 3 | `smart_message_reducer` 未实现 | Section 3.3 | 消息列表无上限增长风险 |

### Medium 优先级

| # | 差距 | 设计来源 | 影响 |
|---|------|---------|------|
| 4 | Namespace 未嵌入 thread_id | Section 8 | 潜在跨租户隔离问题 |
| 5 | `RetrievalTrigger` 未接入 Graph | Section 5.2 | 多维触发检索逻辑存在但未使用 |

---

## 实现计划

### Fix #1: Add hot_tool_results to AgentState

**目标**: 将 Tool Result Hot Zone 纳入 State 管理，支持跨 checkpoint 持久化

**修改文件**:
- `src/agent/state.py` — 添加 `hot_tool_results: list[ToolResultSummary]`
- `src/agent/context/compression.py` — 调整 ToolResultStore 与 State 集成

**验收标准**:
- `hot_tool_results` 在 checkpoint 保存时被序列化
- resume 后 Hot Zone 状态恢复

### Fix #2: Add read_memory/write_memory nodes

**目标**: 将 Section 5.1 设计的多维检索节点加入 Graph

**修改文件**:
- `src/agent/graph.py` — 添加 `read_memory` 和 `write_memory` 节点
- `src/agent/context/long_term.py` — 实现 `RetrievalTrigger` 集成

**节点流**:
```
START → read_memory → think → execute → write_memory → compress → save
```

**验收标准**:
- 跨会话记忆在 token 水位 >40% 时自动注入
- 语义相关任务触发相关记忆检索

### Fix #3: Implement smart_message_reducer

**目标**: 实现智能消息合并，防止无限增长

**修改文件**:
- `src/agent/state.py` — 添加 `smart_message_reducer` 函数

**逻辑**:
- MAX_MESSAGES = 20
- 超过阈值时调用 `ContextCompressor` 压缩

**验收标准**:
- `messages` 列表超过 20 条时自动触发压缩

### Fix #4: Embed namespace in thread_id

**目标**: 符合 Section 8 的四元组隔离设计

**修改文件**:
- `src/agent/agent.py` — 修改 `create_agent()` 中的 thread_id 生成逻辑
- `src/agent/context/long_term.py` — 使用 `get_namespace()` 验证隔离

**thread_id 格式**: `f"{tenant_id}:{org_id}:{session_id}"`

**验收标准**:
- 跨租户访问被正确拒绝

---

## 当前进度

- [x] Fix #1: hot_tool_results in State
- [x] Fix #2: read_memory/write_memory nodes
- [x] Fix #3: smart_message_reducer
- [x] Fix #4: namespace in thread_id
- [x] Fix #5: connect RetrievalTrigger
- [x] Lint + Typecheck + Tests

**Test results**: 98 passed, 1 failed (pre-existing, API key), 3 skipped

---

## 关键决策点

1. **State Schema 变更**: 是否保持向后兼容？旧 checkpoint 数据如何处理？
2. **Compression 时机**: smart_message_reducer 在 append 时调用 vs 专门的 compress 节点
3. **RetrievalTrigger 位置**: 放在 `read_memory` 节点内 vs 作为独立节点

---

## 参考

- 设计文档: `docs/context_design.md`
- 状态定义: `src/agent/state.py`
- Graph 定义: `src/agent/graph.py`
- 压缩逻辑: `src/agent/context/compression.py`