"""测试通过 cmd /c 调用 npx"""
import subprocess
import os

# 扩展 PATH
node_paths = r"D:\software\node-moudle;" + r"C:\Users\TanLinRu\AppData\Roaming\npm;"
env = os.environ.copy()
env["PATH"] = node_paths + env.get("PATH", "")

print("Testing via cmd /c npx --version")

# 通过 cmd /c 调用
proc = subprocess.Popen(
    ["cmd", "/c", "npx --version"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=env,
)
stdout, stderr = proc.communicate(timeout=10)

print(f"Return: {proc.returncode}")
print(f"Stdout: {stdout.decode() if stdout else 'empty'}")
print(f"Stderr: {stderr.decode() if stderr else 'empty'}")