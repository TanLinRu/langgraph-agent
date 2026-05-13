# LangGraph Agent — Architecture Optimization Report

## Context

This document analyzes the current architecture of `D:\project\ai\langgraph-agent` across four dimensions (context management, competitive moats, intelligent orchestration, full-chain observability) and provides prioritized improvement recommendations.

---

## 一、现状总评

| 维度 | 现状 | 评分 | 说明 |
|------|------|------|------|
| 上下文管理 | 较好 | ⭐⭐⭐⭐ | LLM 压缩 + SQLite/ChromaDB + 7天归档，机制完整 |
| 护城河 | 一般 | ⭐⭐⭐ | 靠 OpenCode CLI 集成和 SOP 流程，但缺壁垒级创新 |
| 智能编排 | 中等 | ⭐⭐⭐ | 三套编排模式并存，路由策略缺失，skills 未被充分复用 |
| 全链路设计 | 较好 | ⭐⭐⭐⭐ | EventBus + Metrics + Checkpoint，观测和恢复链路完整 |

---

## 二、上下文管理分析

### 2.1 现有机制

```
用户输入
  → init（加载长期记忆上下文）
  → think（LLM 推理）
  → execute（工具执行）
  → compress（70% 阈值触发 LLM 摘要压缩）
  → save（持久化到 SQLite + JSONL）
  → 归档（7天 TTL 自动清理）
```

### 2.2 优点
- **多层分离**：压缩（短期）→ 长期记忆（SQLite）→ 归档，三层职责清晰
- **语义搜索**：ChromaDB 向量检索支持相似会话召回
- **断点恢复**：`initialization.py` 启动时自动恢复最近会话

### 2.3 不足与优化方向

| 问题 | 现状 | 优化方向 |
|------|------|---------|
| 无上下文优先级 | 所有消息一视同仁 | 引入重要性评分，优先保留关键决策点、用户确认、工具结果 |
| 压缩触发僵硬 | 固定 70% 阈值 | 动态阈值：根据任务类型（代码生成 > 对话）调整 |
| 向量检索粗糙 | 直接相似度匹配 | 引入 RAG pipeline：query 重写 → 召回 → 重排 |
| 无上下文验证 | 发给 LLM 前无校验 | 增加 context budget 检查，超限强制摘要或截断 |
| 单机存储 | 文件系统依赖 | 长期应支持 PostgreSQL（向量插件）+ Redis |

---

## 三、护城河分析

### 3.1 现有壁垒

| 壁垒 | 实现方式 | 强度 |
|------|---------|------|
| OpenCode 集成 | ACP/CLI 协议，外部编辑器作为执行引擎 | ⭐⭐⭐ 中等 |
| SOP 流程 | 状态持久化 + 多模板支持 | ⭐⭐⭐ 中等 |
| 多工具链 | 11 个 LangChain tools + 13 个 Skills | ⭐⭐⭐ 中等 |
| Vue Flow 可视化 | 编排 DAG 实时可视化 | ⭐⭐⭐ 中等 |

### 3.2 不足与优化方向

| 问题 | 优化方向 |
|------|---------|
| 壁垒不够深 | 需要积累**领域专属的工作流模板库**（不是代码，是经过验证的最佳实践流程） |
| Skills 复用率低 | DynamicOrchestrator 目前几乎不用 SKILLS_REGISTRY，应该把 skills 作为 DAG 节点 |
| 无数据飞轮 | 每次执行结果没有反馈到知识库，长期价值无法积累 |
| 缺乏可解释性 | Agent 每步决策没有结构化日志，难以审计和优化 |

---

## 四、智能编排设计分析

### 4.1 三套编排模式现状

```
┌─────────────────────────────────────────────────────────┐
│                    用户请求入口                           │
└──────────────────────┬──────────────────────────────────┘
                       │
              task_classifier.py（简单分类：简单/复杂）
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    单 Agent         Supervisor       Dynamic
    Agent.run()    Manager         Orchestrator
    (/chat)       (/api/execution)  (/api/orchestrate)
```

| 模式 | 触发条件 | 特点 | 问题 |
|------|---------|------|------|
| 单 Agent | 简单任务 | 直接执行，无 DAG | 无法处理多步骤任务 |
| SupervisorManager | 预定义图 | 静态 DAG，LLM 路由 | 需要预先配置，无法动态生成 |
| DynamicOrchestrator | 复杂任务 | LLM 动态生成 DAG，可回滚重规划 | Skills 未接入，计划不稳定时好时坏 |

### 4.2 核心问题：路由策略缺失

`task_classifier.py` 只做简单/复杂二分类，实际上：

```
问题 1: 三套入口完全独立，用户/调用方必须手动选择
问题 2: DynamicOrchestrator 不使用 SKILLS_REGISTRY
问题 3: SupervisorManager 的图需要预定义，无法动态注册
问题 4: 三个模式的输出格式不统一，无法互相替代
```

### 4.3 优化方向：统一智能编排层

```
用户请求
    ↓
自适应编排引擎（新增）
    ├── 分析任务类型
    ├── 查询 Skills 库匹配
    ├── 查询历史最佳实践
    ├── 选择执行路径：
    │     简单任务 → 单 Agent（< 3 步）
    │     中等任务 → SupervisorManager（已知 DAG）
    │     复杂任务 → DynamicOrchestrator（未知 DAG）
    └── 执行 + 记录到知识库
```

**关键实现**：
1. `orchestration_router.py`（新增）：统一的路由策略，根据任务特征、上下文复杂度、Skills 匹配度自动选择编排模式
2. Skills 必须作为 DAG 节点接入 DynamicOrchestrator
3. 每个执行路径的结果都反馈到"最佳实践库"供后续参考

---

## 五、全链路设计分析

### 5.1 现有链路

```
用户输入
  → HTTP/FastAPI
    → EventBus（SSE 实时推送）
    → MetricsCollector（指标收集）
    → LangGraph Checkpoint（状态快照）
    → OrchestratorCheckpoint（编排状态）
    → SQLite/ChromaDB（持久化）
      → 前端 SSE 消费
```

### 5.2 优点
- **观测完善**：EventBus 覆盖所有关键事件类型
- **容错健全**：circuit breaker + retry + graceful degradation 三重保护
- **Checkpoint 恢复**：OrchestratorCheckpoint 支持从断点恢复

### 5.3 不足与优化方向

| 问题 | 现状 | 优化方向 |
|------|------|---------|
| 无 trace ID | 各组件事件独立，没有统一请求链 ID | 引入 `trace_id`，贯穿所有日志和事件 |
| 无端到端审计 | 操作日志分散在各个模块 | 增加 `audit_log.py`，记录谁、什么时间、做了什么 |
| 无 API 认证 | 所有端点公开 | 增加 API Key / JWT 认证层 |
| 无 API 限流 | 端点无保护 | 增加 FastAPI 限流中间件 |
| Checkpoint 粗糙 | 只在步骤级别 | 增加到**原子操作级别**的快照 |
| 前端观测弱 | Dashboard 只是事件列表 | 增加实时 DAG 可视化时间线、Token 消耗曲线 |

---

## 六、优先优化建议（按价值和可行性排序）

### Phase 1：高价值 + 低风险（立即可做）

#### P1-1：统一智能编排路由层
- **文件**：`src/agent/orchestration_router.py`（新增）
- **内容**：
  - 统一入口，根据任务复杂度、Skills 匹配度、上下文长度自动路由到最合适的编排模式
  - 合并三个 API 端点为一个 `/api/agent/run`
  - Skills 强制作为 DAG 节点接入 DynamicOrchestrator
- **验证**：发送不同复杂度任务，确认自动路由到对应模式

#### P1-2：引入 trace_id 全链路追踪
- **文件**：`src/agent/trace_context.py`（新增）+ 各模块修改
- **内容**：每个请求生成 UUID，贯穿 EventBus / Metrics / Checkpoint 所有事件
- **验证**：一次请求的所有事件都有相同的 trace_id

#### P1-3：Skills 全面接入 DynamicOrchestrator
- **文件**：`src/agent/orchestrator_v2.py`（修改 `PLAN_SYSTEM_PROMPT`）
- **内容**：计划时充分利用 SKILLS_REGISTRY，Skills 对应具体 DAG 节点
- **验证**：发送一个需要代码审查+安全审计的任务，确认 DAG 自动生成包含这两个 Skill

### Phase 2：高价值 + 中风险（需要设计）

#### P2-1：上下文重要性评分
- **文件**：`src/agent/context/prioritizer.py`（新增）
- **内容**：
  - 对每条消息打分：用户确认 > 工具结果 > LLM 推理 > 系统消息
  - 压缩时优先保留高评分消息
  - 支持手动"钉住"关键上下文不被压缩
- **验证**：相同任务两次执行，钉住关键消息后结果更准确

#### P2-2：API 认证 + 限流
- **文件**：`src/agent/middleware/auth.py`（新增）+ `server.py`
- **内容**：API Key 认证 + per-user 限流
- **验证**：无 API Key 请求返回 401，带正确 Key 才能访问

#### P2-3：审计日志
- **文件**：`src/agent/audit_log.py`（新增）
- **内容**：记录所有写操作（文件修改、工具执行、workflow 创建/删除）
- **验证**：执行写操作工具，查询审计日志有记录

### Phase 3：长期价值（需要较大改动）

#### P3-1：分布式存储支持
- PostgreSQL（pgvector）替代 SQLite/ChromaDB
- Redis 替代 JSONL 文件
- 支持多实例部署

#### P3-2：数据飞轮
- 执行结果自动入库
- 相似任务自动推荐历史最佳实践
- Skill 使用效果追踪和排名

#### P3-3：可解释性引擎
- 结构化决策日志（每步为什么选这个 Agent/Skill）
- 生成执行报告（类似 git bisect 的报告）
- 用户可导出/分享执行过程

---

## 七、总结

| 优先级 | 优化项 | 价值 | 改动范围 |
|--------|--------|------|---------|
| P1-1 | 统一智能编排路由 | 高 | 新增 1 文件 |
| P1-2 | trace_id 全链路追踪 | 高 | 跨多个文件 |
| P1-3 | Skills 全面接入 Orchestrator | 高 | 改 1 个文件 |
| P2-1 | 上下文重要性评分 | 中高 | 新增 1 文件 |
| P2-2 | API 认证 + 限流 | 中高 | 新增 1 + 改 server.py |
| P2-3 | 审计日志 | 中 | 新增 1 文件 |
| P3-1 | 分布式存储 | 中低 | 较大重构 |
| P3-2 | 数据飞轮 | 高 | 新增多个文件 |
| P3-3 | 可解释性引擎 | 中 | 新增 1 文件 |

**核心建议**：先做 P1 三项，它们不改架构，只增强现有模块，能显著提升系统智能度和可观测性，且风险最低。
