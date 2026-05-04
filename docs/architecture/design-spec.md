# Agent 架构设计规约

> LangGraph Agent 生产级实现设计规范

---

## 1. 上下文设计

### 1.1 分层架构

| 层级 | 内容 | 管理方式 |
|------|------|----------|
| 常驻层 | System Prompt、Skills 索引 | 稳定，不压缩 |
| 运行时层 | 当前任务、时间、进度 | 每轮更新 |
| 会话层 | 消息流 | LLM 压缩 |
| 记忆层 | MEMORY.md、向量、Session | 持久化 |

### 1.2 压缩机制

- **触发阈值**: 70% token 使用率
- **压缩策略**: LLM 摘要
- **保留消息数**: 最近 5 条
- **保留优先级**:
  1. 架构决策（不得摘要）
  2. 文件变更
  3. 验证状态
  4. TODO
  5. 工具输出（可删除）

### 1.3 长期存储

| 存储类型 | 技术 | 位置 |
|----------|------|------|
| 语义记忆 | MEMORY.md | `memory/memory/MEMORY.md` |
| 向量存储 | ChromaDB | `memory/chroma/` |
| 会话元数据 | SQLite | `memory/sessions/sessions.db` |
| 会话消息 | JSONL | `memory/sessions/{thread_id}.jsonl` |
| 归档 | JSONL | `memory/archive/` |

### 1.4 归档策略

- **周期**: 7 天
- **操作**: 移动到 archive/，从 SQLite 删除
- **通知**: 生成归档报告

---

## 2. 状态管理

### 2.1 状态定义

```python
class AgentState(TypedDict):
    messages: list                      # 消息列表
    thread_id: str                     # 会话 ID
    task_status: str                   # pending/in_progress/completed/failed
    current_plan: list | None          # 当前计划
    compression_count: int             # 压缩次数
    checkpoint_id: str | None           # 检查点 ID
```

### 2.2 Checkpoint

- **技术**: SQLite (MemorySaver)
- **恢复**: 服务重启时自动恢复最近会话

---

## 3. 工具系统

### 3.1 工具设计原则 (ACI)

- **Action-oriented**: 描述动作而非功能
- **Context-aware**: 包含 Use when / Don't use when
- **Structured output**: 返回结构化数据

### 3.2 核心工具

| 工具 | 职责 |
|------|------|
| execute_code | Python 代码执行 |
| data_processor | CSV/JSON 清洗、转换、统计 |
| file_operator | 文件读/写/编辑 |
| search | 代码和文档搜索 |

---

## 4. Skills 系统

### 4.1 设计原则

- **索引常驻**: 描述符保留在系统提示中
- **按需加载**: 完整内容触发时加载
- **Use when / Don't use when**: 必须包含反例

### 4.2 内置 Skills

| Skill | 用途 |
|-------|------|
| code_review | 代码审查与质量检查 |
| data_analysis | 数据处理与可视化 |
| debugging | 问题诊断与修复 |

---

## 5. 服务重启恢复

### 5.1 恢复流程

```
1. 加载 System Prompt
2. 加载 Skills Index
3. 加载 MEMORY.md
4. ChromaDB 语义搜索
5. SQLite 恢复最近会话消息
6. 构建运行时上下文
7. 验证恢复成功
8. 继续执行
```

### 5.2 配置

- `resume_on_startup`: True
- `load_recent_sessions`: 5

---

## 6. 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `trigger_threshold` | 0.7 | 压缩触发阈值 |
| `keep_recent` | 5 | 保留最近消息数 |
| `session_ttl_days` | 7 | Session 保留天数 |
| `vector_dimension` | 1536 | ChromaDB 向量维度 |
| `summary_max_tokens` | 500 | 摘要最大长度 |

---

## 7. 目录结构

```
src/agent/
├── context/
│   ├── short_term.py         # 短期上下文
│   ├── long_term.py         # 长期上下文
│   ├── compression.py       # LLM 压缩
│   ├── initialization.py    # 重启恢复
│   └── archive.py           # 归档
├── prompts/
│   └── system_prompt.py
├── skills/
│   └── __init__.py
└── tools/
    └── __init__.py

memory/
├── memory/MEMORY.md
├── sessions/
├── archive/
└── chroma/
```

---

## 8. 实现顺序

1. 基础架构（config, state, 目录）
2. 长期上下文（SQLite + ChromaDB）
3. 短期上下文 + 压缩
4. 重启恢复 + 归档
5. 提示 + 技能 + 工具
6. 主入口集成