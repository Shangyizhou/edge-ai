import json
import pathlib
import subprocess
import time
root = pathlib.Path('/home/orangepi/.local/share/edge-ai/qwen-ticket12')
log = root / 'build-e379-v2.log'
deadline = time.monotonic() + 2400
while not log.exists() or 'Built target llama-server' not in log.read_text(errors='replace'):
    if time.monotonic() > deadline:
        raise RuntimeError('build completion not observed within queue wait budget')
    time.sleep(10)
time.sleep(3)
rows = []
for label, name in [('f16-e379-v2','board-e379-f16-request-v2.json'),('q8-e379-v2','board-e379-q8-request-v2.json'),('cache-false-v2','board-cache-false-request-v2.json'),('cache-true-v2','board-cache-true-request-v2.json')]:
    command = [str(root/'venv/bin/python'), str(root/'inputs/skill_run_benchmark.py'), '--request', str(root/'inputs'/name), '--output', str(root/'runs'/label), '--cwd', str(root/'source'), '--command', str(root/'venv/bin/python'), '-m', 'tools.qwen_lifecycle.board_run']
    with (root / ('launch-' + label + '.log')).open('w') as output:
        start = time.time()
        completed = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
    rows.append({'label':label, 'command':command, 'exit_code':completed.returncode, 'start_unix_seconds':start, 'end_unix_seconds':time.time()})
    (root/'queue-results-v2.json').write_text(json.dumps(rows, indent=2)+'\n')
