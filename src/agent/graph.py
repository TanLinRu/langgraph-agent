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


def _node_think(state):
    messages = state.get("messages", [])
    response = llm.invoke(messages)
    return {"messages": [response]}


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


def _node_compress(state):
    messages = state.get("messages", [])
    should_compress = compressor.should_compress(messages)
    if should_compress:
        compressed = compressor.compress(messages)
        return {"messages": compressed}
    return state


def _node_save(state):
    return state


workflow = StateGraph(AgentState)
workflow.add_node("init", _node_init)
workflow.add_node("think", _node_think)
workflow.add_node("execute", _node_execute)
workflow.add_node("compress", _node_compress)
workflow.add_node("save", _node_save)

workflow.set_entry_point("init")
workflow.add_edge("init", "think")
workflow.add_edge("execute", "compress")
workflow.add_conditional_edges(
    "think",
    _should_execute,
    {"execute": "execute", "end": END}
)
workflow.add_edge("compress", "save")
workflow.add_conditional_edges(
    "save",
    lambda s: "think" if s.get("task_status") == "in_progress" and s.get("compression_count", 0) < 5 else "end",
    {"think": "think", "end": END}
)

graph = workflow.compile()
