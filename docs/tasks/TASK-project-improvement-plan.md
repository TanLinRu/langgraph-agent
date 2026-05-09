# 项目改进计划

## 目标
根据代码审查结果，制定系统性的改进计划

## 当前状态
- 70 个测试通过
- 功能基本完善，但存在架构和安全问题

## 改进计划

### Phase 1: P0 关键修复 (安全/死代码)

#### 1.1 删除死代码
- **文件**: server.py:844-874
- **问题**: return 后未执行的代码
- **状态**: 待处理

#### 1.2 输入验证增强
- **文件**: server.py:152-155 (ChatRequest)
- **修改**: 添加 max_length=10000
- **状态**: 待处理

#### 1.3 CORS 配置
- **文件**: server.py:143-149
- **修改**: 改用环境变量控制允许的 origin
- **状态**: 待处理

#### 1.4 路径验证增强
- **文件**: src/agent/tools/__init__.py:219-223
- **修改**: 使用 path canonicalization + 白名单
- **状态**: 待处理

### Phase 2: P1 架构改进

#### 2.1 健康检查端点
- **文件**: server.py
- **新增**: GET /health, GET /ready
- **状态**: 待处理

#### 2.2 重试机制
- **文件**: src/agent/agent.py
- **新增**: tenacity 指数退避 (3 次重试)
- **状态**: 待处理

#### 2.3 依赖注入重构
- **文件**: server.py
- **修改**: 全局单例改用 app.state
- **状态**: 待处理

#### 2.4 速率限制
- **文件**: server.py
- **新增**: slowapi 限流
- **状态**: 待处理

### Phase 3: P2 性能优化

#### 3.1 日志优化
- **文件**: src/agent/agent.py:284-293
- **修改**: 减少热路径日志输出
- **状态**: 待处理

#### 3.2 JSONL 优化
- **文件**: src/agent/context/long_term.py:186-197
- **修改**: 添加索引或缓存
- **状态**: 待处理

### Phase 4: 测试补充

#### 4.1 新增测试
- orchestrator_v2.py - DynamicOrchestrator
- supervisor.py - SupervisorManager
- acp_client.py - ACP 客户端
- server.py - API 端点

## 执行顺序

1. Phase 1 (P0) - 必须先做，安全相关
2. Phase 2 (P1) - 架构改进
3. Phase 3 (P2) - 性能优化
4. Phase 4 - 测试补充

## 验收标准

- [ ] P0 问题全部修复
- [ ] P1 问题至少完成 50%
- [ ] 所有修改通过测试
- [ ] 无新 lint 警告