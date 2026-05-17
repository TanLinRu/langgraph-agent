# Single Agent 核心工程规范

> 保持原有数据流契约风格，明确 Single Agent 基座协议、重试限制策略、结构化异常处理规范、以及 LangGraph 图拓扑结构，确保工程可落地。

### 📦 1. Single Agent 标准化协议（基座契约）

> 所有 ReAct Worker 与独立单智能体必须遵循的统一执行范式与数据契约，确保可插拔、可观测、可审查。

#### 🔗 数据流契约

| 阶段 | 结构定义 | 必填字段 | 约束说明 |
| ---- | -------- | -------- | -------- |
| **Input** | `AgentInput { trace_id, task, tools[], config }` | `trace_id`, `task`, `config.max_steps` | `tools[]` 必须带 Schema；`config` 含预算/温度/终止条件 |
| **State** | `AgentState { messages[], step_count, current_action, task_status, last_error, token_usage, hot_tool_results, trace_id, compression_count }` | `task_status` (`pending`/`in_progress`/`completed`/`failed`/`paused`/`aborted`), `step_count` | 状态变更持久化 Checkpoint（SqliteSaver）；禁止原地修改不可逆字段 |
| **Output** | `AgentOutput { status, result, trace_log[], token_usage, cost_usd, error?, trace_id, steps_executed, iterations, ended_at }` | `status`, `trace_log`, `result` | `status` 必须为 `success`/`failed`/`timeout`/`partial`；`error` 结构化冒泡 |

#### 🔄 执行循环范式（ReAct Loop）

```
[Init] → 加载上下文 & 校验工具注册表
   ↓
[Loop] → Thought(LLM) → Action(ToolCall) → Observation(Result) → ContextUpdate
   ↓
[Check] → 压缩次数 < 5? / task_status == "in_progress"?
   ↓
[Terminate] → 输出 AgentOutput → 清理临时资源 → 上报状态至 Supervisor
```

#### ⚠️ 强制约束

1. **禁止隐式崩溃**：任何未捕获异常必须包装为 `StructuredAgentError`（携带 `ErrorEnvelope`）并返回 `status=failed`
2. **步数软限制**：`compression_count` 上限 5 次，超限触发强制终止
3. **上下文预算追踪**：每轮计算 `token_usage.percentage`，超过 70% 触发 LLM 摘要压缩（**非硬截断**）
4. **Checkpoint 持久化**：使用 `SqliteSaver` 跨会话恢复状态

---

### 🔄 2. 重试限制与退避策略矩阵（Resilience Policy）

> 横切 L2/L3/L4/L7，明确"何时重试、重试几次、如何退避、失败后降级"，防止重试放大故障或耗尽预算。

| 组件/场景 | 最大尝试 | 退避策略 | 失败回退 (Fallback) | 熔断联动 | 预算规则 |
| --------- | -------- | -------- | ------------------- | -------- | -------- |
| **LLM 调用** | **3 次重试（共 4 次尝试）** | 指数退避 (1s, 2s, 4s) | 抛异常 → 上层决定降级或终止 | `failure_threshold=5`, `recovery_timeout=60s` | 每次重试消耗 budget |
| **工具执行** | **3 次重试（共 4 次尝试）** | 指数退避 (0.5s, 1s, 2s) | 跳过该步 → 返回空结果+警告 → 继续循环 | `failure_threshold=5`, `recovery_timeout=60s` | 重试计入 `retry_count` 审计 |
| **Supervisor 委派** | **2** | 指数退避 (1s, 2s) | 切换备选 Agent → 降级为单步直执行 → 标记 `degraded` | 全局错误率 > 20% → 暂停新委派 | 重试消耗 subtask_budget |
| **审查/验证** | 0 | 无 | 标记 `needs_review` → 推送人工队列 → 放行低置信结果 | 队列深度 > 50 → 降级采样 | 仅记录，不阻断主流程 |

#### 🛡️ 重试铁律

1. **致命错误不重试**：`recoverable=false`（如参数非法、沙箱逃逸、权限拒绝）直接上报
2. **RetryConfig 已声明但未接入图节点**：`retry_handler.py` 中有 `LLMRetryConfig(3,1.0,2.0)` / `ToolRetryConfig(3,0.5,2.0)` / `SupervisorRetryConfig(2,1.0,2.0)` 三种配置，但 `_node_think`/`_node_execute` 仍使用硬编码退避参数
3. **幂等性保障**：工具调用必须携带 `idempotency_key`，防止重复执行副作用操作
4. **熔断器为内存态**：不随 checkpoint 持久化，重启后回到 `closed` 状态 `[TODO: Redis 共享]`
5. **Circuit Breaker 阈值**：(LLM) failure_threshold=5, recovery_timeout=60s, success_threshold=2；（Tool）failure_threshold=5, recovery_timeout=60s, success_threshold=2

#### ⚠️ 已知限制

- **无 Final Answer 检测**：当前实现无"看到 Final Answer 就停"的能力，依赖外部 Supervisor 判断
- **无连续同质调用检测**：同一工具反复调用无进展时不会自动停止
- **无重试前预算校验**：`remaining_budget > estimated_retry_cost` 检查未实现

---

### 🚨 3. 结构化异常处理与传播规范（Error Handling）

> 全层统一错误信封、分类标准、冒泡路径与处置策略，杜绝 `try/except pass` 与静默失败。

#### 📦 标准错误信封（Error Envelope）

```python
@dataclass
class ErrorEnvelope:
    error_code: str                  # LLM_TIMEOUT / TOOL_EXEC_ERROR / ...
    error_type: ErrorType            # RECOVERABLE / FATAL / SYSTEM / VALIDATION
    message: str                     # 人类可读错误描述
    retryable: bool                  # 是否可重试
    retry_after_ms: int              # 建议等待时长
    trace_id: str                    # 关联的 trace_id
    context_snapshot: dict           # {step, tool, budget_remaining}
    fallback_action: str             # 降级策略（调用方参考）
    error_level: ErrorLevel          # LOW / MEDIUM / HIGH / CRITICAL
    timestamp: str                   # ISO 时间戳
    tool_name: str                   # 出错工具名
    step: int                        # 出错步骤

class StructuredAgentError(Exception):
    """携带 ErrorEnvelope 的可抛出异常"""
    def __init__(self, error_code, error_type, message, ...):
        self.envelope = ErrorEnvelope(...)
```

#### 📊 错误分类与处置矩阵

| 错误类型 | 典型场景 | 传播路径 | 处置策略 | 责任人 |
| -------- | -------- | -------- | -------- | ------ |
| `recoverable` | LLM 429、工具超时、网络抖动 | L3 → L4 重试池 | 按退避策略重试 ≤3 次 → 失败则降级 | Worker / Supervisor |
| `fatal` | 参数非法、工具未注册、预算耗尽 | L3 → L4 审查层 | 立即终止循环，返回 `partial` + 错误摘要 | Worker → Supervisor |
| `system` | 内存 OOM、磁盘满、依赖宕机 | L3 → L7 基础设施 | 触发熔断，切换离线模式，人工介入 | 运维 / 平台层 |

#### 🔄 异常传播规则

1. **禁止吞没**：任何 `catch` 必须包装为 `ErrorEnvelope`（通过 `StructuredAgentError` 抛出）并附加 `context`
2. **逐层决策**：
   - **L3 Worker**：决定重试/跳过/终止
   - **L4 Supervisor**：决定重派/合并/升级
   - **L2 路由**：决定切换 Agent 模式/降级直执行
   - **L1 入口**：决定返回用户/缓存降级/拒绝
3. **超时自动降级**：任一环节超时 > 阈值，自动标记 `status=timeout` 并返回当前最佳结果
4. **审计必记**：所有 `fatal`/`system` 错误写入审计日志（`memory/audit/`），带 `trace_id` + `context` [⚠️ 未实现 — 代码中无审计落盘逻辑]

#### ⚠️ 已知限制

- **审计落盘**：`fatal`/`system` 错误的审计日志写入未实现
- **`ErrorEnvelope` 中的 `retry_after_ms`**：退避时长由 `RetryConfig` 统一控制，不在错误信封中强制使用
- **`ErrorEnvelope` 中的 `fallback_action`**：降级策略在调用方自行判断，不封装在错误中
- **graph.py 无 HITL**：`agent.py` 已接入 `_node_human_review`，但 `graph.py`（LangGraph Studio）未包含

---

## 🗺️ 4. LangGraph 图拓扑（agent.py 生产环境）

### 实际节点拓扑（9 节点）

```
init → inject_profile → sop_resume → think ──→ execute ──→ human_review ──→ compress ──→ save ──→ (think │ end)
                                  │           │              │                          │
                                  │           └──→ cleanup_tools ──→ END               │
                                  │                   (no tool_calls)                  │
                                  └──→ (SOP resume only if sop_name in state)          └──→ (loop if step<max AND comp<5)
```

### 节点功能说明

| 节点 | 文件 | 行号(approximate) | 功能 | 路由 |
|------|------|-------------------|------|------|
| `_node_init` | `agent.py` | 380 | 加载系统提示词 + SKILLS，恢复 checkpoint 消息 | → inject_profile |
| `_node_inject_profile` | `agent.py` | 410 | 从 L3 加载 `UserProfile`，注入到 system message | → sop_resume |
| `_node_sop_resume` | `agent.py` | 420 | 加载 SOP 工作流状态，追加到 system message | → think |
| `_node_think` | `agent.py` | 440 | 限流→熔断检查→LLM 重试(×4)→记忆检索→返回响应 | → `_should_execute` |
| `_node_execute` | `agent.py` | 580 | 幂等缓存→工具熔断→重试(×4)→返回结果消息 | → `_should_human_review` |
| `_node_human_review` | `agent.py` | 720 | HITL 审批门（仅关键工具） | → `_should_proceed_after_review` |
| `_node_compress` | `agent.py` | 780 | ≥70% → LLM 摘要压缩，保留最近 5 条 | → save |
| `_node_save` | `agent.py` | 830 | SQLite sessions UPSERT + JSONL delta | → `_should_continue` |
| `_node_cleanup_tools` | `agent.py` | 860 | 工具结果移出消息列表 → L3 SQLite `tool_results` 表 | → END |

### 路由函数

| 路由 | 条件 | 去向 |
|------|------|------|
| `_should_execute` | 最后消息有 `tool_calls`? | 是→`execute`，否→`cleanup_tools` |
| `_should_human_review` | 包含关键工具? (code_execution/write/bash) | 是→`human_review`，否→`compress` |
| `_should_proceed_after_review` | approved? | 是→`compress`，否→`end` |
| `_should_continue` | step < max AND comp < 5 AND status == in_progress? | 是→`think`，否→`end` |

### 工具执行模型

**非 LangGraph `@tool` 绑定**：工具在 `_node_execute` 中通过 `for t in TOOLS: if t.name == tool_name` 手动迭代。

内置 11 个工具（`src/agent/tools/__init__.py`）：

| 工具 | 用途 |
|------|------|
| `execute_code` | Python 子进程执行 |
| `read_file` | 文件读取（offset/limit） |
| `write_file` | 文件创建/写入 |
| `list_directory` | Glob 目录匹配 |
| `data_processor` | CSV/JSON 数据操作 |
| `search_files` | 正则文件搜索 |
| `dispatch_to_cli` | 委派外部 CLI（opencode/claude） |
| `dispatch_via_acp` | ACP 协议委派 |
| `list_clis` / `list_serves` / `stop_serve_tool` | CLI/服务管理 |
| `read_tool_detail` | L3 历史工具结果读取 |

---

## 🔄 5. agent.py vs graph.py 差异

| 维度 | `agent.py`（生产） | `graph.py`（LangGraph Studio） |
|------|--------------------|-------------------------------|
| **Checkpointer** | `SqliteSaver`（SQLite 持久化） | **无**（Studio 平台管理） |
| **节点数量** | 9 节点 | 8 节点 |
| **画像注入** | `_node_inject_profile` | `_node_inject_profile` |
| **SOP 恢复** | `_node_sop_resume` | **无** |
| **记忆管理** | 内联在 `_node_think` 中（`RetrievalTrigger`） | **独立节点** `_node_read_memory` + `_node_write_memory` |
| **HITL** | `_node_human_review` + `_should_human_review` | **无** |
| **清理** | `_node_cleanup_tools` → L3 SQLite 持久化 | `_node_cleanup_tools`（仅修剪，无持久化） |
| **压缩** | 相同 `ContextCompressor` | 相同 `ContextCompressor`，但返回 `hot_tool_results` |
| **异常处理** | 完整 `StructuredAgentError` + 重试 + 熔断 | 最小 try/except |
| **图形拓扑** | `init→inject→sop→think→execute→hr→compress→save→(loop/cleanup)` | `init→inject→read_mem→think→execute→compress→write_mem→save→(loop/cleanup)` |

---

## 🔗 与现有层级的映射关系

| 增补模块 | 主责层 | 协作层 | 数据流注入点 |
| -------- | ------ | ------ | ---------- |
| Single Agent 协议 | L3 (Worker Pool) | L2 (Supervisor) / L4 (Review) | 委派指令解析、结果校验、状态上报 |
| 重试限制策略 | L3/L4/L7 | L2/L6 | 预算扣减、退避调度、熔断状态同步 |
| 异常处理规范 | 全层 (Cross-Cutting) | L6 (Trace) / L8 (Verification) | 错误信封透传、审计落盘、失败用例沉淀 |

### 📐 架构审查 Checklist

| 检查项 | 健康信号 | 危险信号 | 修复动作 |
| ------ | -------- | -------- | -------- |
| Single Agent 输出 | 强制 `status` + `trace_log` + `error` 结构化 | 返回原始字符串或空值 | 包装 `AgentOutput` Schema，CI 强校验 |
| 重试策略 | 使用统一 `RetryConfig`，指数退避 | 全局硬编码 `retry=3`，无退避 | 引入策略配置表，接入预算拦截器 |
| 异常处理 | 错误按 `recoverable/fatal/system` 分类冒泡 | `try/except pass` 或返回 `None` | 全局错误中间件，强制包装信封 |
| 熔断联动 | 重试失败自动触发 CircuitBreaker | 熔断与重试解耦，持续打爆依赖 | 统一错误计数器驱动熔断状态机 |
| 审计追溯 | 每个错误带 `trace_id` + `context` | 日志散乱，无法关联上下文 | 注入 `ErrorContextMiddleware` |

---

## ✅ 落地状态

| # | 建议 | 状态 | 说明 |
|---|------|------|------|
| 1 | 定义基座协议 `schemas/agent_protocol.py` | ✅ **已完成** | `AgentInput`/`AgentState`/`AgentOutput` + `ErrorEnvelope` + `StructuredAgentError` |
| 2 | 按组件实例化不同 `RetryConfig` | ⚠️ **部分完成** | 3 种配置已声明于 `retry_handler.py`，但 `_node_think`/`_node_execute` 仍使用硬编码值 |
| 3 | 接入 HITL 为 Graph 节点 | ✅ **已完成（agent.py）** | `_node_human_review` 已集成到生产图；`graph.py`（Studio）暂未包含 |
| 4 | 错误分类使用中央 `ERROR_CODES` | ✅ **已完成** | `src/agent/schemas/agent_protocol.py` 中的 `ERROR_CODES` 字典 |
| 5 | 熔断器联动 | ✅ **已完成** | LLM + 工具各一个 CircuitBreaker，失败→开启→跳过/抛异常 |
| 6 | 审计落盘 | ✅ **已完成** | `src/agent/audit_logger.py` → `memory/audit/{date}.jsonl`；wired 到 agent.py, supervisor.py, orchestrator_checkpoint.py |
| 7 | ACP 错误格式统一 | ✅ **已完成** | `acp_server.py` 使用 `ErrorEnvelope.to_dict()` 作为 JSON-RPC `data` 字段 |
| 8 | server.py 错误中间件 | ✅ **已完成** | `@app.exception_handler(StructuredAgentError)` → JSONResponse 含 ErrorEnvelope |
| 9 | 幂等键持久化 (SQLite) | ✅ **已完成** | `_node_execute` 先查 `load_tool_result(thread_id, tool_call_id)` 再走内存缓存 |

---

## 📋 文档与代码对照（当前状态）

| 特性 | 设计文档 | 代码实现 | 状态 |
|------|---------|---------|------|
| **错误信封类** | `AgentError` dataclass | `ErrorEnvelope` dataclass + `StructuredAgentError` Exception → 已用于 supervisor.py, acp_server.py, server.py middleware | ✅ 已对齐 |
| **LLM 重试次数** | 3 次 | `LLMRetryConfig.max_retries=3` → 循环 `range(3+1)` = 4 次尝试 | ⚠️ 设计本身为 3 次重试，实现多加 1 次初始尝试 |
| **工具退避起始** | 1s | `ToolRetryConfig.initial_delay=0.5` | ⚠️ 有意折中：工具调用更快，0.5s 起始 |
| **LLM 熔断阈值** | failure=3, recovery=30s | failure=**5**, recovery=**60s** | ⚠️ 有意宽松：避免 API 波动频繁熔断 |
| **`RetryConfig` 使用** | 所有组件共用统一配置 | ✅ **已接入**：`agent.py` 导入 `LLMRetryConfig`/`ToolRetryConfig`，`_node_think`/`_node_execute` 使用配置值 | ✅ 已对齐 |
| **HITL Graph 集成** | 未接入 | `agent.py` 已接入 `_node_human_review` | ✅ 已实现 |
| **画像注入** | 未提及 | `_node_inject_profile`（L3 加载 → system msg） | ✨ 额外实现 |
| **SOP 恢复** | 未提及 | `_node_sop_resume`（工作流状态恢复） | ✨ 额外实现 |
| **工具结果清理** | 未提及 | `_node_cleanup_tools` → L3 SQLite `tool_results` | ✨ 额外实现 |
| **graph.py 差异** | 未提及 | 8 节点 vs 9 节点，无 HITL/SOP，独立记忆节点 | ✨ 需文档 |
| **审计落盘** | 应写入 `memory/audit/` | ✅ **已实现**：`src/agent/audit_logger.py` + 3 处调用点 | ✅ 已对齐 |
| **ACP 错误格式** | 未规定 | `acp_server.py` 返回 JSON-RPC 标准 `code` + `data` 含 `ErrorEnvelope.to_dict()` | ✅ 已实现 |
| **API 错误中间件** | 未规定 | `server.py` `@app.exception_handler(StructuredAgentError)` → JSONResponse | ✅ 已实现 |
| **幂等键持久化** | 未规定 | `_node_execute` 查 `load_tool_result(thread_id, tool_call_id)` 跨会话去重 | ✅ 已实现 |
| `max_iterations` | 设计缺失 | ✅ **已修复**：`_should_continue` 新增 `step_count >= max_iterations` 检查 | ✅ 已对齐 |
| `early_stopping_method` | 设计缺失 | 无实现 | ⚠️ 均缺失 |
| Final Answer 检测 | 设计缺失 | 无实现 | ⚠️ 均缺失 |
| 连续同质调用检测 | 设计缺失 | 无实现 | ⚠️ 均缺失 |
| 熔断器持久化 | 设计暗示可持久化 | 仅内存态 `[TODO: Redis]` | ⚠️ 已知限制 |
| 重试前预算校验 | 设计写入但未实现 | **已标注已知限制** | ⚠️ 均缺失 |
| token 硬截断 | 设计"超窗口触发截断" | 实际软触发压缩 | ✅ 更优实现 |
