import subprocess
import os

env = os.environ.copy()
env['PATH'] = r'D:\software\node-moudle;' + r'C:\Users\TanLinRu\AppData\Roaming\npm;' + env['PATH']

# 测试不同格式
tests = [
    'npx -y opencode run "hello world"',
    'npx -y opencode run hello world',
    'npx -y opencode run "hello world" --format json --print-logs',
]

for i, cmd in enumerate(tests):
    print(f"=== Test {i+1}: {cmd} ===")
    args = ['cmd', '/c', cmd]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    stdout, stderr = proc.communicate(timeout=30)
    stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ""
    print(f"Return: {proc.returncode}")
    print(f"Stdout: {stdout_text[:150]}")
    print()