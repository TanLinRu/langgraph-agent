# AI Agent 上下文设计架构文档

> 版本：v1.2 | 更新日期：2024-06 | 状态：设计评审后修订

---

## 一、核心概念定义

### 1.1 上下文（Context）vs 记忆（Memory）

| 概念        | 定义                                   | 生命周期 | 业界对应        |
| ----------- | -------------------------------------- | -------- | --------------- |
| **Context** | 当前任务的 Working Set，让本次推理可解 | 单次推理 | LangGraph State |
| **Memory**  | 跨任务/会话的持久化，影响未来决策      | 长期     | LangGraph Store |

### 1.2 分层架构

```
Layer 4: Organizational Memory (组织级)     - 企业级元数据、治理策略
Layer 3.5: Procedural Memory (程序性)     - Agent操作模式、工作流程知识
Layer 3: Semantic/Relational Memory (语义层) - 实体关系、时序信息
Layer 2: Episodic/Experiential Memory (经验层) - 历史对话摘要、关键决策
Layer 1: Working Memory (工作内存)       - 当前消息、工具输出、中间状态
```

> **与 MemGPT/Letta 架构对应关系**：
> - Core Memory ≈ L1 + 部分 L2（核心记忆，始终在上下文）
> - Recall Memory ≈ L2 + L3（可召回记忆，需检索加载）
> - Archival Memory ≈ L3（归档记忆，长期存储）

---

## 二、LangGraph 组件映射

| 通用层级           | LangGraph 组件        | 说明                                  |
| ------------------ | --------------------- | ------------------------------------- |
| L1: Working        | **State.messages**    | 当前推理的原始数据                    |
| L2: Session        | **Checkpointer**      | 单会话状态持久化，thread_id 隔离      |
| L3: Cross-Session  | **Store (namespace)** | 跨会话长期记忆，按用户/类型分命名空间 |
| L4: Organizational | **External Service**  | 外部元数据服务（需自定义节点接入）    |

---

## 三、State 设计

### 3.1 State Schema

```python
from typing import TypedDict, Annotated, Optional
from datetime import datetime
from enum import Enum

class ConflictType(Enum):
    """记忆冲突类型"""
    CONTRADICTION = "contradiction"   # 语义矛盾
    EVOLUTION = "evolution"           # 意图演进（允许保留历史）
    SPECIFICATION = "specification"    # 细化补充

class ToolResultSummary(TypedDict):
    """Hot Zone 内 Tool Result 的摘要"""
    tool_call_id: str
    tool_name: str
    summary: str           # 简短描述，不含原始结果
    status: str            # success / failed
    timestamp: str
    access_count: int     # 访问热度（用于 LRU 淘汰）

class AgentState(TypedDict):
    # === L1: Working Memory ===
    messages: list                              # 对话历史（含 tool_calls/tool_results）
    current_input: str                           # 当前输入
    tool_outputs: list                          # 工具输出（临时）
    
    # === L2: Session Context ===
    session_summary: str                        # 会话摘要（超过 N 轮后生成）
    turn_count: int                            # 轮次计数
    checkpoint_id: str                         # 检查点 ID（恢复用）
    token_usage: dict                          # Token 预算追踪
    
    # === L3: Memory Index ===
    memory_strategy: str                       # 记忆策略选择
    hot_tool_results: list[ToolResultSummary]  # Hot Zone：最近 K 个 Tool Result（含访问热度）
```

### 3.2 Token 预算追踪

```python
class AgentState(TypedDict):
    token_usage: Annotated[dict, token_budget_reducer]
    # {
    #     "messages": 15000,
    #     "injected": 5000,
    #     "hot_zone": 2000,
    #     "budget": 200000,
    #     "percentage": 11
    # }
```

### 3.3 自定义 Reducer

```python
def smart_message_reducer(existing: list, new: list) -> list:
    """智能消息合并：控制 Context 增长"""
    MAX_MESSAGES = 20
    combined = existing + new
    if len(combined) <= MAX_MESSAGES:
        return combined
    return compress_messages(combined)

def token_budget_reducer(existing: dict, new: dict) -> dict:
    """Token 预算累加"""
    result = existing.copy()
    for key, value in new.items():
        result[key] = result.get(key, 0) + value
    result["percentage"] = round(result.get("messages", 0) / max(result.get("budget", 1), 1) * 100, 1)
    return result

class AgentState(TypedDict):
    messages: Annotated[list, smart_message_reducer]
    token_usage: Annotated[dict, token_budget_reducer]
```

---

## 四、Tool Result 处理方案

### 4.1 核心方案：Hot Zone（LRU+热度）+ External Store + Summary

```
┌─────────────────────────────────────────────────────────────┐
│ Context Window                                              │
├─────────────────────────────────────────────────────────────┤
│ [Hot Zone] 最近 K 个 tool_result                            │
│   → 双因素淘汰：LRU 顺序 + 访问热度                          │
│   → 存储完整对象（含 summary + access_count）                │
│   → 动态调整 K（根据 token 水位 3~5）                         │
└─────────────────────────────────────────────────────────────┘
                          ↓ 超过 K 个时
┌─────────────────────────────────────────────────────────────┐
│ External Store                                             │
├─────────────────────────────────────────────────────────────┤
│ {tool_call_id → {result, timestamp, tool_name, status}}   │
│   → 需要时通过 tool_call_id 检索                            │
│   → 支持完整结果回溯                                        │
└─────────────────────────────────────────────────────────────┘
                          ↓ 需要时
┌─────────────────────────────────────────────────────────────┐
│ Summary (压缩归档)                                          │
├─────────────────────────────────────────────────────────────┤
│   - 工具名称、调用参数、结果状态                              │
│   - 按 tool_call_id 可检索                                  │
│   - 不含原始结果                                            │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 配置参数

| 参数                 | 推荐值      | 依据                      |
| -------------------- | ----------- | ------------------------- |
| **Hot Zone K**       | 3-5（弹性） | Anthropic 建议 + 动态调整 |
| **压缩阈值**         | 60-70%      | 业界共识                  |
| **保留最小**         | 3           | Anthropic 最佳实践        |
| **Tool Result 最大** | 25K tokens  | Claude API 限制           |

### 4.3 LRU + 热度双因素淘汰算法

```python
class ToolResultStore:
    """Tool Result 存储管理器 - LRU + 热度双因素淘汰"""
    
    def __init__(self, hot_zone_size: int = 5):
        self._cache: dict[str, dict] = {}
        self._hot_zone: list[dict] = []  # 按访问顺序排列
        self._hot_zone_size = hot_zone_size
    
    def access(self, tool_call_id: str):
        """访问记录：提升热度"""
        for item in self._hot_zone:
            if item["tool_call_id"] == tool_call_id:
                item["access_count"] = item.get("access_count", 0) + 1
                # 移到末尾（最近访问）
                self._hot_zone.remove(item)
                self._hot_zone.append(item)
                break
    
    def store(self, tool_call_id: str, tool_name: str, 
              result: str, status: str = "success") -> ToolResultSummary:
        """存储 Tool Result"""
        summary = self._generate_summary(tool_name, result, status)
        
        # 存储完整结果
        self._cache[tool_call_id] = {
            "result": result,
            "tool_name": tool_name,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": summary
        }
        
        # 双因素淘汰：LRU + 热度
        hot_entry = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "summary": summary,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "access_count": 0
        }
        
        if len(self._hot_zone) >= self._hot_zone_size:
            # 淘汰策略：访问热度最低的
            hot_zone_sorted = sorted(
                self._hot_zone, 
                key=lambda x: (x.get("access_count", 0), x["timestamp"])
            )
            evicted = hot_zone_sorted[0]
            # 移出 Hot Zone 但保留在 cache 中
            self._hot_zone = [x for x in self._hot_zone if x["tool_call_id"] != evicted["tool_call_id"]]
        
        self._hot_zone.append(hot_entry)
        return hot_entry
    
    def _generate_summary(self, tool_name: str, result: str, status: str) -> str:
        """根据工具类型生成摘要"""
        if status == "failed":
            return f"[{tool_name}] 调用失败"
        result_preview = result[:200] if len(result) > 200 else result
        return f"[{tool_name}] {result_preview}"
```

---

## 五、节点设计

### 5.1 核心节点流

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   START     │────▶│ read_memory │────▶│ call_model  │────▶│write_memory │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                 │                │
                                                 ▼                ▼
                                          ┌─────────────┐     ┌─────────────┐
                                          │execute_tool│     │update_summary
                                          └─────────────┘     └─────────────┘
```

### 5.2 多维触发检索策略

```python
async def read_memory(state: AgentState, 
                      runtime: Runtime,
                      tool_result_store: ToolResultStore) -> dict:
    
    # === L1: 工作内存（直接读取）===
    recent_messages = state["messages"][-10:]
    
    # === L2: 会话级（触发式）===
    session_summary = state.get("session_summary", "")
    token_percentage = state.get("token_usage", {}).get("percentage", 0)
    
    # === L3: 跨会话（多维触发）===
    # 触发条件：token水位 OR 语义相关 OR 任务类型
    query_intent = detect_intent(state["current_input"])  # planning/reflection/comparison
    semantic_sim = compute_similarity(state["current_input"], session_summary)
    
    should_retrieve = (
        token_percentage > 40 or
        query_intent in ["planning", "reflection", "comparison"] or
        semantic_sim > 0.7
    )
    
    memories = []
    if should_retrieve:
        memories = await runtime.store.asearch(
            namespace=(runtime.tenant_id, runtime.org_id, runtime.user_id, "memories"),
            query=state["current_input"],
            limit=3
        )
    
    # 构建注入上下文
    injected_context = build_context(
        summary=session_summary,
        memories=[m.value for m in memories],
        hot_tool_results=tool_result_store.get_hot_zone()
    )
    
    return {"injected_context": injected_context}
```

---

## 六、记忆冲突处理

### 6.1 冲突类型识别

```python
class ConflictType(Enum):
    CONTRADICTION = "contradiction"   # 语义矛盾（如"喜欢咖啡"→"讨厌咖啡"）
    EVOLUTION = "evolution"           # 意图演进（如"想要学习"→"正在学习"）
    SPECIFICATION = "specification"    # 细化补充（如"用 Go"→"用 Go 写 API"）
    NO_CONFLICT = "no_conflict"       # 无冲突
```

### 6.2 冲突解决策略

```python
from enum import Enum

class MemoryOp(Enum):
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    NOOP = "noop"

async def resolve_memory_conflict(old_mem: dict, new_mem: dict) -> tuple[MemoryOp, dict]:
    """解决记忆冲突 - 保留历史轨迹"""
    old_value = old_mem.get("value", "")
    new_value = new_mem.get("value", "")
    source = old_mem.get("source", "")
    
    if old_value == new_value:
        return (MemoryOp.NOOP, old_mem)
    
    # 检测冲突类型
    conflict_type = detect_conflict_type(old_value, new_value)
    
    if conflict_type == ConflictType.CONTRADICTION:
        # 语义矛盾：保留历史轨迹，不直接覆盖
        return (MemoryOp.UPDATE, {
            **old_mem,
            "current_value": new_value,
            "value_history": old_mem.get("value_history", []) + [
                {"value": old_value, "timestamp": old_mem.get("updated_at")}
            ],
            "conflict_type": ConflictType.CONTRADICTION.value,
            "updated_at": datetime.utcnow().isoformat()
        })
    
    elif conflict_type == ConflictType.EVOLUTION:
        # 意图演进：允许直接更新
        return (MemoryOp.UPDATE, {
            **old_mem,
            "value": new_value,
            "updated_at": datetime.utcnow().isoformat()
        })
    
    else:
        # 细化补充/无冲突：直接更新
        return (MemoryOp.UPDATE, {
            **old_mem,
            "value": new_value,
            "updated_at": datetime.utcnow().isoformat()
        })

def detect_conflict_type(old_value: str, new_value: str) -> ConflictType:
    """检测冲突类型（简化版，实际可用语义模型）"""
    # 简单判断：包含否定词为矛盾
    negation_words = ["不", "没", "不要", "不是"]
    has_negation_old = any(w in old_value for w in negation_words)
    has_negation_new = any(w in new_value for w in negation_words)
    
    if has_negation_old != has_negation_new:
        return ConflictType.CONTRADICTION
    return ConflictType.SPECIFICATION
```

---

## 七、结构化压缩策略

### 7.1 压缩摘要 Schema

```python
class CompressedTurn(TypedDict):
    """结构化压缩后的单轮对话"""
    turn_index: int
    user_intent: str          # 用户核心意图
    key_facts: list[str]     # 关键事实/约束（用户明确声明）
    tool_actions: list[dict] # 执行过的工具 [{name, params, status}]
    unresolved: list[str]     # 待解决问题
    compression_rationale: str  # 压缩理由（用于审计）

def compress_messages(messages: list, max_turns: int = 10) -> tuple[list, list[CompressedTurn]]:
    """生成结构化压缩摘要"""
    compressed_turns = []
    preserved = messages[-max_turns:]  # 保留最近 N 轮
    
    # 压缩更早的消息
    old_messages = messages[:-max_turns]
    for i in range(0, len(old_messages), 2):
        user_msg = old_messages[i] if i < len(old_messages) else None
        assistant_msg = old_messages[i+1] if i+1 < len(old_messages) else None
        
        turn = CompressedTurn(
            turn_index=i//2,
            user_intent=extract_intent(user_msg.content) if user_msg else "",
            key_facts=extract_key_facts(user_msg.content) if user_msg else [],
            tool_actions=extract_tool_actions(assistant_msg) if assistant_msg else [],
            unresolved=[],
            compression_rationale="超过保留轮次，压缩归档"
        )
        compressed_turns.append(turn)
    
    return preserved, compressed_turns
```

---

## 八、隔离机制

### 8.1 四元组隔离

```python
def get_namespace(tenant_id: str, org_id: str, user_id: str, memory_type: str):
    """Namespace 设计：租户 > 组织 > 用户 > 记忆类型"""
    return (tenant_id, org_id, user_id, memory_type)
```

### 8.2 Checkpointer 配置

```python
def make_thread_id(context: IsolationContext) -> str:
    return f"{context.tenant_id}:{context.org_id}:{context.session_id}"

config = {
    "configurable": {
        "thread_id": make_thread_id(context),
        "tenant_id": context.tenant_id,
        "org_id": context.org_id
    }
}
```

---

## 九、异常边界处理

### 9.1 异常分类与处理

| 异常类型             | 触发条件         | 处理策略                           |
| -------------------- | ---------------- | ---------------------------------- |
| **Context Overflow** | Token > 70%      | 分层压缩：L1→L2 摘要，L2→L3 归档   |
| **Cross-Tenant**     | namespace 不匹配 | 抛出 IsolationError                |
| **Concurrent**       | 同 session 并发  | Semaphore 限流                     |
| **Checkpoint Lost**  | 无 checkpoint    | 降级到新会话，保留 session_summary |
| **Tool Result Miss** | 检索失败         | 记录日志，降级到 Summary           |

### 9.2 时间维度支持

```python
class TemporalContext(TypedDict):
    """时序上下文"""
    absolute_time: str      # ISO 8601
    relative_time: str      # "昨天"、"上周"
    sequence_after: str     # "调用 tool_A 之后"
    valid_from: str         # 生效开始时间
    valid_until: str       # 生效结束时间（可选）
```

---

## 十、可观测性设计

### 10.1 量化验收标准

| 指标              | 目标值            | 测量方式                            |
| ----------------- | ----------------- | ----------------------------------- |
| **会话溢出率**    | ≤5%（50轮对话内） | token% 超过85%的会话数/总会话数     |
| **记忆命中率**    | ≥70%              | top-3检索结果被模型使用的比例       |
| **跨租户隔离率**  | 100%              | 越权访问被拒绝次数/越权访问尝试次数 |
| **压缩质量**      | ≥85%              | 压缩后任务完成率/原始任务完成率     |
| **Hot Zone 抖动** | ≤10%              | "刚移出就检索"次数/总压缩次数       |

### 10.2 监控指标

| 指标                  | 类型 | 告警阈值                  |
| --------------------- | ---- | ------------------------- |
| Token Usage %         | 技术 | > 80%                     |
| Memory Hit Rate       | 技术 | < 60%                     |
| Compression Frequency | 技术 | > 10次/分钟               |
| Task Completion Rate  | 业务 | 有记忆 vs 无记忆下降 < 5% |
| User Satisfaction     | 业务 | < 4.0 (5分制)             |

---

## 十一、实施计划

### Phase 1: 基础架构（2周）

- [ ] State Schema 定义（含 token_usage、热力追踪）
- [ ] Checkpointer 配置（4级隔离）
- [ ] 基础节点流程实现
- [ ] **验收标准**：50轮对话内 token ≤85%

### Phase 2: 记忆管理（2周）

- [ ] Store 配置 + 语义搜索
- [ ] 写入策略（冲突识别 + 保留历史轨迹）
- [ ] 读取策略（多维触发）
- [ ] Tool Result 分层处理（LRU+热度淘汰）
- [ ] 结构化压缩（Schema + rational）
- [ ] **验收标准**：记忆命中率 ≥70%

### Phase 3: 隔离与治理（2周）

- [ ] 租户/组织隔离（四元组）
- [ ] 并发控制
- [ ] 审计日志
- [ ] PII 脱敏
- [ ] 记忆过期策略
- [ ] **验收标准**：跨租户访问 100% 拒绝

### Phase 4: 高级特性（1周）

- [ ] 断点恢复（含幂等补偿）
- [ ] 时间旅行
- [ ] Human-in-loop
- [ ] 可观测性面板
- [ ] **验收标准**：可恢复中断会话

---

## 十二、关键结论

1. **Tool Result 处理**：旧结果很少被重新引用，清除是安全的（Anthropic）
2. **最佳策略**：Hot Zone（LRU+热度）+ External Store + Summary
3. **冲突解决**：保留历史轨迹，支持偏好演变查询
4. **隔离原则**：四元组 namespace，分层隔离，强制校验

---

## 参考文献

[1] [Anthropic Context Management - Tool Use](https://platform.anthropic.com/docs/agents-and-tools/tool-use/manage-tool-context)

[2] [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413)

[3] [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)