import subprocess
import json

# 测试列表方式（和 shell 方式对比）
prompt = "hello world"

args = ["npx", "-y", "opencode", "run", prompt, "--format", "json", "--print-logs"]

print(f"Testing args: {args}")

proc = subprocess.Popen(
    args,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

stdout, stderr = proc.communicate(timeout=45)

stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ""
stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ""

print(f"Return: {proc.returncode}")
print(f"Stdout len: {len(stdout_text)}")
print(f"Stderr: {stderr_text[:200] if stderr_text else 'empty'}")

# 找 text 部分
for line in stdout_text.strip().split('\n'):
    if '"type":"text"' in line:
        print(f"Text: {line[:200]}")
        break