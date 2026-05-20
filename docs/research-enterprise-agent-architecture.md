# 企业级 AI Agent 架构研究报告

> 为 rect-agent 架构设计提供行业参考 — 涵盖 Agent 模式、Context、Memory、I/O、生产可靠性
>
> 调研时间: 2026-05 | 覆盖 12+ 项目，5 大领域，19+ 模式
>
> ⚠️ **声明验证状态**: 本文档部分引用数据（如 "Pydantic AI 防止 80% 解析故障"、"Plan-Execute 比纯 ReAct 快 23%"）来自行业传闻/基准，未经针对本代码库验证。架构决策应在投入生产前通过基准测试验证。

---

## 目录

1. [项目总览对比](#1-项目总览对比)
2. [Agent 模式分析](#2-agent-模式分析)
3. [Context 管理分析](#3-context-管理分析)
4. [Memory 系统分析](#4-memory-系统分析)
5. [I/O 标准化分析](#5-io-标准化分析)
6. [生产可靠性对比](#6-生产可靠性对比)
7. [深度源码分析：Top 3 项目](#7-深度源码分析)
   - [7.1 LangGraph](#71-langgraph)
   - [7.2 Pydantic AI](#72-pydantic-ai)
   - [7.3 Agno](#73-agno)
8. [架构建议](#8-架构建议)
9. [缺失主题分析](#9-缺失主题分析)
10. [附录：参考链接与术语表](#10-附录)

---

## 1. 项目总览对比

> ⚠️ GitHub Stars 为动态数据，标注时间为 2026-05，仅供参考。

| # | 项目 | Stars (2026-05) | 架构模式 | 核心特性 | 生产就绪度 |
|---|------|----------------|----------|----------|-----------|
| 1 | **LangGraph** (langchain-ai/langgraph) | ~40k | 有状态图 StateGraph，Pregel/NetworkX 启发 | 持久化执行，检查点，HITL，子图，流式，LangSmith 可观测 | **最高** — Klarna/Uber/LinkedIn/Replit/JP Morgan 生产使用 |
| 2 | **Agno** (agno-agi/agno) | ~40k | 三层 Agent 框架 (SDK+Runtime+Dashboard) | 类型安全 I/O，100+ 工具包，多 Agent Team，MCP，Agentic RAG | **高** — FastAPI 运行时，RBAC，OpenTelemetry，50+ 端点 |
| 3 | **Pydantic AI** (pydantic/pydantic-ai) | ~25k | Agent 泛型 `Agent[DepsT, OutputT]`，底层 pydantic-graph | 结构化输出一等公民，依赖注入，MCP/A2A，Capabilities | **中高** — OpenTelemetry 原生，Logfire 可观测，v1 稳定；但图引擎和检查点比 LangGraph 成熟度低 |
| 4 | **CrewAI** (crewAIInc/crewAI) | ~52k | 角色 Crew + Flows（事件驱动编排） | 角色 Agent（role/goal/backstory），顺序/层级/共识流程，原生 MCP/A2A | **中高** — 企业版 HIPAA/SOC2，450M+ 月工作流 |
| 5 | **AutoGPT** (Significant-Gravitas/AutoGPT) | ~184k | Forge 套件 + Platform | Agent 协议标准，Marketplace，低代码构建器 | **中** — 成熟但实验性，生产稳定性问题 |
| 6 | **MetaGPT** (FoundationAgents/MetaGPT) | ~47k | 多 Agent 软件公司模拟 (SOP 驱动) | 角色 Agent (PM/架构师/工程师)，SOP 执行，软件工件产出 | **中** — 适合原型/研究 |
| 7 | **Microsoft Agent Framework** (microsoft/semantic-kernel + autogen) | ~70k | Graph + Agent Runtime | 函数工具，群聊，A2A/MCP，Magentic-One，持久化执行 | **高** — 微软支持，Azure 原生，GA |
| 8 | **Dify** (langgenius/dify) | ~70k | 可视化工作流引擎 + Agent 节点 + RAG | 聊天流/工作流应用，变量系统，插件，模型无关 | **高** — 云+自部署，Langfuse 可观测 |
| 9 | **LangFlow** (langflowai/langflow) | ~50k | 可视化 LangChain 图构建器 | 低代码，RAG 模式，LangChain 节点，调试体验 | **中高** — 生产 PostgreSQL+K8s |
| 10 | **OpenAI Agents SDK** (openai/openai-agents-python) | ~30k | Agent + Handoff + Guardrails | Guardrails，交接模式，Tracing，原生 OpenAI | **中高** — 2025 末 GA，供应商锁定 |
| 11 | **SmolAgents** (huggingface/smolagents) | ~15k | 极简模块化提示链 | 轻量，工具使用，任何 LLM | **低** — 原型/教育 |
| 12 | **Google ADK** (google/adk-python) | ~8k | 模块化 Agent 定义，Vertex AI 集成 | Gemini 原生，A2A，MCP，HITL | **中高** — GCP 原生 |

---

## 2. Agent 模式分析

### 2.1 ReAct（推理+行动）— 基础模式

所有主流框架实现 ReAct 为基线: `思考 → 行动 → 观察 → 思考[...]`

**关键实现差异**:

| 方面 | 文本解析 ReAct | 原生函数调用 ReAct | LangGraph 托管 ReAct |
|------|---------------|-------------------|---------------------|
| 可靠性 | 低（正则可能出错） | 高（结构化 JSON） | 最高（图约束） |
| 跨模型兼容 | 全部 | 仅函数调用支持的模型 | 任意（通过 LangChain） |
| 并行工具调用 | 单步单工具 | 单步多工具 | 通过分支原生支持 |
| 可观测性 | 文本轨迹可见 | 思考可能隐藏 | LangSmith 完全可观测 |

**生产模式**（`agent-patterns` 库）:

```
Agent ≠ Executor — LLM 返回意图（JSON action），系统通过 ToolGateway 验证:
  validate_action() → ToolGateway.call() → observe → loop
  有 Budget: max_steps, max_tool_calls, max_seconds
  有 Loop detection: 相同工具+相同参数
  有 Stop reasons: success, max_steps, loop_detected, tool_denied, invalid_action
```

### 2.2 Plan-and-Execute（计划-执行）

将规划和执行分离以减少推理开销。

| 框架 | 实现 | 权衡 |
|------|------|------|
| **LangGraph** | 两节点图: `planner_node` + `executor_node` | 规划做前瞻分解；执行器按序执行计划 |
| **CrewAI** | 顺序流程（每个 Agent 是一个计划步骤） | 规划在第一步隐含；适应性弱 |
| **MetaGPT** | 角色级 SOP（PM 规划，工程师执行） | 最严格流程；输出完全可预测 |

**适用场景**: 任务有已知结构但不完全确定时。

**现有系统对标**: `orchestrator_v2.py` (837 行) 已实现 LLM 驱动的任务分解，将用户任务拆为 DAG 步骤，拓扑排序执行，支持回滚和自适应重规划。它定义 `OrchestratorState`、`OrchestratorStep`，已有依赖感知执行模式。

### 2.3 Supervisor-Worker（监督者-工作者）— 多 Agent 标准

**企业多 Agent 事实标准**。一个监督者 Agent 将任务路由给专门的工作者 Agent。

**LangGraph 实现**:
```
StateGraph:
  supervisor_node（LLM 决定路由）→ conditional_edge 路由到工作者
  工作者_node 返回 → 循环回 supervisor 或结束
```

**CrewAI 实现**:
```
层级流程:
  管理 Agent → 分配任务 → 工作者 Agent → 返回结果 → 管理 Agent 综合
```

**Agno 实现**:
```
Team(mode="coordinate") 或 Team(mode="route")
  团队领导者维护共享状态和上下文
  成员有专门工具集
  领导者在 agent_team.run() 期间协调
```

**现有系统对标**: `state.py` 已定义 `SubAgentState`，专门为 supervisor 模式下多 Agent 协作设计。`registry.py` 已实现 Agent 注册和多图调度。

### 2.4 Graph Orchestration（图编排）— LangGraph 风格

将 Agent 构建为**有状态图**，节点是计算，边是控制流。

```
State = TypedDict（整个工作流共享的单一类型化模式）
节点  = 函数(State) → dict（读取/更新 State）
边   = 条件路由基于 State 内容
子图  = 可组合的独立 Agent 集群
```

**模式对比**:

| 维度 | ReAct | Supervisor-Worker | 图编排 |
|------|-------|-------------------|--------|
| 复杂度 | 低 | 中 | 高 |
| 控制力 | 低 | 中 | 最高 |
| 状态持久化 | 最小 | 通过共享状态 | 一等公民 |
| 可观测性 | 文本轨迹 | LLM 决定路由 | 每步状态快照 |
| 最佳场景 | 单工具任务 | 专门化工作者 | 复杂分支+循环 |

### 2.5 多 Agent 协调模式

| 模式 | Agno | CrewAI | LangGraph | 适用场景 |
|------|------|--------|-----------|----------|
| **Route** | Team(mode="route") | 层级流程 | supervisor→conditional_edge | 明确分工的任务 |
| **Coordinate** | Team(mode="coordinate") | 顺序流程 | 线性链 | 有序多步骤 |
| **Collaborate** | Team(mode="collaborate") | 共识流程 | 循环图 | 需要协商的任务 |
| **Swarm** | — | — | LangGraph Swarm 预建 | 大量同质 Agent |

---

## 3. Context 管理分析

### 3.1 Token Budget + 压缩触发器（已有模式验证）

现有系统使用 **70% 令牌阈值**（最大 128K），保留最近的 **5 条用户/助手消息 + 5 条工具结果**，结构化格式为 `CompressedTurn`。

**行业验证**:
- **Dify** `TokenBufferMemory`: 可配置窗口大小，2000 token 硬限制，500 条消息最大限制
- **LangGraph** `MessagesState`: 通过节点/边管理上下文窗口（无自动压缩，需自定义逻辑）
- **Pydantic AI**: 无内置压缩；依赖工具调用策略管理上下文

### 3.2 Hot Zone + LRU + 热度驱逐（已有模式验证）

现有系统使用双因素驱逐（LRU+热度）管理工具结果。

**行业对应**:
- **Agno** `Memory Optimization`: 将多个记忆合并为更少的、更高效的记忆
- **CrewAI** `Entity Memory`: 结构化记忆，带时间衰减的 LRU 算法
- **Microsoft Agent Framework** `AgentThread`: `save_state()` / `load_state()` 持久化

### 3.3 RAG 用于上下文检索

| 框架 | RAG 方法 | 向量数据库 | 检索策略 |
|------|----------|-----------|----------|
| **Agno** | 一等公民 `Knowledge` 模块 | 20+（Milvus, LanceDB, Pinecone, Qdrant） | 混合搜索（向量+关键词）+ 重排序 |
| **LangGraph** | 通过 LangChain 集成 | 任意 | 自定义 |
| **Dify** | 内置知识库 | Milvus, Zilliz, TiDB | 混合检索 + 元数据过滤 + 重排序器 |
| **CrewAI** | 通过工具外部集成 | 任意 | 工具控制 |

**Agno Agentic RAG**: Agent 在运行时**搜索**知识库，而不是预注入。接近现有 `long_term` 上下文（SQLite+ChromaDB）模式。

**差距**: 现有 ChromaDB 集成在索引时搜索，缺重排序器。短期修复可使用 ChromaDB MMR 搜索作为轻量近似。

### 3.4 动态上下文注入（Agno 模式）

**Dynamic Context Engineering**: 运行时将变量、状态和检索数据注入上下文。与现有 `initialize`（resume）上下文系统对齐。

*参考代码*: `libs/agno/agno/agent/` — Agent 类支持运行时提示更新和基于状态的指令。

### 3.5 基于状态的上下文过滤（Microsoft 模式）

Microsoft Agent Framework 使用 `AgentActor` 基类，运行时通过 `save_state()` / `load_state()` 管理上下文。`AgentThread` 抽象会话状态存储位置。

---

## 4. Memory 系统分析

### 4.1 全景对比: 4 层记忆模型

| 层级 | 现有系统 | 行业对标 |
|------|---------|---------|
| **L1 工作记忆** | State.messages（内存） | LangGraph MessagesState, Pydantic AI RunContext |
| **L2 会话** | SqliteSaver + JSONL (`./memory/sessions/`) | Agno Storage, CrewAI ShortTerm Memory |
| **L3 跨会话** | Store + ChromaDB (`./memory/chroma/`) | Agno Memory, CrewAI Entity Memory |
| **L4 组织** | 外部服务 | Agno Knowledge, Dify 知识库 |

### 4.2 会话持久化（L2 行业标准）

| 框架 | 机制 | 用途 |
|------|------|------|
| **LangGraph** | `Checkpointer`（SQLite/PostgreSQL/Redis） | 工作流步骤之间持久化图状态 |
| **Agno** | `Storage`（SQLite/PostgreSQL）+ `db` 参数 | 跨运行持久化会话历史和状态 |
| **CrewAI** | 内置记忆后端（短期/长期/实体） | 零配置为 Agent 提供记忆 |
| **Dify** | `TokenBufferMemory`（会话范围） | 缓冲最近消息，处理 token 计数 |
| **现有系统** | SqliteSaver + JSONL（`./memory/sessions/`） | 消息增量 + 检查点 |

**差距**: JSONL 增量好，但缺每用户/每会话隔离和 LangGraph `checkpoint-and-resume` 模式。

### 4.3 跨会话长期记忆（L3 行业标准）

| 框架 | 机制 | 持久化 |
|------|------|--------|
| **Agno** | `Memory`（用户记忆）+ `Culture`（Agent 间共享记忆） | 数据库 |
| **CrewAI** | 上下文记忆 + 实体记忆 | 文件/数据库 |
| **现有系统** | ChromaDB（向量）+ `MEMORY.md`（语义） | ChromaDB + 文件 |

**Agno `Culture` 概念**: 允许多 Agent 共享集体记忆。对于 `rect-agent` 来说是一个强候选模式。

### 4.4 Agentic RAG（L3-L4 行业标准）

Agno 和 Dify 在框架层面内置 Agentic RAG:
- Agent 在运行时**搜索**知识库（非预注入）
- 混合搜索（向量 + 关键词）+ 重排序
- 20+ 向量数据库支持

**差距**: ChromaDB 集成好，但**缺重排序器**且向量搜索在索引时而非检索时——当前 RAG 性能的即时改进点。短期方案：使用 ChromaDB 内置 MMR 搜索。

### 4.5 结构化输出记忆（Pydantic AI 模式）

Pydantic AI 将记忆视为**类型化数据结构**而非自由文本:

```python
class MemoryEntry(BaseModel):
    timestamp: datetime
    agent_id: str
    session_id: str
    memory_type: Literal["episodic", "semantic", "procedural"]
    content: str
    tags: list[str]
    importance_score: float  # 用于热度驱逐
```

---

## 5. I/O 标准化分析

### 5.1 类型化状态模式（LangGraph 模式）

**核心思想**: 整个工作流图共享单一类型化模式。每节点读写共享状态。

**现有系统现状**: `src/agent/state.py` 已实现 **21 个显式类型化字段**，包括:
- `messages: Annotated[list, smart_message_reducer]` — 带自定义 reducer 的消息合并
- `token_usage: Annotated[dict, token_budget_reducer]` — 带预算控制的 token 追踪
- `task_status: Literal["pending", "in_progress", ...]` — 枚举状态约束
- `current_action: Optional[CurrentAction]` — 类型化动作追踪
- `last_error: Optional[ErrorEnvelope]` — 结构化错误记录
- `SubAgentState`、`OrchestratorState`、`OrchestratorStep` — 多 Agent 编排状态

```python
# 现有状态模式（已实现深度类型化）
class AgentState(TypedDict):
    messages: Annotated[list, smart_message_reducer]
    token_usage: Annotated[dict, token_budget_reducer]
    step_count: int
    task_status: Literal["pending", "in_progress", "paused", "completed", "failed", "aborted"]
    current_action: Optional[CurrentAction]
    last_error: Optional[ErrorEnvelope]
    trace_id: str
    thread_id: str
    # ... 共 21+ 字段
```

**改进方向**: 标准化 reducer 命名、添加 `Annotated[list, add_messages]` 对齐 LangGraph 社区惯例。

### 5.2 结构化输出一等公民（Pydantic AI + Agno 模式）

**Pydantic AI**（最具方法论严谨）:

```python
agent = Agent(
    model='openai:gpt-4o',
    deps_type=SupportDependencies,
    output_type=SupportOutput,  # Pydantic 模型 — 强制结构化响应
    instructions="..."
)
result = await agent.run("...", deps=deps)
# result.output 类型为 SupportOutput（Mypy 可验证）
```

**现有系统现状**: `src/agent/schemas/agent_protocol.py` 已定义 `AgentOutput`/`AgentInput` 等 Pydantic 模式。

**差距**: 现有代码库未在 Agent 类层面强制 `output_type`。LLM 调用依赖提示词约束而非模式约束。建议 2 将解决这一问题。

### 5.3 依赖注入（Pydantic AI + Agno 模式）

**Pydantic AI `RunContext`**:

```python
@agent.tool
async def customer_balance(
    ctx: RunContext[SupportDependencies], include_pending: bool
) -> float:
    balance = await ctx.deps.db.customer_balance(
        id=ctx.deps.customer_id,
        include_pending=include_pending,
    )
    return balance
```

**架构注意**: Pydantic AI 的 `RunContext` 适用于单步运行的框架。**LangGraph 是多步骤、有状态的图执行模型**，节点接收 `State` 本身作为上下文。直接移植 `RunContext` 意味着:
- 要么将 `RunContext` 嵌入 State（每步骤需要序列化）
- 要么作为不持久化的依赖注入（需要检查点路径或线程安全组件）

**现有系统现状**: 工具通过状态传递配置（`config: AgentConfig` 在 `agent.py` 中注入），全局模块（`rate_limiter`、`tool_breakers`）通过基函数访问。

**改进方向**: 有限范围的轻量 `RunContext`：仅用于测试的 mock 点，不替代 LangGraph 的 State 驱动模型。

### 5.4 工具定义的标准化

| 框架 | 工具定义 | 类型化参数 | 错误处理 |
|------|---------|-----------|---------|
| **LangGraph** | 任意 Python 函数 + LangChain 工具包装 | 通过 Pydantic | 工具内自定义 |
| **Pydantic AI** | `@agent.tool` + `RunContext` + Pydantic 验证 | 强类型（函数签名） | 自动重试 + `ModelRetry` |
| **Agno** | `Tool` 类 + 100+ 预构建工具包 | Pydantic schema | 工具内自定义 |
| **CrewAI** | 基于角色的工具分配 + 工具类 | YAML/Python | 任务级重试（`max_retry_limit`） |

**现有系统现状**: 现有 12 个内置工具已:
- 返回 `ToolResult` TypedDict（来自 `src/agent/schemas/tool_result.py`）
- 通过 `retry_handler.py` 中的 `RetryableTool` 包装器实现预算感知重试
- 每组件重试配置（`LLMRetryConfig`、`ToolRetryConfig`、`SupervisorRetryConfig`）
- 指数退避
- `_node_execute` 中的工具级熔断器

**改进方向**: 正式化 `RectTool` 封装类，统一现有零散的包装逻辑。

### 5.5 状态持久化 / 检查点

| 框架 | 方法 | 恢复能力 | HITL 支持 |
|------|------|---------|-----------|
| **LangGraph** | 一等检查点 `Checkpointer` | 完美（崩溃恢复） | 原生 `interrupt()` + 恢复 |
| **Pydantic AI** | 通过 `TemporalAgent`/`DBOSAgent` | 持久化执行 | 通过包装器 |
| **Agno** | `Storage` + `Memory` 驱动 | 好（会话恢复） | 运行时审批 |
| **现有系统** | SqliteSaver + JSONL | 好 | 通过 `human_in_loop.py` |

**差距**: `graph.py` 无检查点（与 `agent.py` 不同）——已标注为关键不一致。

---

## 6. 生产可靠性对比

> 此维度评估框架内置的生产可靠性能力。现有系统在此维度表现突出，多项能力领先业界。

| 能力 | 现有系统 | LangGraph | Pydantic AI | Agno | CrewAI |
|------|---------|-----------|-------------|------|--------|
| **速率限制** | `RateLimiter` (RPM+成本+熔断) | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 |
| **熔断器** | 每工具+每 LLM，可选 Redis | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 |
| **预算控制** | 成本预检查 + halt 阈值 | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 |
| **优雅降级** | 主/备切换 + 级别 (normal/degraded/failed) | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 |
| **人机协同** | 类型化审批队列 (CODE/ASSISTANT/RESOURCE) | `interrupt()` | `requires_approval` flag | 运行时审批 | 任务级审批 |
| **健康检查** | `ServiceHealthChecker` | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 |
| **可观测性** | `get_metrics()` + LangSmith | LangSmith 集成 | Logfire/OpenTelemetry | OpenTelemetry | 企业版 |
| **审计日志** | 检查点持久化 + `audit_logger` | 检查点 | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 |
| **错误分类** | `ErrorEnvelope` + `ErrorType` + `ErrorLevel` | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 | ❌ 无内置 |

### 6.1 现有可靠性基础设施详解

#### 速率限制器 (`src/agent/rate_limiter.py`)

| 特性 | 说明 |
|------|------|
| RPM 限制 | 基于滑动窗口的分钟级频率限制 |
| 每小时成本熔断 | `max_cost_per_hour`, `alert_threshold`, `halt_threshold` 三级控制 |
| 每工具熔断器 | `ToolCircuitBreaker` 管理，独立失败阈值/恢复超时 |
| 每 LLM 熔断器 | 专用 `_llm` breaker，保护 LLM 调用 |
| Redis 持久化 | `RedisCircuitBreaker` 支持分布式状态 |
| 半开恢复 | `STATE_HALF_OPEN` 自动探测恢复 |

#### 优雅降级 (`src/agent/graceful_degradation.py`)

| 特性 | 说明 |
|------|------|
| 降级级别 | `normal` → `degraded` → `failed` 三级 |
| 主/备切换 | 主服务失败自动切换备用 |
| 健康检查 | `ServiceHealthChecker` 基于失败计数自动判定 |
| 恢复检测 | 成功后自动回到正常状态 |

#### 人机协同 (`src/agent/human_in_loop.py`)

| 特性 | 说明 |
|------|------|
| 审批类型 | `CODE_EXECUTION`, `WRITE_OPERATION`, `RESOURCE_ACCESS` |
| 审批队列 | 异步请求/响应模式 |
| 超时处理 | 可配置审批超时 |
| 回调注册 | `register_callback()` 支持自定义后处理 |

### 6.2 差距分析

现有系统在生产可靠性方面**领先所有分析的框架**，但仍有改进空间:

| 差距 | 说明 | 优先级 |
|------|------|--------|
| 缺 `interrupt()` 原生 HITL | 当前 HITL 用 `asyncio.ensure_future` 异步模式，LangGraph 1.x 提供更可靠的 `interrupt()` | 高 |
| 缺 OpenTelemetry 集成 | 当前仅 LangSmith，缺标准 OTel 导出 | 中 |
| 重试配置碎片化 | `LLMRetryConfig`/`ToolRetryConfig`/`SupervisorRetryConfig` 应统一 | 低 |
| 降级策略不够丰富 | 当前仅主/备切换，缺熔断+降级联动策略 | 中 |

---

## 7. 深度源码分析

### 7.1 LangGraph

**仓库**: [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph)

#### 核心架构（`langgraph/graph/state.py`）

```python
class StateGraph(Graph):
    """有向图，节点操作一个类型化的共享状态模式。"""

    def add_node(self, name: str, fn: Callable):
        """注册一个操作状态的节点函数。"""

    def add_edge(self, src: str, dst: str):
        """添加无条件边。"""

    def add_conditional_edges(self, src: str, router_fn: Callable, mapping: dict):
        """路由函数基于当前状态决定执行路径。"""

    def compile(self, checkpointer=None) -> CompiledGraph:
        """编译为可执行图，可选检查点。"""
```

#### 状态管理

```python
# 预建消息状态
class MessagesState(TypedDict):
    messages: Annotated[list, add_messages]

# 自定义状态模式
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    next_node: str
    step_count: int
    # 任何额外字段

# Annotated[type, reducer_fn] — 自定义状态合并
# add_messages: 追加到列表（消息场景）
# operator.add: 合并列表
# 自定义 reducer: 按需
```

#### 检查点系统（核心差异化特性）

```python
# 检查点保存完整图状态
# 支持: 崩溃恢复, HITL 暂停/恢复, 时间旅行调试
checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
graph = workflow.compile(checkpointer=checkpointer)

# 恢复:
thread_id = {"configurable": {"thread_id": "user-session-1"}}
for event in graph.stream({"messages": [user_input]}, thread_id):
    # 每次中断后恢复执行
    ...

# 检查点集成持久化存储:
# SQLite（开发）| PostgreSQL（生产）| Redis（分布式）
```

#### 关键文件结构

| 路径 | 功能 |
|------|------|
| `langgraph/graph/state.py` | StateGraph 实现 |
| `langgraph/checkpoint/` | 检查点抽象（SQLite, Postgres, Memory） |
| `langgraph/prebuilt/` | 预建 Agent (`create_react_agent` 等) |
| `langgraph/pregel/` | 底层 Pregel 执行引擎 |
| `langgraph/types.py` | `interrupt()` 等类型 |

#### 对 rect-agent 的启示

核心洞察: **状态是一等原则，不是事后想法**。图模式让你推理数据流而非仅提示流。验证当前基于图的方法。现有 21 字段的 `AgentState` 已符合这一原则，但可更紧密对齐 LangGraph 社区 reducer 惯例。

---

### 7.2 Pydantic AI

**仓库**: [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai)

#### 核心架构（`pydantic_ai_slim/pydantic_ai/agent/__init__.py`）

```python
class Agent(Generic[AgentDepsT, OutputDataT]):
    # 类型层面参数化: Agent[依赖类型, 输出类型]

    def __init__(
        self,
        model: Model | str,
        output_type: OutputSpec[OutputDataT] = str,   # 类型安全输出
        deps_type: type[AgentDepsT] = NoneType,       # 类型化依赖注入
        tools: Sequence[Tool[AgentDepsT] | ToolFunc] = (),
        system_prompt: str | Sequence[str] = (),
        result_tool: Tool[AgentDepsT] | None = None,  # 带验证的结果工具
        result_validators: Sequence[ResultValidator[AgentDepsT, OutputDataT]] = (),
        ...
    )
```

#### 工具系统（`pydantic_ai_slim/pydantic_ai/tools.py`）

```python
@dataclass(init=False)
class Tool(Generic[ToolAgentDepsT]):
    function: ToolFuncEither[ToolAgentDepsT]
    takes_ctx: bool
    max_retries: int | None
    name: str
    description: str | None
    prepare: ToolPrepareFunc | None  # 动态注册/注销
    requires_approval: bool          # 内置 HITL
    timeout: float | None
    function_schema: FunctionSchema   # 从函数签名自动生成

    @property
    def tool_def(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters_json_schema=self.function_schema.json_schema,
            kind='unapproved' if self.requires_approval else 'function',
        )
```

#### 图执行（通过 pydantic-graph）

```python
# 每个 Agent 底层被构建为一个图
def _build_graph(self) -> Graph:
    # 节点: 系统提示注入 → 模型调用 → 工具执行 → 输出验证
    # 边: 条件路由（if tool_calls → 回到模型调用）
    # END: 输出匹配 output_type
```

#### 依赖注入模式

```python
# 类型化的运行上下文
@dataclass
class SupportDependencies:
    db: Database
    customer_id: str
    settings: Settings

# Agent 依赖类型参数化
support_agent = Agent(
    model='openai:gpt-4o',
    deps_type=SupportDependencies,
    output_type=SupportOutput,
)

# 运行时注入
result = await support_agent.run(
    "What is my balance?",
    deps=SupportDependencies(db=db, customer_id="123", settings=settings)
)
```

#### 关键文件结构

| 路径 | 功能 |
|------|------|
| `pydantic_ai_slim/pydantic_ai/agent/__init__.py` | Agent 主类 |
| `pydantic_ai_slim/pydantic_ai/tools.py` | 工具系统 |
| `pydantic_ai_slim/pydantic_ai/result.py` | 结果处理/验证 |
| `pydantic_ai_slim/pydantic_ai/_agent_graph.py` | 图构建 |
| `pydantic_graph/` | pydantic-graph 引擎 |

#### 局限性说明

| 限制 | 说明 |
|------|------|
| 图引擎成熟度 | `pydantic-graph` 比 LangGraph 新，缺内置检查点、流模式较简单、无子图 |
| 工具执行 | 缺原生并行工具调用（LangGraph 通过分支支持） |
| 生产可靠性 | 无内置速率限制/熔断器/预算控制 |
| 状态持久化 | 无一等检查点；需通过 `TemporalAgent`/`DBOSAgent` 包装 |

#### 对 rect-agent 的启示

核心洞察: **类型安全的边界**。每个交互点（输入、输出、工具、依赖）都经过类型化和验证。建议采纳 `output_type` 强制模式，但注意其图引擎和检查点比 LangGraph 成熟度低，不应作为 rect-agent 的基础框架。

---

### 7.3 Agno

**仓库**: [agno-agi/agno](https://github.com/agno-agi/agno)

#### 核心架构（`libs/agno/agno/agent/`）

```
5 级系统:
  Level 1: 带工具和指令的 Agent
  Level 2: 带知识和存储的 Agent
  Level 3: 带记忆和推理的 Agent
  Level 4: 能推理和协作的 Team
  Level 5: 带状态和确定性的 Workflow
```

#### Agent 类结构（`libs/agno/agno/agent/agent.py`）

```python
class Agent:
    name: str
    model: Model              # 模型无关（23+ 供应商）
    tools: list[Tool]         # 100+ 预构建工具包
    knowledge: KnowledgeBase  # Agentic RAG 通过 20+ 向量数据库
    storage: Database         # SQLite/PostgreSQL 会话持久化
    memory: Memory            # 用户记忆（跨会话）+ Culture（共享）

    # I/O 标准化
    input_schema: type | None
    output_schema: type | None

    # 多 Agent
    team: Team  # Route / Collaborate / Coordinate 模式
```

#### Team 模式（关键差异化）

```python
# 3 种多 Agent 协调模式:
# 1. "route" — 团队领导者转发消息给专门成员
# 2. "coordinate" — 成员使用共享上下文协作
# 3. "collaborate" — 完全自主团队协作

team = Team(
    mode="coordinate",
    members=[research_agent, writer_agent, editor_agent],
    model=OpenAIChat(id="gpt-4o"),
    success_criteria="生产就绪报告",
    instructions=["始终引用来源"],
)
```

#### 记忆系统（最全面）

```
记忆类型:
  1. 会话历史（通过 Storage）- L2
  2. 用户记忆（跨会话偏好）- L3
  3. Culture（Agent 间共享长期记忆）- L3
  4. 知识（通过向量数据库 Agentic RAG）- L4

MemoryManager:
  - 自定义哪些 LLM 创建/更新记忆
  - 隐私规则
  - Memory Optimization: 合并多个记忆为更少、更高效的
  - Memory Tools: Agent 使用显式工具 CRUD 记忆
```

#### 关键文件结构

| 路径 | 功能 |
|------|------|
| `libs/agno/agno/agent/agent.py` | Agent 主类 |
| `libs/agno/agno/agent/team.py` | Team 模式 |
| `libs/agno/agno/agent/session.py` | 会话管理 |
| `libs/agno/agno/agent/memory.py` | 记忆系统 |
| `libs/agno/agno/knowledge/` | 知识库/RAG |
| `libs/agno/agno/storage/` | 持久化存储 |
| `libs/agno/agno/tools/` | 100+ 工具包 |

#### 对 rect-agent 的启示

核心洞察: **分层记忆 + Team 模式**。三层记忆架构（用户/Culture/知识）可组合映射到 4 层模型。Team 模式为多 Agent 协调提供了优雅形态。

---

## 8. 架构建议

### 建议 1: 深化类型化状态模式

**现状**: `AgentState` 已有 21+ 类型化字段，但 reducer 命名不统一（`smart_message_reducer` vs LangGraph 标准 `add_messages`）。

**改进**:
```python
# 当前: 自定义 reducer 命名
class AgentState(TypedDict):
    messages: Annotated[list, smart_message_reducer]

# 改进: 标准化 reducer + 更丰富元数据
class RectAgentState(TypedDict):
    messages: Annotated[list, add_messages]          # LangGraph 标准 reducer
    metadata: SessionMetadata                         # 类型化会话信息
    step_count: int                                   # 循环控制
    compression_count: int                            # 压缩跟踪
    compressed_history: list[CompressedTurn]           # 结构化压缩
    active_tools: dict[str, ToolResult]               # 类型化工具结果
    pending_human_approval: bool                      # HITL 标志
    cost_budget: CostBudget                           # 预算追踪
```

**理由**: 标准化 reducer 使状态行为可预测，提升与 LangGraph 生态的互操作性。

**工作量**: 低 | **影响**: 高

---

### 建议 2: 为结构化输出添加 `output_type` 强制

**现状**: `src/agent/schemas/agent_protocol.py` 已定义 `AgentOutput`/`AgentInput`，但 Agent 类未在类型层面强制输出模式。LLM 调用依赖提示词约束而非模式约束。

**改进**:
```python
class RectAgent(Generic[OutputT]):
    def __init__(
        self,
        model: ChatOpenAI,
        output_type: type[OutputT] = str,
        ...
    ):
        self._output_schema = output_type

    def invoke(self, input_data: dict, config: dict) -> OutputT:
        # 将 output_schema 传递给 LLM 作为响应格式
        result = self._graph.invoke(
            input_data,
            config,
            output_schema=self._output_schema
        )
        return self._output_schema.model_validate(result)
```

**理由**: 类型层面强制输出可减少 80%+ 的解析相关故障（基于 Pydantic AI 的行业验证）。与现有 `AgentOutput`/`AgentInput` 模式兼容。

**工作量**: 低 | **影响**: 高

---

### 建议 3: 有限范围依赖注入

**现状**: 工具通过状态传递配置，全局模块通过基函数访问。测试时 mock 全局变量。

**架构注意**: LangGraph 是多步骤有状态图，节点接收 `State` 作为上下文。Pydantic AI 的 `RunContext` 设计用于单步运行，无法直接移植。

**改进**:
```python
# 轻量上下文 — 仅用于测试 mock 点
@dataclass
class RectContext:
    """有限范围的依赖上下文，不替代 State。"""
    rate_limiter: RateLimiter
    tool_breakers: ToolCircuitBreaker
    config: AgentConfig

# 工具签名 — 通过闭包注入，非 RunContext
def create_tool_node(ctx: RectContext) -> ToolNode:
    def execute_wrapper(request: ToolCallRequest, execute: Callable) -> ToolMessage:
        # 使用 ctx 中的依赖
        if not ctx.rate_limiter.check_limit():
            return error_result("rate_limited")
        return execute(request)
    return ToolNode(TOOLS, wrap_tool_call=execute_wrapper)
```

**理由**: 保留 LangGraph 的 State 驱动模型，同时为测试提供可控的 mock 点。不过度工程化。

**工作量**: 中 | **影响**: 高（可测试性）

---

### 建议 4: 分层记忆管理器（渐进式）

**现状**: 4 层模型（L1-L4）都耦合在 `context/` 模块中，7+ 个类分散管理。

**渐进式实施计划**:

**第 1 阶段**（低风险）: 创建 `MemoryManager` 外观，包装现有 `LongTermManager`、`ContextCompressor`、`ToolResultStore`、`RetrievalTrigger` — 无行为变化。

```python
class MemoryManager:
    def __init__(self):
        self.working = WorkingMemory()        # L1
        self.session = SessionMemory()         # L2
        self.cross_session = VectorMemory()    # L3
        self.organizational = KnowledgeBase()  # L4

    async def retrieve(self, query: str, level: int = 3) -> MemoryContext:
        contexts = []
        if self.working.has_relevant(query):
            contexts.append(self.working.get())
        if level >= 2:
            contexts.append(await self.session.get_context(query))
        if level >= 3:
            docs = await self.cross_session.search(query, use_hybrid=True)
            contexts.append(docs)
        if level >= 4:
            knowledge = await self.organizational.retrieve(query)
            contexts.append(knowledge)
        return self._merge_contexts(contexts)

    async def store(self, turn: CompressedTurn, importance: float):
        await self.session.store(turn)
        if importance > IMPORTANCE_THRESHOLD:
            await self.cross_session.store(
                self._to_vector(turn),
                metadata={"importance": importance}
            )
```

**第 2 阶段**（中风险）: 添加重要性评分到压缩流程。

**第 3 阶段**（高风险）: 实现重排序器（如 Agno），迁移到检索时搜索。

**理由**: 渐进降低风险。Agno 通过 `Storage`/`Memory`/`Knowledge` 分离验证了分层方法。

**工作量**: 高 | **影响**: 中

---

### 建议 5: 统一工具注册封装

**现状**: 工具重试/熔断/审批逻辑分散在 `retry_handler.py`、`_node_execute`、`human_in_loop.py` 多个地方。

**改进**:
```python
@dataclass
class RectTool(Generic[ToolDepsT]):
    function: Callable
    name: str
    description: str
    parameters_schema: type         # Pydantic 模型
    takes_ctx: bool = False
    max_retries: int = 3
    requires_approval: bool = False  # HITL 门控
    timeout: float = 30.0

    async def execute(self, ctx: RectContext, **kwargs) -> ToolResult:
        validated = self.parameters_schema(**kwargs)

        if self.requires_approval:
            await self._request_approval(ctx)

        for attempt in range(self.max_retries):
            try:
                result = await self.function(ctx, **validated.model_dump())
                return ToolResult(status="success", data=result)
            except RetryableError as e:
                if attempt == self.max_retries - 1:
                    return ToolResult(status="error", error=str(e))
                await asyncio.sleep(2 ** attempt)

        return ToolResult(status="error", error="Max retries exceeded")
```

**理由**: 将现有零散的包装逻辑统一到一个模式中。复用现有 `ToolResult` TypedDict、`RetryableTool` 重试逻辑和 `human_in_loop.py` 审批队列。

**工作量**: 中 | **影响**: 高（可维护性）

---

### 执行优先级

| 编号 | 建议 | 影响 | 工作量 | 推荐顺序 | 基准 |
|------|------|------|--------|---------|------|
| 1 | 深化类型化状态 | 高（可靠性） | 低 | **2** | LangGraph 标准 |
| 2 | `output_type` 强制 | 高（可靠性） | 低 | **1** | Pydantic AI |
| 3 | 有限范围依赖注入 | 高（可测试性） | 中 | 4 | Pydantic AI（适配） |
| 4 | 分层记忆管理器 | 中（架构） | 高 | 5 | Agno |
| 5 | 统一工具注册 | 高（可维护性） | 中 | 3 | Pydantic AI + Agno |

**推荐执行顺序**: 建议 2 → 建议 1 → 建议 5 → 建议 3 → 建议 4

从最简单、影响力最高的开始（强制结构化输出），逐步加深架构改进。

---

## 9. 缺失主题分析

本文档主要分析 Agent 模式、Context、Memory、I/O 和生产可靠性。以下主题是重要的架构维度，但受限于研究范围未深入展开，建议后续单独分析。

### 9.1 流式传输

流式传输是用户交互的核心要求，各框架实现差异显著:

| 框架 | 流式模式 | 中间步骤 | WebSocket/SSE |
|------|---------|---------|---------------|
| **LangGraph** | `stream_mode="values"`/`"updates"` | ✅ | 通过 FastAPI |
| **Pydantic AI** | async generator | ❌ | 需自行包装 |
| **Agno** | Generator | ❌ | 通过 FastAPI |
| **现有系统** | `graph.stream()` with `stream_mode="values"` | ✅ (agent.py) | 通过 server.py |

**生产模式**:
- 逐 Token: LLM 输出流式传输到前端
- 中间步骤: 工具调用时发出进度更新
- 优先级响应: 先返回初始认知，再流式推理

### 9.2 多租户与隔离

| 维度 | 现有系统 | 行业最佳实践 |
|------|---------|-------------|
| **检查点隔离** | 通过 `thread_id` 命名空间 | LangGraph: 每租户独立 checkpointer |
| **向量存储隔离** | 单 ChromaDB 实例 | 每租户独立集合 vs 元数据过滤 |
| **配置隔离** | 单 `AgentConfig` | 每租户配置覆盖 |
| **速率限制** | 全局 | 每租户独立配额 |

**命名空间模式**: 现有 `make_thread_id` 使用 `tenant_id:org_id:user_id:session_id` 模式，已为多租户准备。

### 9.3 错误分类与恢复策略

现有系统已实现完整的错误分类体系，但文档未覆盖:

```python
# src/agent/schemas/agent_protocol.py
@dataclass
class ErrorEnvelope:
    error_code: str            # LLM_RATE_LIMIT, TOOL_EXEC_ERROR, etc.
    error_type: ErrorType      # FATAL, RECOVERABLE
    error_level: ErrorLevel    # LOW, MEDIUM, HIGH, CRITICAL
    retryable: bool            # 是否可重试
    trace_id: str              # 分布式追踪
```

**生产恢复策略**:
| 错误类型 | 重试策略 | 熔断策略 |
|---------|---------|---------|
| 速率限制 | 指数退避 (2s, 4s, 8s) | 开 breaker |
| 超时 | 重试 ×3 | 半开恢复 |
| 权限 | 不重试 | 不开 breaker |
| 参数错误 | 不重试 | 不开 breaker |

### 9.4 Agent 间通信协议

| 协议 | 模式 | 适用场景 | 现有系统 |
|------|------|---------|---------|
| **MCP** (Model Context Protocol) | 请求-响应 | 工具/资源/提示共享 | 未集成 |
| **A2A** (Agent-to-Agent) | 发布-订阅 | 多 Agent 协作 | 未集成 |
| **ACP** (Agent Communication Protocol) | JSON-RPC stdio | 子进程 Agent 调度 | `dispatch_via_acp` 已实现 |

**分析**: MCP 和 A2A 各被主流框架提及但未进行过比较分析。现有系统通过 ACP 实现 Agent 间通信，与 LangGraph 生态兼容性一般。如需扩展多 Agent 协作，建议评估 MCP 集成。

### 9.5 模型供应商多样性

| 维度 | 当前状态 | 风险 |
|------|---------|------|
| 模型 | 仅 OpenAI (gpt-4o) | 供应商锁定 |
| 嵌入 | 仅 OpenAI | 供应商锁定 |
| Fallback | 无 | 单点故障 |

**建议**: 通过 `AGENT_MODEL` 环境变量已支持模型切换（`openai:gpt-4`），但缺：
- Anthropic/Google/开源模型支持
- 回退链（主模型失败自动切换到备用）
- 不同约束模型适配（最大上下文差异、函数调用格式差异）

### 9.6 测试模式

AGENTS.md 已要求"每个新功能必须包含测试"，本文档应分析:

| 框架 | 测试模式 | Mock 策略 | 图测试 |
|------|---------|-----------|--------|
| **LangGraph** | 节点级单元测试 + 图级集成测试 | mock LLM 调用 | `graph.invoke()` 全流程测试 |
| **Pydantic AI** | 依赖注入天然可测试 | mock `RunContext.deps` | 单步测试 |
| **现有系统** | pytest + mock LLM | Mock + Real 双模式 | `test_agent.py` 已有 |

**图测试挑战**: LangGraph 图不易进行纯单元测试（节点依赖全局状态），更适合集成测试。`create_react_agent` 减少了自定义节点数量，降低测试复杂度。

---

## 10. 附录

### 参考项目

| 项目 | URL |
|------|-----|
| LangGraph | https://github.com/langchain-ai/langgraph |
| Agno | https://github.com/agno-agi/agno |
| Pydantic AI | https://github.com/pydantic/pydantic-ai |
| CrewAI | https://github.com/crewAIInc/crewAI |
| AutoGPT | https://github.com/Significant-Gravitas/AutoGPT |
| MetaGPT | https://github.com/FoundationAgents/MetaGPT |
| Semantic Kernel | https://github.com/microsoft/semantic-kernel |
| AutoGen | https://github.com/microsoft/autogen |
| Dify | https://github.com/langgenius/dify |
| LangFlow | https://github.com/langflowai/langflow |
| OpenAI Agents SDK | https://github.com/openai/openai-agents-python |
| SmolAgents | https://github.com/huggingface/smolagents |
| Google ADK | https://github.com/google/adk-python |

### 术语表

| 术语 | 说明 |
|------|------|
| ReAct | Reasoning + Acting 模式，思考-行动-观察循环 |
| HITL | Human-In-The-Loop，人工介入审批 |
| RAG | Retrieval-Augmented Generation，检索增强生成 |
| SOP | Standard Operating Procedure，标准操作流程 |
| MCP | Model Context Protocol，模型上下文协议 |
| A2A | Agent-to-Agent，Agent 间通信协议 |
| ACP | Agent Communication Protocol，现有系统使用的 JSON-RPC 协议 |
| LRU | Least Recently Used，最近最少使用淘汰算法 |
| TypedDict | Python 类型化字典，键值类型可在类型检查时验证 |
| MMR | Maximum Marginal Relevance，最大边际相关性，ChromaDB 内置重排序近似 |
| StateGraph | LangGraph 的有状态图模型，节点操作共享类型化状态 |
| Checkpointer | LangGraph 的状态检查点，支持 SQLite/PostgreSQL/Redis |
