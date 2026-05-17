# TASK: Context Design Gap Fix

**Task**: 修复 `context_design.md` 与实际实现的差距  
**Created**: 2025-05-13  
**Last Updated**: 2025-05-17  
**Status**: In Progress

---

## Goal
1. **代码-文档对齐（P1-P8）**：按 `agent-flow-design.md` 规范修改已有代码，覆盖 8 个阶段
2. **低开销验证基础设施**：默认 Mock 测试，通过环境变量切换真实 API
3. **可观测性基础设施**：双通道日志、结构化 JSONL 输出、内容级 DEBUG
4. **Model 修复**：DashScope API 兼容修正 `openai:qwen3.5-flash` → `qwen3.5-flash`

---

## Constraints & Preferences
- 严格按阶段顺序：P1→P2→...→P8
- 每个阶段必须有对应的测试用例
- `docs/architecture/alignment-plan.md` 为标准（已合并 6 个补充说明）
- 低开销验证：默认 mock，通过 `CONTEXT_USE_REAL_API=true` 启用真实 API

---

## Progress

### 已完成

#### P1-P4 代码改造
- **P1（基础协议层）** — 30/30 测试通过
- **P2（Agent 层）** — 60+ 测试通过
- **P3（上下文系统）** — 27 测试通过
- **P4（工具层）** — 17 测试通过

#### 可观测性基础设施（2025-05-17）
- `context-log-diagnosis.py`：双通道日志（stdout INFO + 文件 DEBUG），默认 mock，Real API 通过 `$env:CONTEXT_USE_REAL_API="true"` 切换
- `compression.py`：`_dump_messages_debug()` 内容级日志，逐条打印消息内容
- `agent.py`：`_node_think` DEBUG 日志，打印完整 LLM 请求/响应
- `conftest.py`：pytest 文件日志 → `logs/pytest-{timestamp}.log`
- JSONL 输出：`logs/context-verify-{timestamp}.jsonl`
- `logs/` 目录 + `.gitkeep`

#### 阈值调整
- 测试级：`trigger_threshold=0.1`（500 tokens 触发）
- 生产级：0.7（89600 tokens）

#### 验证结果
- **Mock 验证**：3/3 通过
  - 压缩：7 条消息/758 tokens → 4 条消息/590 tokens（省 22.2%）
  - 多轮对话：3 轮/414 tokens
  - 长时记忆：session save+load
- **Real API 验证**：3/3 ✅ 通过
  - LLM Enrich/Summarize 200 OK
  - Model 修复：`.env` 中 `AGENT_MODEL=openai:qwen3.5-flash` → `qwen3.5-flash`

### 进行中
- *（无）*

### 阻塞
- *（无）*

---

## 剩余工作（P5-P8，未来阶段）

| 阶段 | 任务 | 文件 | 说明 |
|------|------|------|------|
| P5 | T21 | `agent.py` | 幂等键（`_idempotent_cache`） |
| P5 | T22 | `supervisor.py` | ErrorEnvelope 包装（`state.error = env.to_dict()`） |
| P5 | T23 | `orchestrator_v2.py` | 接入 `@retry_with_backoff` 装饰器 |
| P6 | T24 | `acp_server.py` | JSON-RPC 错误格式（`error=env.to_jsonrpc()`） |
| P6 | T25 | `acp_client.py` | 错误码解析（`result["error"]` 结构） |
| P7 | T26 | `server.py` | 统一错误中间件（StructuredAgentError → JSONResponse） |
| P8 | — | 13 个测试文件 | 约 91 个新增测试用例 + 3 个 Real API 测试 |

---

## Key Decisions
- `ToolResult.to_dict()` 统一：LangChain @tool 装饰器返回 dict，非 dataclass
- `compress()` 返回 `CompressionResult`：所有调用方解包 `.compressed_messages`
- `pytest.ini` 替代 `pyproject.toml`：避免与 langsmith `pytest_configure` 冲突
- 测试阈值 0.1（500 tokens），生产阈值 0.7（89600 tokens）

---

## Critical Context
- Python 3.13.12, pytest 9.0.3, Windows GBK（终端 emoji 编码异常，写入文件正常）
- 已有失败用例：`test_acp.py::test_initialize`（缺少凭证）
- 测试汇总：191 通过，1 失败（ACP），15 跳过
- `ruff`/`mypy` 未安装 —— 改用 import 验证
- 多轮 `agent.run()` 返回 `result["result"]["messages"]`
- `LongTermManager.save_session(thread_id, messages, metadata)`

---

## Context 差距清单

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

## 实现计划（未完成部分）

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

### Fix #3: smart_message_reducer 实现

**目标**: 对消息列表实施上限保护，防止无限增长

**修改文件**:
- `src/agent/context/compression.py` — 实现 `smart_message_reducer`

**验收标准**:
- 消息数量超过阈值时自动触发压缩
- 保留最新 N 条 + 摘要

---

## Relevant Files
- `pytest.ini`：11 个 markers
- `tests/conftest.py`：15+ fixtures + pytest 文件日志
- `tests/plugins/test_logger.py`：ResultCollector 插件
- `docs/context/context-log-diagnosis.py`：双通道验证脚本（mock + real API）
- `src/agent/context/compression.py`：`_dump_messages_debug()` 内容级日志
- `src/agent/agent.py`：`_node_think` DEBUG 日志
- `logs/`：日志输出目录
- `docs/architecture/alignment-plan.md`：标准文档（8 个阶段，P1-P4 已完成）
- `docs/architecture/agent-flow-design.md`：架构规范原始文档

---

## 验证命令

```bash
# Mock 验证（默认）
python docs/context/context-log-diagnosis.py

# Real API 验证
$env:CONTEXT_USE_REAL_API="true"; python docs/context/context-log-diagnosis.py

# 查看日志
Get-Content "logs/context-verify-*.log" -Tail 50 -Wait

# pytest 测试
python -m pytest tests/ -v
```