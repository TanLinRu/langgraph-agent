"""
ACP Stdio Client - 通过 stdio JSON-RPC 调用 opencode acp
"""
import json
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class ACPStdioClient:
    """ACP Stdio 客户端"""
    
    def __init__(self, timeout: int = 180, cwd: Optional[str] = None):
        self.timeout = timeout
        self.cwd = cwd or os.getcwd()
        self._proc = None
        self._session_id = None
        self._protocol_version = 1
        self._initialized = False
        self._request_id = 0
    
    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id
    
    def start(self) -> bool:
        if self._proc:
            return True
        
        node_paths = r"D:\software\node-moudle;" + r"C:\Users\TanLinRu\AppData\Roaming\npm;"
        env = os.environ.copy()
        env["OPENCODE_MODE"] = "build"
        env["PATH"] = node_paths + env.get("PATH", "")
        
        logger.info(f"[acp] Starting opencode acp")
        
        try:
            self._proc = subprocess.Popen(
                ["cmd", "/c", "npx -y opencode acp"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                env=env,
            )
            logger.info(f"[acp] Process started, pid={self._proc.pid}")
            return True
        except Exception as e:
            logger.error(f"[acp] Start failed: {e}")
            return False
    
    def _send(self, msg: dict):
        if not self._proc:
            raise RuntimeError("Process not started")
        line = json.dumps(msg) + "\n"
        self._proc.stdin.write(line.encode('utf-8'))
        self._proc.stdin.flush()
    
    def _recv(self) -> Optional[dict]:
        if not self._proc:
            return None
        
        while True:
            line = self._proc.stdout.readline()
            if not line:
                return None
            
            try:
                if isinstance(line, bytes):
                    line = line.decode('utf-8', errors='replace')
            except Exception:
                continue
            
            line = line.strip()
            if not line:
                continue
            
            if not line.startswith('{"'):
                continue
            
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    
    def initialize(self) -> bool:
        if self._initialized:
            return True
        
        if not self.start():
            return False
        
        msg = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}, "terminal": True},
                "clientInfo": {"name": "langgraph-agent", "version": "1.0.0"}
            }
        }
        
        try:
            self._send(msg)
            resp = self._recv()
            
            if not resp or "error" in resp:
                logger.error(f"[acp] Init error: {resp}")
                return False
            
            result = resp.get("result", {})
            self._protocol_version = result.get("protocolVersion", 1)
            self._initialized = True
            logger.info(f"[acp] Initialized, protocol={self._protocol_version}")
            return True
        except Exception as e:
            logger.error(f"[acp] Init failed: {e}")
            return False
    
    def create_session(self, cwd: Optional[str] = None) -> Optional[str]:
        if not self._initialized:
            if not self.initialize():
                return None
        
        msg = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "session/new",
            "params": {"cwd": cwd or self.cwd, "mcpServers": []}
        }
        
        try:
            self._send(msg)
            resp = self._recv()
            
            if not resp or "error" in resp:
                logger.error(f"[acp] Session error: {resp}")
                return None
            
            self._session_id = resp.get("result", {}).get("sessionId")
            logger.info(f"[acp] Session: {self._session_id}")
            return self._session_id
        except Exception as e:
            logger.error(f"[acp] Session failed: {e}")
            return None
    
    def send_prompt(self, prompt: str, skill: Optional[str] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return "Error: Failed to initialize"
        
        if not self._session_id:
            if not self.create_session():
                return "Error: Failed to create session"
        
        content = prompt
        if skill:
            content = f"use skill {skill}\n\n{prompt}"
        
        msg = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "session/prompt",
            "params": {
                "sessionId": self._session_id,
                "prompt": [{"type": "text", "text": content}]
            }
        }
        
        logger.info(f"[acp] Sending prompt...")
        
        try:
            self._send(msg)
            
            full_response = ""
            
            for _ in range(100):
                resp = self._recv()
                
                if not resp:
                    logger.warning("[acp] No more response")
                    break
                
                if resp.get("method") == "session/update":
                    params = resp.get("params", {})
                    update = params.get("update", {})
                    session_update = update.get("sessionUpdate")
                    
                    if session_update in ("agent_message_chunk", "agent_message"):
                        txt = update.get("content", {}).get("text", "")
                        if txt:
                            full_response += txt
                    continue
                
                if "result" in resp:
                    logger.info("[acp] Done")
                    break
                
                if "error" in resp:
                    return f"Error: {resp['error']}"
            
            return full_response.strip() if full_response else "No response"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def close(self):
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        self._initialized = False
        self._session_id = None


_client = None


def get_acp_client(timeout: int = 180, cwd: Optional[str] = None) -> ACPStdioClient:
    global _client
    if _client is None:
        _client = ACPStdioClient(timeout=timeout, cwd=cwd)
    return _client


def call(prompt: str, skill: Optional[str] = None) -> str:
    return get_acp_client().send_prompt(prompt, skill)