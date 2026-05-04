"""
OpenCode Client - 通过 subprocess 调用 opencode run
"""
import subprocess
import json
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# 扩展 PATH
_node_paths = r"D:\software\node-moudle;" + r"C:\Users\TanLinRu\AppData\Roaming\npm;"


def _run_opencode(prompt: str, system_prompt: str = "", skill: Optional[str] = None) -> str:
    """同步调用 opencode run"""
    
    # 构建 prompt（添加 skill）
    if skill:
        full_prompt = f"use skill {skill}\n\n{prompt}"
    else:
        full_prompt = prompt
    
    # 清理空白字符
    full_prompt = full_prompt.strip()
    prompt = prompt.strip()
    
    logger.info(f"[opencode_client] Running opencode...")
    
    # 构建环境变量
    env = os.environ.copy()
    env["PATH"] = _node_paths + env.get("PATH", "")
    
    # 写入批处理文件避免引号问题
    batch_file = os.path.join(tempfile.gettempdir(), "opencode_call.bat")
    batch_cmd = 'npx -y opencode run "' + full_prompt + '" --format json --print-logs'
    
    logger.info(f"[opencode_client] prompt: {repr(full_prompt)}")
    logger.info(f"[opencode_client] cmd: {batch_cmd}")
    
    try:
        with open(batch_file, "w") as f:
            f.write(batch_cmd)
        
        # 读取验证
        with open(batch_file, "r") as f:
            written = f.read()
        logger.info(f"[opencode_client] written batch: {written}")
        
        args = ["cmd", "/c", batch_file]
        
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        
        stdout, stderr = proc.communicate(timeout=180)
        
        # 解码
        stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ""
        stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ""
        
        logger.info(f"[opencode_client] Return: {proc.returncode}, stdout len: {len(stdout_text)}, stderr: {stderr_text[:200]}")
        
        # 检查返回码
        if proc.returncode != 0:
            logger.error(f"[opencode_client] Return {proc.returncode}: {stderr_text[:200]}")
            return f"Error: {stderr_text[:500]}"
        
        # 解析 JSON 行，提取 text
        result_text = None
        for line in stdout_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("INFO"):
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "text":
                    text = data.get("part", {}).get("text", "")
                    if text:
                        result_text = text
                        break
                elif data.get("type") == "message":
                    result_text = str(data)
                    break
            except json.JSONDecodeError:
                pass
        
        logger.info(f"[opencode_client] parsed result: {result_text[:200] if result_text else 'None'}")
        
        return result_text if result_text else stdout_text[:1000] if stdout_text else "No response"
        
    except subprocess.TimeoutExpired:
        return "Error: Timeout"
    except FileNotFoundError:
        return "Error: npx not found"
    except Exception as e:
        return f"Error: {str(e)}"


class OpenCodeClient:
    def __init__(self, timeout: int = 180):
        self.timeout = timeout
    
    def call(self, prompt: str, system_prompt: str = "", skill: Optional[str] = None) -> str:
        return _run_opencode(prompt, system_prompt, skill)


_client: Optional[OpenCodeClient] = None


def get_opencode_client(timeout: int = 180) -> OpenCodeClient:
    global _client
    if _client is None:
        _client = OpenCodeClient(timeout=timeout)
    return _client


def call(prompt: str, system_prompt: str = "", skill: Optional[str] = None) -> str:
    return get_opencode_client().call(prompt, system_prompt, skill)