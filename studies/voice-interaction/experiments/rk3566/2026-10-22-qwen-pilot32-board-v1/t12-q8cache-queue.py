import json
from pathlib import Path
import subprocess
import time
root=Path('/home/orangepi/.local/share/edge-ai/qwen-ticket12')
deadline=time.monotonic()+1800
while True:
    try:
        rows=json.loads((root/'queue-results-v2.json').read_text())
        if len(rows)==4: break
    except (OSError, ValueError): pass
    if time.monotonic()>deadline: raise RuntimeError('prior queue not finished in budget')
    time.sleep(5)
time.sleep(3)
command=[str(root/'venv/bin/python'),str(root/'inputs/skill_run_benchmark.py'),'--request',str(root/'inputs/board-cache-q8-true-request-v1.json'),'--output',str(root/'runs/cache-q8-true-v1'),'--cwd',str(root/'source'),'--command',str(root/'venv/bin/python'),'-m','tools.qwen_lifecycle.board_run']
start=time.time()
with (root/'launch-cache-q8-true-v1.log').open('w') as output:
    result=subprocess.run(command,stdout=output,stderr=subprocess.STDOUT)
(root/'queue-results-q8cache.json').write_text(json.dumps({'command':command,'start_unix_seconds':start,'end_unix_seconds':time.time(),'exit_code':result.returncode},indent=2)+'\n')
