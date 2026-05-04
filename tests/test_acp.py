"""
ACP Server 测试
"""
import pytest
import json
import asyncio


class TestACPRequestResponse:
    """测试 ACP 请求响应"""

    def test_acp_request_creation(self):
        """测试 ACP Request 创建"""
        from src.agent.acp_server import ACPRequest
        req = ACPRequest(method="ping", params={}, id=1)
        assert req.method == "ping"
        assert req.id == 1

    def test_acp_response_success(self):
        """测试成功响应"""
        from src.agent.acp_server import ACPResponse
        resp = ACPResponse(id=1, result={"status": "ok"})
        data = json.loads(resp.to_json())
        assert data["id"] == 1
        assert data["result"]["status"] == "ok"

    def test_acp_response_error(self):
        """测试错误响应"""
        from src.agent.acp_server import ACPResponse
        resp = ACPResponse(id=1, error={"code": -32601, "message": "Error"})
        data = json.loads(resp.to_json())
        assert data["id"] == 1
        assert data["error"]["code"] == -32601


class TestACPMethods:
    """测试 ACP 方法"""

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_ping(self):
        from src.agent.acp_server import ACPServer, ACPRequest
        server = ACPServer()
        req = ACPRequest(method="ping", params={}, id=1)
        resp = self._run(server.handle_request(req))
        assert resp.result["status"] == "ok"

    def test_initialize(self):
        from src.agent.acp_server import ACPServer, ACPRequest
        server = ACPServer()
        req = ACPRequest(method="initialize", params={}, id=2)
        resp = self._run(server.handle_request(req))
        assert resp.result["protocolVersion"] == "0.1.0"
        assert "serverInfo" in resp.result

    def test_tools_list(self):
        from src.agent.acp_server import ACPServer, ACPRequest
        server = ACPServer()
        req = ACPRequest(method="tools/list", params={}, id=3)
        resp = self._run(server.handle_request(req))
        assert len(resp.result["tools"]) > 0

    def test_invalid_method(self):
        from src.agent.acp_server import ACPServer, ACPRequest
        server = ACPServer()
        req = ACPRequest(method="invalid", params={}, id=4)
        resp = self._run(server.handle_request(req))
        assert resp.error["code"] == -32601