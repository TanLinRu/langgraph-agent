"""
LangGraph Studio 可视化入口

通过 `langgraph dev` 启动后，Studio 会加载此文件中的 `graph` 变量。
该变量是一个编译好的 LangGraph 有状态图，支持聊天、工具调用、上下文压缩等。

注意：LangGraph CLI 不允许自定义 checkpointer（由平台自动管理），
因此这里的图不使用 MemorySaver。
"""
import os
from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from src.agent.config import DEFAULT_CONFIG
from src.agent.state import AgentState
from src.agent.context import LongTermManager, LongTermConfig, ContextCompressor, CompressionConfig
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.skills import SKILLS_INDEX
from src.agent.tools import TOOLS


config = DEFAULT_CONFIG.model_copy(update={
    "api_key": os.getenv("OPENAI_API_KEY", ""),
    "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "model": os.getenv("AGENT_MODEL", "openai:gpt-4"),
})

llm = ChatOpenAI(
    model=config.model.replace("openai:", ""),
    api_key=config.api_key,
    base_url=config.base_url,
    temperature=0,
)

long_term_config = LongTermConfig(
    memory_dir=config.long_term.memory_dir,
    session_ttl_days=config.long_term.session_ttl_days,
    vector_enabled=config.long_term.vector_enabled,
    chroma_persist_dir=config.long_term.chroma_persist_dir,
)
long_term = LongTermManager(long_term_config)

compression_config = CompressionConfig(
    trigger_threshold=config.short_term.trigger_threshold,
    keep_recent=config.short_term.keep_recent,
)
compressor = ContextCompressor(compression_config, llm)


class RetrievalTrigger:
    """多维触发检索 (设计参考: context_design.md 5.2)"""

    def __init__(self, long_term_manager: LongTermManager):
        self.long_term = long_term_manager

    def should_retrieve(self, state: AgentState) -> bool:
        """多维触发条件

        触发条件（满足任一即触发）:
        1. token水位 > 40%
        2. 任务类型 in [planning, reflection, comparison]
        3. 语义相似度 > 0.7
        """
        token_percentage = state.get("token_usage", {}).get("percentage", 0)
        current_input = state.get("messages", [{}])[-1].get("content", "")

        trigger_conditions = (
            token_percentage > 40 or
            self._is_planning_task(current_input) or
            self._is_reflection_task(current_input) or
            self._check_semantic_similarity(state, current_input)
        )
        return trigger_conditions

    def _is_planning_task(self, text: str) -> bool:
        keywords = ["计划", "规划", "接下来", "下一步", "roadmap", "plan"]
        return any(kw in text.lower() for kw in keywords)

    def _is_reflection_task(self, text: str) -> bool:
        keywords = ["之前", "上次", "之前做", "回忆", "之前是"]
        return any(kw in text for kw in keywords)

    def _check_semantic_similarity(self, state: AgentState, current_input: str) -> bool:
        """检查语义相似度 > 0.7 (Jaccard 关键词重叠)"""
        if not current_input:
            return False
        input_words = set(current_input.lower().split())
        if not input_words:
            return False
        session_summary = self._get_session_summary(state)
        if not session_summary:
            return False
        summary_words = set(session_summary.lower().split())
        overlap = len(input_words & summary_words)
        union = len(input_words | summary_words)
        jaccard = overlap / union if union > 0 else 0
        return jaccard > 0.7

    def _get_session_summary(self, state: AgentState) -> str:
        """从已压缩消息中提取 session summary"""
        for msg in state.get("messages", []):
            name = msg.get("name", "") if isinstance(msg, dict) else ""
            if name == "context_summary":
                return msg.get("content", "")[:500]
        return ""

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        """语义检索相关记忆"""
        return self.long_term.search_similar(query, top_k)


retrieval_trigger = RetrievalTrigger(long_term)


def _node_init(state):
    from src.agent.prompts import SYSTEM_PROMPT
    from src.agent.skills import SKILLS_INDEX
    system_content = f"{SYSTEM_PROMPT}\n\n---\n\n{SKILLS_INDEX}"
    messages = [{"role": "system", "content": system_content}]
    last_user = state.get("messages", [{}])[-1] if state.get("messages") else {}
    if isinstance(last_user, dict):
        content = last_user.get("content", "")
    else:
        content = getattr(last_user, "content", "")
    if content:
        messages.append({"role": "user", "content": content})
    return {"messages": messages}


def _node_read_memory(state):
    """读取跨会话记忆 (设计参考: context_design.md 5.1)"""
    if not retrieval_trigger.should_retrieve(state):
        return {"injected_memory": []}

    current_input = state.get("messages", [{}])[-1].get("content", "")
    memories = retrieval_trigger.retrieve(current_input, top_k=3)

    if not memories:
        return {"injected_memory": []}

    memory_content = "\n".join(f"- {m}" for m in memories)
    injected_msg = {
        "role": "system",
        "content": f"【相关记忆】\n{memory_content}",
        "name": "injected_memory",
    }
    return {"injected_memory": [injected_msg]}


def _node_think(state):
    messages = state.get("messages", [])
    injected = state.get("injected_memory", [])
    if injected:
        messages = messages + injected
    response = llm.invoke(messages)
    return {"messages": [response], "injected_memory": []}


def _should_execute(state):
    messages = state.get("messages", [])
    if not messages:
        return "execute"
    last = messages[-1]
    if hasattr(last, "tool_calls"):
        has_tool = bool(last.tool_calls)
    elif isinstance(last, dict):
        has_tool = bool(last.get("tool_calls"))
    else:
        has_tool = False
    return "execute" if has_tool else "end"


def _node_execute(state):
    from src.agent.agent import _msg_get
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else {}
    tool_calls = _msg_get(last_msg, "tool_calls", [])
    results = []
    for call in tool_calls:
        tool_name = _msg_get(call, "name")
        tool_input = _msg_get(call, "arguments", {})
        tool_call_id = _msg_get(call, "id")
        for t in TOOLS:
            if t.name == tool_name:
                try:
                    result = t.invoke(tool_input)
                    results.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": str(result)
                    })
                except Exception as e:
                    results.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": f"错误: {str(e)}"
                    })
                break
    return {"messages": results}


def _node_write_memory(state):
    """写入记忆 (设计参考: context_design.md 5.1)"""
    messages = state.get("messages", [])
    if messages:
        last_user = None
        for msg in reversed(messages):
            role = msg.get("role", "")
            if role == "user":
                last_user = msg.get("content", "")
                break
        if last_user:
            long_term.write_memory(last_user, category="interaction")
    return {}


def _node_compress(state):
    messages = state.get("messages", [])
    should_compress = compressor.should_compress(messages)
    if should_compress:
        compressed = compressor.compress(messages)
        hot_zone = compressor.get_hot_zone()
        hot_tool_results = [
            {
                "tool_call_id": h.tool_call_id,
                "tool_name": h.tool_name,
                "summary": h.summary,
                "status": h.status,
                "timestamp": h.timestamp,
                "access_count": h.access_count,
            }
            for h in hot_zone
        ]
        return {"messages": compressed, "hot_tool_results": hot_tool_results}
    return state


def _node_save(state):
    return state


workflow = StateGraph(AgentState)
workflow.add_node("init", _node_init)
workflow.add_node("read_memory", _node_read_memory)
workflow.add_node("think", _node_think)
workflow.add_node("execute", _node_execute)
workflow.add_node("write_memory", _node_write_memory)
workflow.add_node("compress", _node_compress)
workflow.add_node("save", _node_save)

workflow.set_entry_point("init")
workflow.add_edge("init", "read_memory")
workflow.add_edge("read_memory", "think")
workflow.add_edge("execute", "compress")
workflow.add_conditional_edges(
    "think",
    _should_execute,
    {"execute": "execute", "end": END}
)
workflow.add_edge("compress", "write_memory")
workflow.add_edge("write_memory", "save")
workflow.add_conditional_edges(
    "save",
    lambda s: "read_memory" if s.get("task_status") == "in_progress" and s.get("compression_count", 0) < 5 else "end",
    {"read_memory": "read_memory", "end": END}
)

graph = workflow.compile()


# === Supervisor Graph (for LangGraph Studio visualization) ===

def _build_studio_supervisor():
    """构建 supervisor 图用于 Studio 可视化。"""
    from src.agent.registry import get_registry
    from src.agent.supervisor import SupervisorManager

    registry = get_registry(memory_dir=config.long_term.memory_dir)
    graphs = registry.list_graphs()

    if not graphs:
        return None

    graph_def = graphs[0]
    mgr = SupervisorManager(registry, llm, TOOLS)
    return mgr.build_supervisor(graph_def["id"])


try:
    supervisor_graph = _build_studio_supervisor()
except Exception:
    supervisor_graph = None
