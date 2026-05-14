# Context 上下文设计文档

> 版本: v1.0 | 更新日期: 2024-05-14 | 状态: 已实现

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         LangGraph-Agent Context                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  L1: Working Memory (State.messages)                             │   │
│  │  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │   │
│  │  │ system  │  │   user   │  │ assistant │  │ tool (is_hot_zone) │  │   │
│  │  └─────────┘  └──────────┘  └──────────┘  └───────────────────┘  │   │
│  │       ↑            ↑             ↑                  ↑            │   │
│  │       └────────────┴─────────────┴──────────────────┘            │   │
│  │                     smart_message_reducer                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│                                    ▼ 70% 阈值触发                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ContextCompressor (压缩器)                                     │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌─────────────────┐   │   │
│  │  │ LLM 摘要生成     │  │ CompressedTurn │  │  Hot Zone Store  │   │   │
│  │  │ (3-5句话)       │  │ (结构化)        │  │  (LRU+热度淘汰)  │   │   │
│  │  └────────────────┘  └────────────────┘  └─────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│                    ┌───────────────┴───────────────┐                   │
│                    ▼                               ▼                   │
│  ┌──────────────────────────┐     ┌──────────────────────────────┐     │
│  │  L2: Session (SQLiteSaver) │     │  L3: Cross-Session (ChromaDB)│     │
│  │  ┌──────────────────────┐ │     │  ┌──────────────────────────┐ │     │
│  │  │ sessions.db          │ │     │  │ agent_memory collection  │ │     │
│  │  │ sessions/{id}.jsonl │ │     │  │ (cosine similarity)       │ │     │
│  │  └──────────────────────┘ │     │  └──────────────────────────┘ │     │
│  └──────────────────────────┘     └──────────────────────────────┘     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 数据流图

### 2.1 单轮对话流程

```
┌─────────┐     ┌─────────┐     ┌──────────┐     ┌──────────┐     ┌─────────┐
│  User   │────▶│  init   │────▶│  think   │────▶│ execute  │────▶│  save   │
│ Input   │     │  node   │     │  (LLM)   │     │ (tools)  │     │  node   │
└─────────┘     └─────────┘     └──────────┘     └──────────┘     └─────────┘
                                                                   │
                                                                   ▼
                                                          ┌────────────────┐
                                                          │ LongTermManager│
                                                          │ .save_session()│
                                                          └────────────────┘
                                                                   │
                                              ┌────────────────────┬┴──────────────┐
                                              ▼                    ▼               ▼
                                        ┌──────────┐      ┌────────────┐     ┌──────────┐
                                        │ sessions │      │ sessions   │     │ ChromaDB │
                                        │   .db    │      │/{id}.jsonl │     │ 向量检索  │
                                        └──────────┘      └────────────┘     └──────────┘
```

### 2.2 压缩流程 (70% Token 阈值)

```
                          Token >= 70%
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ContextCompressor.compress()                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 分离消息类型                                                   │
│     ┌────────────────────────────────────────────────────────┐   │
│     │ messages -> [system, user_assistant, tools]             │   │
│     └────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  2. Tool Results 存入 Hot Zone                                   │
│     ┌────────────────────────────────────────────────────────┐   │
│     │ ToolResultStore.store(tool_call_id, name, result)      │   │
│     │ -> LRU+热度双因素淘汰                                    │   │
│     └────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  3. 生成结构化压缩 (CompressedTurn)                              │
│     ┌────────────────────────────────────────────────────────┐   │
│     │ for user/assistant pairs:                               │   │
│     │   CompressedTurn {                                      │   │
│     │     turn_index,                                         │   │
│     │     user_intent,  // 用户核心意图                       │   │
│     │     key_facts,      // 关键事实                          │   │
│     │     tool_actions,   // 工具调用记录                      │   │
│     │     unresolved,     // 待解决问题                        │   │
│     │     compression_rationale                               │   │
│     │   }                                                     │   │
│     └────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  4. LLM 生成摘要                                                 │
│     ┌────────────────────────────────────────────────────────┐   │
│     │ "请用 3-5 句话概括以下对话的关键信息..."                 │   │
│     │ - 保留关键决策和结论                                     │   │
│     │ - 记录未完成的任务                                       │   │
│     │ - 提取重要的技术和事实信息                                │   │
│     │ - 不要包含详细的推理过程                                  │   │
│     └────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  5. 输出压缩后消息                                               │
│     ┌────────────────────────────────────────────────────────┐   │
│     │ [                                                              │
│     │   system 消息,                                               │
│     │   {role: "system", name: "context_summary",                │
│     │    content: "LLM摘要...",                                   │
│     │    compressed_turns: [...]},                               │
│     │   最近 5 轮 user/assistant,                                 │
│     │   Hot Zone tool results (is_hot_zone=true)                  │
│     │ ]                                                             │
│     └────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 跨会话记忆检索

```
                         Token > 40%
                      Task Type: planning
                      Semantic Similarity > 0.7
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RetrievalTrigger.should_retrieve()           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  判断条件（三选一即触发）:                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. token_percentage > 40%                                │  │
│  │ 2. task_type in [planning, reflection, comparison]       │  │
│  │ 3. semantic_similarity > 0.7 (Jaccard)                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  LongTermManager.search_similar(query, top_k=3)                │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ChromaDB: cosine similarity query                         │  │
│  │ 返回 top-3 相关记忆                                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  注入到 AgentState.injected_memory                              │
│                              │                                  │
│                              ▼                                  │
│  [injected_memory] -> think 节点 -> LLM 处理                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 数据结构设计

### 3.1 AgentState Schema

| 字段 | 类型 | 说明 |
|------|------|------|
| `messages` | `Annotated[list, smart_message_reducer]` | 对话历史，MAX=20 触发通知 |
| `hot_tool_results` | `list[ToolResultSummary]` | Hot Zone 持久化 |
| `injected_memory` | `list` | 跨会话注入 |
| `thread_id` | `str` | 会话标识 |
| `task_status` | `Literal` | pending/in_progress/completed/failed |
| `token_usage` | `Annotated[dict, token_budget_reducer]` | Token 预算追踪 |
| `compression_count` | `int` | 压缩次数，限制 < 5 |
| `current_plan` | `list \| None` | 当前计划 |
| `sop_name` | `str \| None` | SOP 名称 |
| `sop_step` | `int \| None` | SOP 步骤 |
| `checkpoint` | `str \| None` | 检查点 ID |
| `created_at` | `str` | 创建时间 |
| `updated_at` | `str` | 更新时间 |

### 3.2 CompressedTurn Schema

| 字段 | 类型 | 说明 |
|------|------|------|
| `turn_index` | `int` | 轮次索引 |
| `user_intent` | `str` | 用户核心意图 (前200字符) |
| `key_facts` | `list[str]` | 关键事实/约束 (TODO: 需 LLM 提取) |
| `tool_actions` | `list[dict]` | 工具调用记录 `[{name, params, status}]` |
| `unresolved` | `list[str]` | 待解决问题 (TODO: 需检测) |
| `compression_rationale` | `str` | 压缩理由，用于审计 |

### 3.3 ToolResultSummary Schema

| 字段 | 类型 | 说明 |
|------|------|------|
| `tool_call_id` | `str` | 工具调用ID |
| `tool_name` | `str` | 工具名称 |
| `summary` | `str` | 摘要 (前200字符) |
| `status` | `str` | success / failed |
| `timestamp` | `str` | ISO 时间戳 |
| `access_count` | `int` | 访问热度 (默认 0) |

### 3.4 Hot Zone 淘汰算法

```
淘汰条件: len(hot_zone) >= hot_zone_size (默认 5)

淘汰策略: 按 (access_count 升序, timestamp 升序) 排序
          -> 热度最低 + 时间最老的先淘汰

流程:
  1. 新工具结果存入 _cache (保留完整结果)
  2. 创建 ToolResultSummary 加入 _hot_zone
  3. 如果 len(_hot_zone) >= hot_zone_size，执行 _evict()
  4. _evict() 排序后移除第一个 (热度最低)
```

---

## 4. 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_tokens` | 128000 | Context window 大小 |
| `trigger_threshold` | 0.7 | 压缩触发阈值 (70%) |
| `keep_recent` | 5 | 保留最近对话轮数 |
| `summary_max_tokens` | 500 | LLM 摘要最大长度 |
| `hot_zone_size` | 5 | Hot Zone 工具结果数量 |
| `MAX_MESSAGES` | 20 | smart_message_reducer 阈值 |
| `semantic_threshold` | 0.7 | 检索触发相似度 |
| `token_threshold` | 0.4 | 检索触发 Token 水位 |

---

## 5. 存储位置

| 存储 | 路径 | 说明 |
|------|------|------|
| SQLite 元数据 | `./memory/sessions.db` | 会话表 + 记忆表 |
| JSONL 增量 | `./memory/sessions/{thread_id}.jsonl` | 消息增量存储 |
| ChromaDB | `./memory/chroma/` | 向量索引 |
| 归档 | `./memory/archive/` | 7 天 TTL 归档 |

---

## 6. 与 OpenCode 摘要模式对比

| 方面 | 本项目 | OpenCode 模式 |
|------|--------|---------------|
| **摘要单元** | `CompressedTurn` | 轮次级结构化 |
| **用户意图** | `user_intent` (前200字符) | 自动提取 |
| **工具追踪** | `tool_actions` 列表 | 工具调用历史 |
| **关键事实** | `key_facts` (待实现) | TODO |
| **待解决问题** | `unresolved` (待实现) | TODO |
| **触发方式** | Token 70% 阈值 | 轮次阈值 |

---

## 7. 实现状态

| 特性 | 状态 | 文件位置 |
|------|------|----------|
| AgentState 定义 | ✅ 已实现 | `src/agent/state.py:42-56` |
| smart_message_reducer | ✅ 已实现 | `src/agent/state.py:29-39` |
| token_budget_reducer | ✅ 已实现 | `src/agent/state.py:20-26` |
| CompressedTurn | ✅ 已实现 | `src/agent/context/compression.py:44-55` |
| ContextCompressor | ✅ 已实现 | `src/agent/context/compression.py:69-143` |
| ToolResultStore | ✅ 已实现 | `src/agent/context/tool_result_store.py:19-133` |
| LongTermManager | ✅ 已实现 | `src/agent/context/long_term.py:71-232` |
| RetrievalTrigger | ✅ 已实现 | `src/agent/context/retrieval_trigger.py:14-65` |
| Hot Zone 持久化 | ⚠️ 部分 | 压缩时同步到 state |
| key_facts LLM 提取 | ❌ 待实现 | 需修改 compress() |
| unresolved 检测 | ❌ 待实现 | 需 LLM 辅助 |
| session_summary 锚点 | ⚠️ 依赖压缩 | 需定期生成节点 |

---

## 8. 改进计划

### Phase 1: 完善压缩质量 (Easy)

- [ ] LLM 提取 `key_facts` 字段
- [ ] LLM 检测 `unresolved` 字段
- [ ] 强制生成 `session_summary` 锚点

### Phase 2: 增强语义搜索 (Medium)

- [ ] 集成 sentence-transformers Embedding
- [ ] 替换 Jaccard 为余弦相似度
- [ ] 添加 session_summary 向量化

### Phase 3: Hot Zone 持久化 (Medium)

- [ ] SQLite 存储 Hot Zone 访问计数
- [ ] 重启后恢复热度
- [ ] 增量更新而非重置

---

## 9. 参考

- 设计文档: `docs/context_design.md`
- 状态定义: `src/agent/state.py`
- 压缩逻辑: `src/agent/context/compression.py`
- 工具存储: `src/agent/context/tool_result_store.py`
- 长期管理: `src/agent/context/long_term.py`
- 检索触发: `src/agent/context/retrieval_trigger.py`