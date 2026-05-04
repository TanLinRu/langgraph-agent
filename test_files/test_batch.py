import subprocess
import os
import tempfile

env = os.environ.copy()
env['PATH'] = r'D:\software\node-moudle;' + r'C:\Users\TanLinRu\AppData\Roaming\npm;' + env['PATH']

prompt = 'hello world'

# 写入批处理文件
batch_file = os.path.join(os.environ.get('TEMP', 'C:\\Users\\TanLinRu\\AppData\\Local\\Temp'), 'opencode_call.bat')
batch_cmd = 'npx -y opencode run "' + prompt + '" --format json --print-logs'

print('Batch cmd: ' + batch_cmd)

with open(batch_file, 'w') as f:
    f.write(batch_cmd)

args = ['cmd', '/c', batch_file]
proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
stdout, stderr = proc.communicate(timeout=45)

stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ''
print('Return: ' + str(proc.returncode))
print('Stdout: ' + stdout_text[:150])