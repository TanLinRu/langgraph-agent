# 产品/运营业务场景 + Chat UI 指标增强 - 实施计划

> 创建时间：2026-05-05
> 状态：已完成

---

## 一、背景

### 业务需求

1. **产品/运营业务场景**后续接入：
   - 运营自动化：客服机器人、工单处理、CRM 操作
   - 产品分析：数据分析、报表生成
   - PRD 可视化设计：产品需求文档 → 流程图 → HTML 原型

2. **Chat UI 侧边栏指标看板**：
   - 任务 Graph 进度
   - Token 消耗、费用
   - Agent/Skill 状态与可用列表

### 现状分析

| 模块 | 现状 |
|------|------|
| 后端 metrics | `agent.get_metrics()` 返回全局累计指标，未返回 per-turn 详情 |
| Chat UI | 已接收 metrics 数据但未展示 |
| 侧边栏面板 | 有 TaskProgressPanel、SkillTriggerPanel、AgentActivityPanel |
| 类型定义 | `ExecutionMetrics` 已定义但未使用 |

---

## 二、实施计划

### 阶段 1：基础指标增强（1-2 周）

#### 1.1 后端增强

| 任务 | 说明 | 涉及文件 |
|------|------|---------|
| T1.1.1 | 扩展 per-turn metrics：prompt_tokens, completion_tokens, cost, step_details | `src/agent/agent.py` |
| T1.1.2 | 新增 `/api/execution/current` API：返回当前任务的 flow graph 状态 | `server.py` |
| T1.1.3 | 新增 `/api/registry/tools` API：返回已注册的 tools/skills 列表 | `server.py` |
| T1.1.4 | SSE step 事件：推送 step 开始/结束事件 | `src/agent/event_callback.py` |

#### 1.2 前端增强

| 任务 | 说明 | 涉及文件 |
|------|------|---------|
| T1.2.1 | 新增 MetricsPanel：展示 token 消耗、费用、耗时统计 | `ui/src/components/dashboard/MetricsPanel.vue` |
| T1.2.2 | 新增 ToolsPanel：展示可用 tools/skills 列表 | `ui/src/components/dashboard/ToolsPanel.vue` |
| T1.2.3 | Dashboard store 对接新 API | `ui/src/stores/dashboard.ts` |
| T1.2.4 | 现有面板增强：TaskProgressPanel 显示 flow graph |

---

### 阶段 2：产品/运营场景接入（3-4 周）

#### 2.1 SOP 模板库

| 模板 | 说明 |
|------|------|
| SOP-CRM-001 | 客服工单处理流程 |
| SOP-CRM-002 | CRM 客户跟进流程 |
| SOP-DATA-001 | 数据分析报表流程 |

#### 2.2 Workflow 模板

| Workflow | 说明 |
|----------|------|
| workflow-crm-ticket | 工单处理 Workflow |
| workflow-data-analysis | 数据分析 Workflow |

#### 2.3 Agent 能力配置

| Agent | 说明 |
|-------|------|
| crm-agent | CRM 操作 Agent |
| data-analyst-agent | 数据分析 Agent |
| prd-designer-agent | PRD 设计 Agent |

---

### 阶段 3：PRD 可视化设计（5-6 周）

#### 3.1 完整流程

```
用户输入 PRD → AI 评审 → 流程设计 → UI 原型生成 → HTML 编辑导出
```

#### 3.2 新增模块

| 模块 | 说明 |
|------|------|
| PRD 输入组件 | 结构化需求收集 |
| AI 评审 Agent | 需求完整性评估 |
| 流程设计 Engine | 生成可视化流程图 |
| HTML 生成器 | 输出可编辑 HTML |
| Workflow: PRD-design | PRD 设计流程模板 |

---

## 三、API 设计

### 3.1 新增 API 端点

#### GET /api/registry/tools

返回所有已注册的工具和技能。

```json
{
  "tools": [
    { "name": "Bash", "description": "执行 Shell 命令", "category": "system" },
    { "name": "Read", "description": "读取文件", "category": "system" }
  ],
  "skills": [
    { "name": "code-review", "description": "代码审查", "category": "development" }
  ],
  "agents": [
    { "name": "default", "description": "默认 Agent" }
  ]
}
```

#### GET /api/execution/current

返回当前任务的执行状态。

```json
{
  "execution_id": "exec-xxxx",
  "status": "running",
  "current_step": 2,
  "total_steps": 5,
  "graph": {
    "nodes": [...],
    "edges": [...]
  },
  "metrics": {
    "prompt_tokens": 1500,
    "completion_tokens": 500,
    "total_tokens": 2000,
    "cost_usd": 0.02
  }
}
```

#### SSE /api/events/stream 事件类型（新增）

| 事件类型 | 说明 |
|---------|------|
| step_start | 步骤开始 |
| step_complete | 步骤完成 |
| metrics_update | 指标更新 |

---

### 3.2 前端面板设计

#### MetricsPanel

```
┌─────────────────────────────┐
│ 📊 指标概览              │
├─────────────────────────────┤
│ Token 消耗    │ 2,000     │
│ 费用       │ $0.02      │
│ 耗时       │ 5.2s      │
│ LLM 调用   │ 3 次      │
│ 压缩次数   │ 0 次      │
└─────────────────────────────┘
```

#### ToolsPanel

```
┌─────────────────────────────┐
│ 🔧 可用工具                │
├─────────────────────────────┤
│ 系统工具                  │
│ ├── Bash                  │
│ ├── Read                 │
│ ├── Edit                │
│ ├── Glob               │
├─────────────────────────────┤
│ 技能                    │
│ ├── code-review         │
│ ├── tdd-guide          │
├─────────────────────────────┤
│ Agents                  │
│ ├── default            │
│ └── opencode-agent     │
└─────────────────────────────┘
```

---

## 四、任务清单

### 阶段 1

- [x] T1.1.1 后端 per-turn metrics 扩展
- [x] T1.1.2 /api/execution/current API
- [x] T1.1.3 /api/registry/tools API
- [x] T1.1.4 SSE step 事件
- [x] T1.2.1 MetricsPanel 前端组件
- [x] T1.2.2 ToolsPanel 前端组件
- [x] T1.2.3 Dashboard store 更新
- [x] T1.2.4 TaskProgressPanel 增强

### 阶段 2

- [x] T2.1 SOP 模板库（3 个）
- [x] T2.2 Workflow 模板（2 个）
- [x] T2.3 Agent 配置（3 个）

### 阶段 3

- [x] T3.1 PRD 输入组件
- [x] T3.2 AI 评审 Agent
- [x] T3.3 流程设计 Engine
- [x] T3.4 HTML 生成器
- [x] T3.5 PRD-design Workflow

---

## 五、完成总结

### 阶段 1：基础指标增强
| 任务 | 文件 |
|------|------|
| per-turn metrics | `src/agent/agent.py` |
| /api/execution/current | `server.py` |
| /api/registry/tools | `server.py` |
| MetricsPanel | `ui/src/components/dashboard/MetricsPanel.vue` |
| ToolsPanel | `ui/src/components/dashboard/ToolsPanel.vue` |

### 阶段 2：产品/运营场景
| 任务 | 实现 |
|------|------|
| Workflow 模板 | 4 个新 workflow（工单/CRM/数据/PRD） |
| Agent 配置 | 3 个新 agent（CRM/Data/PRD） |

### 阶段 3：PRD 可视化
| 任务 | 实现 |
|------|------|
| PRD 输入组件 | `ui/src/components/dashboard/PRDInputPanel.vue` |
| flow_design skill | `src/agent/skills/__init__.py` |
| html_prototype skill | `src/agent/skills/__init__.py` |
| wf-prd-design workflow | `workflows.json` |
3. **时间期望**：第一版交付时间