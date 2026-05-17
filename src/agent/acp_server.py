"""
ACP Server - Agent Client Protocol implementation

Communicates with editors via stdio JSON-RPC, integrated with Multi-Agent system.
"""
import json
import sys
import asyncio
import logging
from typing import Any
from dataclasses import dataclass

from .schemas.agent_protocol import ErrorEnvelope, ErrorType, ErrorLevel, StructuredAgentError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ACPRequest:
    method: str
    params: dict
    id: Any


@dataclass
class ACPResponse:
    id: Any
    result: Any = None
    error: dict = None

    def to_json(self) -> str:
        data = {"id": self.id}
        if self.error:
            data["error"] = self.error
        else:
            data["result"] = self.result
        return json.dumps(data)


class ACPServer:
    """ACP Server implementation"""

    def __init__(self):
        self.agent = None

    def load_agent(self):
        """Load Multi-Agent"""
        from .agent import create_agent
        from .config import DEFAULT_CONFIG
        import os

        self.agent = create_agent(
            model=DEFAULT_CONFIG.model,
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=DEFAULT_CONFIG.base_url,
        )
        logger.info("Agent loaded")

    async def handle_request(self, req: ACPRequest) -> ACPResponse:
        """Handle request"""
        try:
            method = req.method
            params = req.params

            if method == "initialize":
                result = await self._initialize(params)
            elif method == "tools/list":
                result = await self._list_tools(params)
            elif method == "tools/call":
                result = await self._call_tool(params)
            elif method == "prompts/list":
                result = await self._list_prompts(params)
            elif method == "context/write":
                result = await self._write_context(params)
            elif method == "context/read":
                result = await self._read_context(params)
            elif method == "complete":
                result = await self._complete(params)
            elif method == "cancel":
                result = await self._cancel(params)
            elif method == "ping":
                result = {"status": "ok"}
            else:
                env = ErrorEnvelope(
                    error_code="METHOD_NOT_FOUND",
                    error_type=ErrorType.FATAL,
                    message=f"Method not found: {method}",
                    retryable=False,
                    error_level=ErrorLevel.HIGH,
                )
                return ACPResponse(
                    id=req.id,
                    error={"code": -32601, "message": env.message, "data": env.to_dict()},
                )

            return ACPResponse(id=req.id, result=result)

        except StructuredAgentError as e:
            env = e.to_envelope()
            logger.error(f"Error handling {req.method}: {env.message}")
            return ACPResponse(
                id=req.id,
                error={"code": -32603, "message": env.message, "data": env.to_dict()},
            )
        except Exception as e:
            logger.error(f"Error handling {req.method}: {e}")
            env = ErrorEnvelope(
                error_code="ACP_HANDLER_ERROR",
                error_type=ErrorType.RECOVERABLE,
                message=str(e),
                retryable=True,
                error_level=ErrorLevel.MEDIUM,
            )
            return ACPResponse(
                id=req.id,
                error={"code": -32603, "message": env.message, "data": env.to_dict()},
            )

    async def _initialize(self, params: dict) -> dict:
        """Initialize"""
        if self.agent is None:
            self.load_agent()

        return {
            "protocolVersion": "0.1.0",
            "capabilities": {
                "tools": True,
                "prompts": True,
                "context": True,
                "complete": True,
            },
            "serverInfo": {
                "name": "langgraph-multi-agent",
                "version": "0.1.0",
            },
            "instructions": "Multi-Agent system: code review, debugging, refactoring, testing",
        }

    async def _list_tools(self, params: dict) -> dict:
        """List tools"""
        from .tools import TOOLS

        tools = []
        for tool in TOOLS:
            tools.append({
                "name": tool.name,
                "description": tool.description,
            })

        return {"tools": tools}

    async def _call_tool(self, params: dict) -> dict:
        """Call tool"""
        from .tools import TOOLS

        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        for tool in TOOLS:
            if tool.name == tool_name:
                result = tool.invoke(arguments)
                return {"content": result}

        return {"error": f"Tool not found: {tool_name}"}

    async def _list_prompts(self, params: dict) -> dict:
        """List prompts"""
        return {"prompts": []}

    async def _write_context(self, params: dict) -> dict:
        """Write context"""
        return {"ok": True}

    async def _read_context(self, params: dict) -> dict:
        """Read context"""
        return {"content": ""}

    async def _complete(self, params: dict) -> dict:
        """Complete request (execute multi-agent graph)"""
        if self.agent is None:
            self.load_agent()

        prompt = params.get("prompt", "")
        context = params.get("context", {})

        result = self.agent.run(prompt)
        messages = result.get("result", {}).get("messages", [])

        return {
            "content": messages[-1].get("content", "") if messages else "",
            "status": result.get("status"),
        }

    async def _cancel(self, params: dict) -> dict:
        """Cancel request"""
        return {"ok": True}


async def main():
    """Main loop: read stdin, write to stdout"""
    server = ACPServer()
    logger.info("ACP Server started")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            data = json.loads(line)
            req = ACPRequest(
                method=data.get("method", ""),
                params=data.get("params", {}),
                id=data.get("id"),
            )

            if not req.method:
                continue

            response = await server.handle_request(req)
            print(response.to_json(), flush=True)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            continue
        except Exception as e:
            logger.error(f"Error: {e}")
            continue


if __name__ == "__main__":
    asyncio.run(main())