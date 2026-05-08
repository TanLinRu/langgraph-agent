# 任务：消息去重 + 工作流流式展示 + 中断恢复 + 子Agent审查

## 任务目标

1. 修复消息重复问题（前后端）
2. 工作流流式展示（SSE）+ 中断 + 恢复
3. Main Agent 审查子 Agent 响应（拦截/回调机制）

## 当前进度

### Phase 1: 消息去重
- [x] 后端：AgentState messages 去重 (_deduplicate_messages in agent.py)
- [x] 后端：long_term.py save/load 去重
- [x] 前端：chat.ts loadSession 去重

### Phase 2: 工作流流式 + 中断恢复
- [x] 后端：新增 /api/execution/{id}/interrupt 端点
- [x] 后端：新增 /api/execution/{id}/resume 端点
- [x] 后端：SupervisorManager 添加 interrupt/resume 方法
- [x] 前端：agents.ts 添加 runStream, interruptExecution, resumeExecution
- [ ] 前端 UI：添加中断/恢复按钮（需在组件中使用）

### Phase 3: 子Agent审查机制
- [x] 后端：新增 review_agent_response() 方法 (SupervisorManager)
- [x] 后端：在 run() 中集成审查（通过 AGENT_REVIEW_ENABLED 环境变量启用）
- [x] 前端：AgentsTab.vue 添加中断/恢复按钮

## 下一步计划

从 Phase 1 开始：消息去重

## 关键决策点

- 消息重复原因：AgentState 使用 operator.add 导致同一条消息多次 append
- 审查机制：子Agent执行完后，触发主LLM进行审查，通过则继续，失败则重试