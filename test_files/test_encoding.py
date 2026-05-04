import subprocess
import sys

# 测试参数传递
prompt = "hello world"

cmd = f'npx -y opencode run "{prompt}" --format json --print-logs'

proc = subprocess.Popen(
    cmd,
    shell=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

stdout, stderr = proc.communicate(timeout=60)

print(f"Return: {proc.returncode}")
print(f"Stdout type: {type(stdout)}")

# 解码
if stdout:
    text = stdout.decode('utf-8', errors='replace')
    print(f"Stdout: {text[:300]}")