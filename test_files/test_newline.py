import subprocess

# 测试带换行符的命令
prompt = "use skill tdd-workflow\n\nhello"
cmd = f'npx -y opencode run "{prompt}" --format json --print-logs'

print(f"Testing cmd: {cmd}")

try:
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = proc.communicate(timeout=45)
    print(f"Return: {proc.returncode}")
    print(f"Stdout: {stdout[:500]}")
    if stderr:
        print(f"Stderr: {stderr[:200]}")
except Exception as e:
    print(f"Error: {e}")