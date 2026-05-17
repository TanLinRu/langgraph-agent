# LangGraph Agent

> 生产级代码开发与数据处理 Agent，支持多 Agent 编排、SOP 流程、产品/运营场景

## 快速开始

```bash
# 安装
pip install -e .

# 配置
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY

# CLI 运行
python -m src.agent.main --input "写一个快速排序"
python -m src.agent.main --interactive
python -m src.agent.main --archive        # 归档清理
python -m src.agent.main --acp        # ACP 服务模式

# API 服务 (Terminal 1)
python server.py

# 前端 (Terminal 2)
cd ui && npm install && npm run dev
# 访问 http://localhost:3000
```

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Chat UI (Vue 3)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │Messages │ │Metrics  │ │Tools    │ │PRD Input       │  │
│  │Panel   │ │Panel   │ │Panel   │ │Panel           │  │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────────┬─────────┘  │
│       │          │          │             │              │          │
│       └──────────┴──────────┴────────────┴──────────────┘          │
│                            │                                  │
│                     SSE / HTTP                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      Server (FastAPI)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ /chat      │  │ /metrics   │  │ /api/exec   │ │
│  │ /archive   │  │ /skills   │  │ /workflows  │ │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘ │
│        │               │               │            │
│        └───────────────┴───────────────┴────────────┘ │
│                        │                         │
│         ┌──────────────▼──────────────┐         │
│         │  SupervisorManager        │         │
│         │  (多 Agent 编排)           │         │
│         └────────┬───────────────┘         │
│                  │                     │
│    ┌────────────┼─────────────────┐    │
│    │           │             │     │    │
│ ┌──▼──┐  ┌──▼──┐  ┌──▼──┐  │
│ │Agent│  │Agent│  │Agent│  │
│ │ #1 │  │ #2 │  │ #3 │  │
│ └──┬──┘  └──┬──┘  └──┬──┘  │
│    │          │          │       │
└────┼──────────┼──────────┼──────┘
     │          │          │
     └──────────┴──────────┘
             │
    ┌────────▼────────┐
    │   LangGraph   │
    │   StateGraph │
    └─────┬───────┘
          │
┌────────▼─────────────────────────────────────────────────────┐
│                   上下文管理                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ 压缩器      │  │ 长期记忆    │  │ 归档       │ │
│  │(70%阈值)   │  │(SQLite+     │  │(7天TTL)    │ │
│  │            │  │ChromaDB)   │  │            │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└────────────────────────────────────────────────────────┘
```

## 模块架构

### 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **Agent** | `src/agent/agent.py` | 主 Agent 类，LangGraph StateGraph 编排 |
| **Supervisor** | `src/agent/supervisor.py` | 多 Agent 编排管理器 |
| **Registry** | `src/agent/registry.py` | Agent/Graph 注册表 |
| **State** | `src/agent/state.py` | AgentState 定义 |
| **Config** | `src/agent/config.py` | Pydantic 配置 |

### 上下文管理 (`src/agent/context/`)

```
context/
├── __init__.py           # 导出入口
├── compression.py       # 上下文压缩器
├── long_term.py          # 长期记忆 (SQLite + ChromaDB)
├── tool_result_store.py  # 工具结果存储 (Hot Zone)
├── retrieval_trigger.py  # 检索触发器
├── initialization.py     # 上下文初始化器
└── archive.py            # 归档管理器
```

| 模块 | 职责 | 关键类 |
|------|------|--------|
| **compression** | 70% token 阈值触发压缩，LLM 摘要 | `ContextCompressor`, `CompressedTurn`, `CompressionResult` |
| **long_term** | SQLite 会话存储 + ChromaDB 向量检索 | `LongTermManager`, `LongTermConfig` |
| **tool_result_store** | 工具结果缓存，LRU+热度双因素淘汰 | `ToolResultStore`, `ToolResultSummary` |
| **retrieval_trigger** | 检索触发判断（token水位/任务类型/语义相似度） | `RetrievalTrigger` |
| **initialization** | 服务重启恢复上下文 | `ContextInitializer` |
| **archive** | 7天TTL会话归档 | `ArchiveManager` |

### 核心数据结构

```python
# AgentState (state.py)
{
    "messages": Annotated[list, smart_message_reducer],  # 消息列表
    "thread_id": str,                                     # 会话ID
    "task_status": Literal["pending", "in_progress", ...], # 任务状态
    "compression_count": int,                            # 压缩次数
    "token_usage": dict,                                 # token预算
    "hot_tool_results": list[ToolResultSummary],         # Hot Zone
    "injected_memory": list,                             # 注入记忆
}

# CompressedTurn (compression.py)
{
    "turn_index": int,           # 轮次索引
    "user_intent": str,          # 用户意图
    "key_facts": list[str],     # 关键事实 (LLM提取)
    "tool_actions": list[dict],  # 工具调用记录
    "unresolved": list[str],     # 未解决问题 (LLM提取)
    "compression_rationale": str, # 压缩原因
}

# CompressionConfig
{
    "max_tokens": 128000,        # 最大token
    "trigger_threshold": 0.7,    # 触发阈值 (70%)
    "keep_recent": 5,            # 保留最近轮次
    "summary_max_tokens": 500,  # 摘要最大token
    "hot_zone_size": 5,          # Hot Zone大小
}
```

### LangGraph StateGraph 节点

```
init → sop_resume → think
                        ↓
                    [tool_calls?]
                        ↓
                ┌──────┴──────┐
                │             │
              end          execute
                            ↓
                         compress
                            ↓
                           save
                            ↓
                        [task_status?]
                            ↓
                     ┌──────┴──────┐
                     │             │
                    end          think (loop)
```

| 节点 | 职责 | 关键逻辑 |
|------|------|----------|
| **init** | 初始化，避免重复添加 system 消息 | `_deduplicate_messages` |
| **sop_resume** | 检查并恢复 SOP 状态 | `load_sop_state` |
| **think** | LLM 调用 + token 追踪 + 检索触发 | `should_retrieve` |
| **execute** | 工具调用执行 | `TOOLS` registry |
| **compress** | 上下文压缩（70% 阈值） | `ContextCompressor.compress` |
| **save** | 会话持久化（SQLite + JSONL delta） | `LongTermManager.save_session` |

## 数据流

### 单次对话流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                    单次对话流程                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  用户输入 ──▶ init ──▶ sop_resume ──▶ think                         │
│     │                                                              │          │
│     │                                                         tools_call?    │
│     │                                                           │          │
│     │                                                      ┌──────┴─────┐  │
│     │                                                      │            │  │
│     │                                                     ┴▼─────────┐ │  │
│     │                                                     │ execute  │ │  │
│     │                                                     │ (工具执行) │ │  │
│     │                                                     └────┬──────┘ │  │
│     │                                                          │        │  │
│     │                                                     ┌────┴──────┐ │
│     │                                                     │ compress  │ │
│     │                                                     │(70%阈值) │ │
│     │                                                     └────┬──────┘ │
│     │                                                          │        │
│     │                                                  ┌────────┴────────┐ │
│     │                                                  │             │      │
│     │                                            save │         think   │      │
│     │                                           │      │        │      │
│     │                                      ┌────┴────┐   │  ┌────┴─────┐  │
│     └──────────▶│持久化 │◀─────│  │  │  继续循环 │  │
│                └────┬────┘   │  └────┬─────┘  │
│                     │       │       │       │       │
│                     └───────┼───────┴───────┘       │
│                         │                       │
│                    END ◀─────────────────────────
│
└─────────────────────────────────────────────────────────────────────┘
```

### 上下文压缩数据流

```
原始消息列表
    │
    ▼
┌───────────────────┐
│ should_compress() │  token_ratio >= 0.7 ?
└─────────┬─────────┘
          │ Yes
          ▼
┌─────────────────────────────────────────────────────────────┐
│  分类消息                                                     │
│  - system: 合并到单个 + 追加摘要                               │
│  - user/assistant: 构建 CompressedTurn 列表                   │
│  - tool: 存入 ToolResultStore (Hot Zone)                      │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  LLM 增强 (可选)                                             │
│  - _enrich_turns_with_llm(): 提取 key_facts, unresolved      │
│  - _llm_summarize_turns(): 生成摘要                          │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  保留策略                                                     │
│  - keep_recent: 最后 N 轮 user/assistant                     │
│  - hot_zone: ToolResultStore.get_hot_zone()                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
压缩后消息: [
  {role: "system", name: "context_summary",
   content: "原始系统提示 + 【之前对话摘要】...",
   compressed_turns: [...]},
  ...recent_messages,
  ...hot_zone_tool_results (is_hot_zone: true)
]
```

### 多轮对话状态持久化

```
┌───────────────────────────────────────────────────────┐
│                   多轮对话                             │
├───────────────────────────────────────────────────────┤
│                                                       │
│  Turn 1: run("你好")                                   │
│    ├─ init: 添加 system 消息                          │
│    ├─ think: LLM 调用                                 │
│    ├─ [无 tool_calls] → end                           │
│    └─ save: sessions/{thread_id}.jsonl (delta: 3条)   │
│                                                       │
│  Turn 2: run("今天天气")                                 │
│    ├─ init: 检测已有 system → skip                     │
│    ├─ think: 从 checkpointer 恢复消息                  │
│    ├─ execute: tool_calls                             │
│    ├─ compress: 压缩 (if token > 70%)                  │
│    └─ save: sessions/{thread_id}.jsonl (delta: N条)   │
│                                                       │
│  Turn N: resume                                        │
│    ├─ init: SqliteSaver.get() 恢复完整状态             │
│    └─ ...继续循环                                      │
│                                                       │
└───────────────────────────────────────────────────────┘
```

### 长期记忆数据流

```
┌─────────────────────────────────────────────────────────┐
│                 4层记忆模型                              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  L1: Working Memory ── State.messages (内存)            │
│                    │                                    │
│                    ▼                                    │
│  L2: Session ────── SqliteSaver + JSONL deltas           │
│                    │                                    │
│                    ▼                                    │
│  L3: Cross-session ─ Store + ChromaDB (./memory/chroma) │
│                    │                                    │
│                    ▼                                    │
│  L4: Organizational ─ External Services                 │
│                                                         │
└─────────────────────────────────────────────────────────┘

SQLite Schema:
  sessions(thread_id, tenant_id, org_id, user_id, ...,
           message_count, preview, metadata)
  memories(namespace, memory_key, value, current_value,
           value_history, conflict_type)
```

## 工具执行架构

### ToolResult 数据结构

```
┌─────────────────────────────────────────────────────────────┐
│                     ToolResult                               │
├─────────────────────────────────────────────────────────────┤
│  status: str           # "success" | "failed" | "partial" │
│  content: str           # 工具执行结果内容                    │
│  metadata: dict         # 附加信息 (rows, cols, etc)        │
│  error: ErrorEnvelope   # 错误详情 (可选)                    │
│  idempotency_key: str   # 幂等键                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     ErrorEnvelope                            │
├─────────────────────────────────────────────────────────────┤
│  error_code: str       # TOOL_EXEC_ERROR | TOOL_ARGUMENT_... │
│  error_type: str       # "recoverable" | "fatal"           │
│  message: str          # 错误消息                            │
│  retryable: bool       # 是否可重试                          │
│  retry_after_ms: int   # 重试间隔 (ms)                      │
│  trace_id: str         # 追踪ID                             │
│  context_snapshot: dict # 上下文快照                         │
│  fallback_action: str  # 降级策略                           │
│  error_level: int      # 错误级别                           │
│  timestamp: str        # ISO时间戳                           │
│  tool_name: str        # 工具名称                            │
│  step: int             # 执行步骤                            │
└─────────────────────────────────────────────────────────────┘
```

### 工具执行流程

```
think() 返回 tool_calls
        │
        ▼
┌───────────────────┐
│   _node_execute   │
│  (工具执行节点)    │
└─────────┬─────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│  幂等检查                                                       │
│  tool_call_id ──→ _idempotent_cache                         │
│  │ 如果存在 → 直接返回缓存结果 (跳过重复执行)                  │
│  │ 不存在 → 执行工具                                          │
│  LRU 淘汰: 缓存超过1000条时移除最旧条目                       │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│  工具返回 ToolResult.to_dict()                               │
│  {                                                           │
│    "status": "success" | "failed",                          │
│    "content": "...",                                         │
│    "metadata": {...},                                        │
│    "error": {...}  # failed时包含                            │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│  工具结果缓存                                                  │
│  - 缓存在 self._idempotent_cache 内存中                       │
│  - key: tool_call_id                                        │
│  - value: result_msg dict                                   │
│  - 同一 tool_call_id 在同一轮次内不会重复执行                   │
└─────────────────────────────────────────────────────────────┘
```

### 内置工具 (11个)

| 工具 | 说明 | 返回格式 |
|------|------|----------|
| `execute_code` | 执行 Python/Shell 代码 | `{"status": "success", "content": "...", "metadata": {...}}` |
| `read_file` | 读取文件内容 | `{"status": "success", "content": "...", "metadata": {"lines": N}}` |
| `write_file` | 写入文件内容 | `{"status": "success", "content": "已写入..."}` |
| `list_directory` | 列出目录文件 | `{"status": "success", "content": "..."}` |
| `search_files` | 搜索文件内容 | `{"status": "success", "content": "...", "metadata": {"matches": N}}` |
| `data_processor` | 数据处理 | `{"status": "success", "content": "...", "metadata": {...}}` |
| `dispatch_to_cli` | 分发到 CLI | `{"status": "success", "content": "...", "metadata": {...}}` |
| `dispatch_via_acp` | ACP 分发 | `{"status": "success", "content": "...", "metadata": {...}}` |
| `list_clis` | 列出 CLI | `{"status": "success", "content": "..."}` |
| `list_serves` | 列出服务 | `{"status": "success", "content": "..."}` |
| `stop_serve_tool` | 停止服务 | `{"status": "success", "content": "已停止..."}` |

### 错误码

| 错误码 | 说明 | 类型 | 可重试 |
|--------|------|------|--------|
| `TOOL_EXEC_ERROR` | 工具执行错误 | RECOVERABLE | ✅ |
| `TOOL_ARGUMENT_ERROR` | 参数错误 | FATAL | ❌ |
| `TOOL_NOT_FOUND` | 工具不存在 | FATAL | ❌ |
| `TOOL_EXEC_TIMEOUT` | 执行超时 | RECOVERABLE | ✅ |
| `TOOL_PERMISSION_DENIED` | 权限被拒 | FATAL | ❌ |

## 测试架构

### Mock vs Real API 切换

```bash
# Mock 模式（默认）
python -m pytest tests/ -v

# Real API 模式
USE_REAL_API=true python -m pytest tests/ -v
```

### Mock 数据模式

```python
# conftest.py - Mock LLM fixture
def _create_mock_llm():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(
        content="这是 AI 的回复",
        response_metadata={"prompt_tokens": 100, "completion_tokens": 50}
    )
    return llm

# Mock Agent (test_multi_turn_real.py)
@pytest.fixture
def mock_agent(tmp_path):
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = {
        "role": "assistant",
        "content": "Mock response",
        "tool_calls": [],
    }
    agent.llm = mock_llm
    return agent
```

### 测试数据结构

```python
# Mock 消息示例 (test_compression.py)
long_messages = [
    {"role": "system", "content": "你是助手" * 50},
    {"role": "user", "content": "写快排算法" * 20},
    {"role": "assistant", "content": "这是快排..." * 50},
    {"role": "tool", "tool_call_id": "call_1", "name": "execute_code",
     "content": "def quicksort..." * 20},
]

# Mock 压缩结果断言
compressed = compressor.compress(long_messages)
assert len(system_msgs) == 1
assert "【之前对话摘要】" in system_msgs[0]["content"]
assert "compressed_turns" in system_msgs[0]

# Mock CompressedTurn
CompressedTurn(
    turn_index=0,
    user_intent="用户请求实现快速排序",
    key_facts=["使用分治策略", "基准点选择"],
    tool_actions=[{"name": "execute_code", "status": "success"}],
    unresolved=["未测试空数组"],
)
```

### 测试文件列表

| 文件 | 测试内容 | Mock | Real |
|------|---------|------|------|
| `test_compression.py` | 压缩逻辑 | 5 | 3 |
| `test_context_integration.py` | 完整流程 | 10 | 2 |
| `test_multi_turn_real.py` | 多轮对话 | 12 | 4 |
| `test_agent_resume.py` | 会话恢复 | 2 | 2 |
| `test_retrieval_trigger.py` | 检索触发 | 3 | 1 |
| `test_long_term.py` | 长期存储 | 3 | 0 |

### Real API 测试标记

```python
def should_use_real_api():
    return os.getenv("USE_REAL_API", "false").lower() == "true"

@pytest.mark.skipif(
    not should_use_real_api(),
    reason="Requires USE_REAL_API=true"
)
def test_llm_summarize_real_api():
    ...
```

## 业务架构

```
┌─────────────────────────────────────────────────────────────────┐
│            产品/运营场景                                    │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐   │
│  │  客服工单处理 Workflow (wf-crm-ticket)              │   │
│  │  问题分类 → 智能回复 → 工单闭环                 │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  CRM 客户跟进 Workflow (wf-crm-followup)           │   │
│  │  客户画像 → 跟进计划 → 提醒设置                  │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  数据分析 Workflow (wf-data-report)              │   │
│  │  数据查询 → 统计分析 → 报表生成               │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  PRD 设计 Workflow (wf-prd-design)              │   │
│  │  需求分析 → 流程设计 → HTML 原型生成          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │
┌────────▼───────────────────────────────────┐
│          Agent 配置                                │
├───────────────────────────────────────┤
│  crm-agent       │ CRM 客户管理        │
│  data-analyst    │ 数据分析           │
│  prd-designer   │ PRD 设计          │
│  opencode-agent │ OpenCode 执行    │
└───────────────────────────────────────┘
```

## 项目结构

```
langgraph-agent/
├── src/agent/              # 核心代码
│   ├── agent.py           # Agent 主类
│   ├── registry.py       # Agent/Graph 注册
│   ├── supervisor.py    # 多 Agent 编排
│   ├── config.py      # 配置定义
│   ├── state.py       # 状态定义
│   ├── context/      # 上下文管理
│   │   ├── __init__.py           # 导出入口
│   │   ├── compression.py        # 压缩器 (ContextCompressor)
│   │   ├── long_term.py          # SQLite + ChromaDB
│   │   ├── tool_result_store.py  # Hot Zone
│   │   ├── retrieval_trigger.py  # 检索触发
│   │   ├── initialization.py    # 初始化
│   │   └── archive.py           # 归档
│   ├── skills/       # 技能系统
│   ├── tools/        # 工具集
│   ├── prompts/      # 系统提示
│   └── metrics*.py  # 指标收集
├── ui/                # Vue 3 前端
├── server.py           # FastAPI 后端
├── workflows.json     # Workflow 模板
├── memory/           # 会话存储
│   ├── sessions/      # JSONL delta
│   ├── sessions.db    # SQLite metadata
│   ├── memory/        # MEMORY.md
│   ├── chroma/        # 向量数据库
│   └── archive/       # 归档
├── tests/            # pytest (17+ tests)
│   ├── conftest.py              # Mock/Real API fixtures
│   ├── test_compression.py      # 压缩测试
│   ├── test_context_integration.py  # 集成测试
│   ├── test_multi_turn_real.py   # 多轮对话测试
│   ├── test_tool_results.py      # 工具结果格式测试
│   └── ...
└── docs/            # 文档
```

## 核心特性

### 1. 幂等工具执行
- `_idempotent_cache` 缓存同轮次工具结果
- 防止重复执行相同的 tool_calls
- LRU 淘汰策略 (最大 1000 条)

### 2. 结构化工具返回
- 所有工具返回 `ToolResult.to_dict()`
- 包含 `status`, `content`, `metadata`, `error`
- 统一错误处理 (`ErrorEnvelope`)
- 工具元数据可传递附加信息

### 3. 多 Agent 编排
- SupervisorManager 调度多个 Agent
- 支持同步/异步执行模式
- 执行状态实时推送 (SSE)

### 2. 上下文管理
- **压缩**: 70% token 阈值触发，LLM 摘要
- **长期记忆**: SQLite + ChromaDB
- **归档**: 7 天自动清理
- **Hot Zone**: LRU + 热度双因素淘汰

### 3. SOP 流程
- 状态持久化
- 步骤恢复
- 多模板支持

### 4. 产品/运营场景
- 客服工单处理 Workflow
- CRM 客户跟进 Workflow
- 数据分析报表 Workflow
- PRD 可视化设计 Workflow

## API 端点

| 端点 | 说明 |
|------|------|
| `POST /chat` | 对话执行 |
| `GET /metrics` | 指标统计 |
| `GET /api/registry/tools` | 工具/Skills/Agents 注册表 |
| `GET /api/execution/current` | 当前执行状态 |
| `GET /api/events/stream` | SSE 事件流 |
| `GET /api/workflows` | Workflow 列表 |
| `GET /api/skills` | Skills 列表 |

## 预置 Workflow

| ID | 名称 | 说明 |
|----|------|------|
| `wf-crm-ticket` | 客服工单处理 | 问题分类 → 智能回复 → 工单闭环 |
| `wf-crm-followup` | CRM 客户跟进 | 客户画像 → 跟进计划 → 提醒设置 |
| `wf-data-report` | 数据分析报表 | 数据查询 → 统计分析 → 报表生成 |
| `wf-prd-design` | PRD 可视化设计 | 需求分析 → 流程设计 → HTML 原型 |

## 预置 Agents

| ID | 名称 | 说明 |
|----|------|------|
| `crm-agent` | CRM Agent | 客户信息管理、跟进计划 |
| `data-analyst-agent` | Data Analyst | 数据分析、报表生成 |
| `prd-designer-agent` | PRD Designer | PRD 可视化设计 |

## 前端侧边栏面板

- **指标概览**: Token 消耗、费用、耗时、Turn 详情
- **可用工具**: 工具 / 技能 / Agent 列表
- **PRD 输入**: 产品需求文档表单 → 自动生成流程图 + HTML 原型
- **任务进度**: Agent 执行状态实时展示

## 测试

```bash
# 运行所有测试 (Mock 模式)
python -m pytest tests/ -v

# 运行 Real API 测试
USE_REAL_API=true python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_compression.py -v

# 运行单个测试
python -m pytest tests/test_compression.py::TestContextCompression::test_compress_merges_system_messages -v

# 运行匹配模式的测试
python -m pytest tests/ -k "compress" -v
```

### 测试覆盖率

```bash
# 运行并生成覆盖率报告
python -m pytest tests/ --cov=src.agent --cov-report=html

# 查看覆盖率摘要
python -m pytest tests/ --cov=src.agent --cov-report=term-missing
```

## 配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `OPENAI_API_KEY` | OpenAI API Key | - |
| `OPENAI_BASE_URL` | API 地址 | `https://api.openai.com/v1` |
| `AGENT_MODEL` | 模型 | `openai:gpt-4` |
| `AGENT_MEMORY_DIR` | 存储目录 | `./memory` |
| `AGENT_SESSION_TTL_DAYS` | 会话 TTL | `7` |
| `USE_REAL_API` | 启用 Real API 测试 | `false` |

## 文档

- `docs/task-plan-product-operations.md` - 产品/运营场景实施计划
- `docs/architecture/design-spec.md` - 架构设计
- `docs/context_design.md` - 上下文设计
- `AGENTS.md` - 开发指南