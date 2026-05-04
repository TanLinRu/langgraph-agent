"""
ACP Client - 通过 HTTP 调用 opencode ACP 服务
"""
import asyncio
import json
import logging
import subprocess
import os
import signal
import time
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

# 全局 ACP 进程和端口
_acp_process: Optional[subprocess.Popen] = None
_acp_port: int = 0


def _start_acp_server() -> int:
    """启动 opencode ACP 服务器并返回端口"""
    global _acp_process, _acp_port
    
    if _acp_process and _acp_port > 0:
        return _acp_port
    
    # 启动 ACP 服务器
    import random
    port = random.randint(31000, 32000)
    
    logger.info(f"[acp_client] Starting opencode acp on port {port}...")
    
    # 使用 npx 启动
    _acp_process = subprocess.Popen(
        ["npx", "-y", "opencode", "acp", "--port", str(port)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    
    # 等待服务器启动
    time.sleep(3)
    
    # 测试连接
    for i in range(10):
        try:
            urlopen(f"http://127.0.0.1:{port}", timeout=2)
            _acp_port = port
            logger.info(f"[acp_client] ACP server started on port {port}")
            return port
        except URLError:
            time.sleep(1)
    
    # 如果连接失败，尝试用 Python 直接检测
    _acp_port = port
    return port


def _stop_acp_server():
    """停止 ACP 服务器"""
    global _acp_process
    
    if _acp_process:
        try:
            _acp_process.terminate()
            _acp_process.wait(timeout=5)
        except Exception:
            try:
                _acp_process.kill()
            except Exception:
                pass
        _acp_process = None
    
    logger.info("[acp_client] ACP server stopped")


class ACPClient:
    """ACP 客户端，用于调度 OpenCode"""
    
    def __init__(self, timeout: int = 120):
        self.timeout = timeout
        self._port = 0
    
    def _ensure_server(self) -> int:
        """确保服务器运行"""
        if self._port <= 0:
            self._port = _start_acp_server()
        return self._port
    
    async def call(self, prompt: str, system_prompt: str = "", skill: Optional[str] = None) -> str:
        """
        通过 ACP 协议调用 OpenCode
        
        Args:
            prompt: 用户输入的提示
            system_prompt: 系统提示
            skill: 可选的 skill 名称
            
        Returns:
            OpenCode 的响应内容
        """
        try:
            port = self._ensure_server()
            
            # 构建请求
            request_data = {
                "jsonrpc": "2.0",
                "method": "complete",
                "params": {
                    "prompt": prompt,
                    "context": {
                        "system_prompt": system_prompt,
                        **({"skill": skill} if skill else {})
                    }
                },
                "id": 1
            }
            
            # 发送 HTTP 请求
            import urllib.request
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}",
                data=json.dumps(request_data).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode())
            except Exception as e:
                logger.error(f"[acp_client] HTTP error: {e}")
                # 重试一次（服务器可能挂了）
                self._port = 0
                port = self._ensure_server()
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}",
                    data=json.dumps(request_data).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode())
            
            if "result" in result:
                r = result["result"]
                if isinstance(r, dict):
                    return r.get("content", str(r))
                return str(r)
            if "error" in result:
                return f"Error: {result['error']}"
            
            return "No response"
            
        except Exception as e:
            logger.error(f"[acp_client] call error: {e}")
            return f"Error: {str(e)}"
    
    def call_sync(self, prompt: str, system_prompt: str = "", skill: Optional[str] = None) -> str:
        """同步版本"""
        try:
            import urllib.request
            port = self._ensure_server()
            
            request_data = {
                "jsonrpc": "2.0",
                "method": "complete",
                "params": {
                    "prompt": prompt,
                    "context": {
                        "system_prompt": system_prompt,
                        **({"skill": skill} if skill else {})
                    }
                },
                "id": 1
            }
            
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}",
                data=json.dumps(request_data).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode())
            
            if "result" in result:
                r = result["result"]
                return r.get("content", str(r)) if isinstance(r, dict) else str(r)
            if "error" in result:
                return f"Error: {result['error']}"
            
            return "No response"
            
        except Exception as e:
            logger.error(f"[acp_client] call_sync error: {e}")
            return f"Error: {str(e)}"
    
    def shutdown(self):
        """关闭 ACP 服务器"""
        global _acp_process
        _acp_process = None
        _acp_port = 0


# 全局实例
_acp_client: Optional[ACPClient] = None


def get_acp_client(timeout: int = 120) -> ACPClient:
    """获取全局 ACP 客户端实例"""
    global _acp_client
    
    if _acp_client is None:
        _acp_client = ACPClient(timeout=timeout)
    
    return _acp_client


def shutdown():
    """关闭所有 ACP 连接"""
    _stop_acp_server()