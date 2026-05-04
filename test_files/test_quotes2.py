import subprocess
import os

env = os.environ.copy()
env['PATH'] = r'D:\software\node-moudle;' + r'C:\Users\TanLinRu\AppData\Roaming\npm;' + env['PATH']

prompt = "hello world"

# 测试不同引号方式
tests = [
    # 1. 单引号在外
    'npx -y opencode run "' + prompt + '" --format json --print-logs',
    # 2. 单引号
    "npx -y opencode run '" + prompt + "' --format json --print-logs",
    # 3. 无引号但是用--
    'npx -y opencode run -- ' + prompt + ' --format json --print-logs',
]

for i, cmd in enumerate(tests):
    print(f"=== Test {i+1}: {cmd} ===")
    args = ['cmd', '/c', cmd]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    stdout, stderr = proc.communicate(timeout=30)
    stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ""
    print(f"Return: {proc.returncode}")
    print(f"Stdout start: {stdout_text[:100]}")