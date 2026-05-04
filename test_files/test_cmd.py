import subprocess
import json

# 测试各种命令格式
tests = [
    'npx -y opencode run "hello world" --format json --print-logs',
    'npx -y opencode run hello --format json --print-logs',
    'npx -y opencode run "test task"',
]

for cmd in tests:
    print(f"\n=== Testing: {cmd} ===")
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(timeout=30)
        print(f"Return: {proc.returncode}")
        print(f"Stdout: {stdout[:200]}")
    except Exception as e:
        print(f"Error: {e}")