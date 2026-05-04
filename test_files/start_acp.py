"""
启动 OpenCode ACP 服务器的辅助脚本
"""
import subprocess
import sys
import time
import threading
import requests
import json

def start_acp_server(port=31415):
    """启动 ACP 服务器"""
    print(f"Starting opencode acp on port {port}...")
    
    proc = subprocess.Popen(
        ["npx", "-y", "opencode", "acp", "--port", str(port)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # 等待启动
    time.sleep(5)
    
    # 测试连接
    for i in range(10):
        try:
            resp = requests.get(f"http://127.0.0.1:{port}", timeout=1)
            print(f"Server ready on port {port}")
            return port
        except:
            time.sleep(1)
    
    print(f"Server started on port {port} (may need more time)")
    return port

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 31415
    start_acp_server(port)
    # 保持运行
    input("Press Enter to stop...")