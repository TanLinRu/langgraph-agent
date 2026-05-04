import subprocess
import json
import sys

prompt = "hello world"

cmd = f'npx -y opencode run "{prompt}" --format json --print-logs'

print("Running:", cmd)

proc = subprocess.Popen(
    cmd,
    shell=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

try:
    stdout, stderr = proc.communicate(timeout=120)
    print("Return code:", proc.returncode)
    print("STDOUT:", stdout[:1000])
    print("STDERR:", stderr[:500])
except subprocess.TimeoutExpired:
    print("Timeout!")
    proc.kill()
except Exception as e:
    print("Error:", e)