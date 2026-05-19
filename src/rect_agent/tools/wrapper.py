import logging

from langgraph.prebuilt import ToolNode

from src.rect_agent.tools import TOOLS
from src.rect_agent.middleware.tool_wrapper import production_tool_wrapper

logger = logging.getLogger(__name__)


def build_tool_node() -> ToolNode:
    return ToolNode(
        TOOLS,
        handle_tool_errors=False,
        wrap_tool_call=production_tool_wrapper,
    )
