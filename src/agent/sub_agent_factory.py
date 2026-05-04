"""
Sub-Agent Factory

将注册表中的 Agent 定义转换为 LangGraph create_react_agent 实例。
支持 sync 模式（LLM + tools）和 acp 模式（外部 CLI 包装为 tool）。
"""
import re
import logging
from typing import Optional

from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _sanitize_agent_name(agent_id: str) -> str:
    """将注册表 agent_id 转换为 LangGraph 兼容的节点名。

    规则：
    - 移除 'builtin-' 前缀
    - 将 '-' 替换为 '_'
    - 移除非法字符
    - 确保不以数字开头
    - 添加 '_agent' 后缀（如果没有）
    """
    name = agent_id
    if name.startswith("builtin-"):
        name = name[len("builtin-"):]
    # 只保留字母数字和下划线
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    # 不以数字开头
    if name and name[0].isdigit():
        name = "a_" + name
    # 确保有 _agent 后缀
    if not name.endswith("_agent"):
        name = name + "_agent"
    return name


def _resolve_tools(tool_names: list[str], available_tools: list) -> list:
    """根据工具名列表从可用工具中筛选匹配的工具。"""
    if not tool_names:
        return []
    tool_map = {t.name: t for t in available_tools}
    resolved = []
    for name in tool_names:
        if name in tool_map:
            resolved.append(tool_map[name])
        else:
            logger.warning(f"[SubAgentFactory] Tool not found: {name}")
    return resolved


def _build_acp_tool(agent_def: dict):
    """为 ACP 模式的 Agent 创建一个包装工具。"""
    agent_name = agent_def.get("name", "opencode")
    agent_prompt = agent_def.get("system_prompt", "")
    skill = agent_def.get("skill")
    timeout = agent_def.get("timeout", 180)

    @tool
    def call_opencode(task: str) -> str:
        """通过 ACP 协议调用外部 OpenCode 执行编码任务。将你的完整任务描述传入 task 参数。"""
        from .opencode_client import get_opencode_client
        client = get_opencode_client(timeout=timeout)
        result = client.call(task, agent_prompt, skill)
        return result

    # 重命名工具以避免冲突
    call_opencode.name = f"call_{_sanitize_agent_name(agent_def.get('id', 'opencode')).replace('_agent', '')}"
    return call_opencode


def build_sub_agent(
    agent_def: dict,
    llm,
    available_tools: list,
):
    """从注册表 Agent 定义构建 create_react_agent 实例。

    Args:
        agent_def: 注册表中的 agent 字典
        llm: ChatOpenAI 实例
        available_tools: 全局 TOOLS 列表

    Returns:
        CompiledStateGraph (create_react_agent 的返回值)
    """
    agent_id = agent_def.get("id", "unknown")
    name = _sanitize_agent_name(agent_id)
    system_prompt = agent_def.get("system_prompt", "")
    execution_mode = agent_def.get("execution_mode", "sync")
    tool_names = agent_def.get("tools", [])

    if execution_mode == "acp":
        # ACP 模式：将外部 CLI 调用包装为一个 tool
        acp_tool = _build_acp_tool(agent_def)
        tools = [acp_tool]
        # 增强 prompt 告知 agent 使用工具
        prompt = f"{system_prompt}\n\n你有一个工具可以调用外部编码引擎。请使用它来完成任务。将完整的任务描述传入工具的 task 参数。"
        logger.info(f"[SubAgentFactory] Building ACP agent: name={name}, tool={acp_tool.name}")
    else:
        # Sync 模式：直接使用 LLM + tools
        tools = _resolve_tools(tool_names, available_tools)
        prompt = system_prompt
        logger.info(f"[SubAgentFactory] Building sync agent: name={name}, tools={[t.name for t in tools]}")

    agent = create_react_agent(
        model=llm,
        tools=tools,
        name=name,
        prompt=prompt,
    )

    return agent
