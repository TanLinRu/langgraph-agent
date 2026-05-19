# alignment-plan.md — v2 审查补充

> 本文档包含 6 项补充内容，请手动合并到 `docs/architecture/alignment-plan.md`。

---

## 补充 1: `schemas/__init__.py` 需随 T19 更新

T2 创建 `schemas/__init__.py` 时未包含 `tool_result.py`。T19 创建 `schemas/tool_result.py` **后，必须同步更新 `schemas/__init__.py`** 导出 `ToolResult`。

```python
# T19 完成后，在 schemas/__init__.py 添加:
from .tool_result import ToolResult

__all__.extend(["ToolResult"])
```

**插入位置**: P4.1 (T19) 代码块之后，原表格之前。

---

## 补充 2: P3 压缩返回类型变更 — 波及调用者

T17 将 `compress()` 返回类型从 `list` **改为 `CompressionResult`**，以下调用点需同步更新:

| 位置 | 改动 |
|------|------|
| `agent.py:_node_compress` | 解包 `result.compressed_messages` 而非直接用 result |
| `agent.py` 中所有 `compressor.compress()` 调用 | 解包新结构 |
| 测试代码中 mock `compress()` 返回值 | 改为返回 `CompressionResult` |

**插入位置**: P3.1 验收标准之后，P3.2 之前。

---

## 补充 3: 幂等键缓存存储位置

T21 的 `_cache_idempotent_result()` / `_get_idempotent_result()` 未指定后端。方案:

```
存储: Agent 实例级 dict（内存）
  ├── _idempotent_cache: dict[str, dict]  # tool_call_id → result
  ├── TTL: 不主动过期（session 生命周期内有效）
  ├── 上限: 最多缓存 1000 条，超过时淘汰最早条目
  └── 线程安全: threading.Lock 保护
```

如需跨 session 持久化，后续可迁移到 SQLite。

**插入位置**: P4.2 (T21) 实现任务之后，验收标准之前。

---

## 补充 4: 边界情况

| 场景 | 处理策略 | 优先级 |
|------|---------|--------|
| `OPENAI_API_KEY` 缺失 | `_get_or_create_trace_id` 中的 `generate_trace_id()` 使用 `uuid4()` 回退 | P0 |
| Python 3.10+ 兼容 | `X \| None` 语法 → `Optional[X]` | P1 |
| 现有调用者迁移 | `main.py`、`graph.py`、`opencode_agent.py` 中 `run()` 返回值处理 | P2 |
| 多线程安全 | `_idempotent_cache` 使用 `threading.Lock` | P2 |

**插入位置**: 验收标准总览之后，P1 之前。

---

## 补充 5: 测试业务范畴标注

P8 测试文件清单增加 `业务范畴` 和 `优先级` 列:

| 文件 | 覆盖内容 | 数量 | 业务范畴 | 优先级 |
|------|---------|------|---------|--------|
| `tests/test_error_envelope.py` | ErrorEnvelope 构造/序列化 | 8 | Unit | P0 |
| `tests/test_error_integration.py` | structured_catch 装饰器 | 4 | Integration | P0 |
| `tests/test_structured_catch.py` | 装饰器功能 | 7 | Unit | P1 |
| `tests/test_retry_handler.py` | 重试机制 | 8 | Unit | P1 |
| `tests/test_retry_integration.py` | 重试接入执行路径 | 4 | Integration | P1 |
| `tests/test_no_swallowed_exceptions.py` | 无吞没异常 | 5 | Integration | P1 |
| `tests/test_agent_protocol.py` | AgentInput/Output 契约 | 8 | Integration | P0 |
| `tests/test_agent_routing.py` | max_steps/max_iterations 路由 | 5 | Unit | P1 |
| `tests/test_agent_lifecycle.py` | pause/resume/abort | 6 | Unit | P2 |
| `tests/test_human_in_loop.py` | HITL Bug 修复验证 | 7 | Unit + Bugfix | **P0** |
| `tests/test_tool_results.py` | 结构化 ToolResult | 10 | Unit | P2 |
| `tests/test_idempotency_key.py` | 幂等键机制 | 4 | Unit | P2 |
| `tests/test_compression.py` | CompressionResult 结构化 | 6 | Unit | P1 |
| `tests/test_long_term.py` | 存储异常处理 | 4 | Unit | P1 |
| `tests/test_supervisor.py` | Supervisor 结构化错误 | 4 | Unit | P2 |
| `tests/test_api_error_format.py` | API 错误格式统一 | 5 | E2E | P3 |

---

## 补充 6: 实施顺序变更

**严格按阶段顺序执行**：P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8

```
P1 (基础协议层)
 ├── T1  schemas/agent_protocol.py  ← 第一个创建（解决循环依赖）
 ├── T2  schemas/__init__.py
 ├── T3  structured_catch 装饰器
 ├── T4  retry_handler 增强
 ├── T5  agent.py 接入重试
 ├── T7  tools/__init__.py:213 修复吞没
 └── T8  orchestrator_checkpoint.py:141 修复吞没
 │
 ▼
P2 (Agent 层对齐)
 ├── T9   AgentInput/Output 重构
 ├── T10  state.py 添加 step_count 字段
 ├── T11  config.py max_steps 配置
 ├── T12  _should_continue 检查步数
 ├── T13  step_count 递增
 ├── T14  pause/resume/abort
 ├── T15  human_in_loop.py Bug 修复 ← 从 P0 移入
 └── T16  orchestrator_v2.py Bug 修复
 │
 ▼
P3 (上下文系统)
 ├── T17  CompressionResult.errors 字段
 └── T18  long_term.py 异常处理
 │
 ▼
P4 (工具层)
 ├── T19  schemas/tool_result.py
 └── T20  所有工具结构化返回
 │
 ▼
P5 (编排层)
 ├── T21  agent.py 幂等键
 ├── T22  supervisor.py ErrorEnvelope
 └── T23  orchestrator_v2.py 重试
 │
 ▼
P6 (ACP/CLI)
 ├── T24  acp_server.py ErrorEnvelope
 └── T25  acp_client.py 错误解析
 │
 ▼
P7 (API 层)
 └── T26  server.py 统一中间件
 │
 ▼
P8 (测试覆盖)  ← 贯穿全程，每个 T 后写测试
```
