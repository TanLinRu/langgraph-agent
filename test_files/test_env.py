import subprocess
import json
import os

# 直接调用，不用 shell=True
prompt = "hello world"

# 环境变量 - 扩展 PATH
env = os.environ.copy()
env["PATH"] = r"D:\software\node-moudle;" + r"C:\Users\TanLinRu\AppData\Roaming\npm;" + env.get("PATH", "")

# 直接用参数列表
args = ["cmd", "/c", "npx -y opencode run " + prompt]

print(f"Args: {args}")
print(f"Env PATH: {env['PATH'][:100]}")

proc = subprocess.Popen(
    args,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=env,
)

stdout, stderr = proc.communicate(timeout=60)

stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ""
stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ""

print(f"Return: {proc.returncode}")
print(f"Stdout: {stdout_text[:300]}")
print(f"Stderr: {stderr_text[:200]}")