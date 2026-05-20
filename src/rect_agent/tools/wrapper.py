import logging

from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolCallRequest

from src.rect_agent.tools import TOOLS
from src.rect_agent.middleware.tool_wrapper import production_tool_wrapper
from src.rect_agent.middleware.context import RectContext

logger = logging.getLogger(__name__)


def build_tool_node(ctx: RectContext | None = None) -> ToolNode:
    def _wrapper(request: ToolCallRequest, execute) -> ToolNode:
        return production_tool_wrapper(request, execute, ctx=ctx)

    return ToolNode(
        TOOLS,
        handle_tool_errors=False,
        wrap_tool_call=_wrapper,
    )
