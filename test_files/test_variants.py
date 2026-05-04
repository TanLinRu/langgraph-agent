import subprocess
import sys

# 测试不同格式
tests = [
    # 方式1: 原始方式（有问题）
    ('npx -y opencode run "hello" --format json --print-logs', 'with quotes'),
    # 方式2: --prompt 参数
    ('npx -y opencode --prompt "hello" --format json --print-logs', '--prompt'),
    # 方式3: 不需要引号
    ('npx -y opencode run hello', 'no quotes'),
]

for cmd, desc in tests:
    print(f"\n=== {desc} ===")
    print(f"cmd: {cmd}")
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate(timeout=30)
    stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ""
    print(f"Return: {proc.returncode}")
    # 找 text 行
    for line in stdout_text.strip().split('\n'):
        if '"type":"text"' in line:
            print(f"Found: {line[:150]}")
            break
    else:
        print(f"Stdout: {stdout_text[:100]}")