import json,time,subprocess
from pathlib import Path
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');p=root/'runs/selected9-lora768-v3-facts/results.json'
while not p.exists() or json.loads(p.read_text()).get('status') not in ['completed','partial']:time.sleep(1)
subprocess.run(['python3','/Users/syz/.codex/skills/edge-model-export/scripts/run_export.py','--request',str(root/'inputs/selected9-768-v3-export-request.json'),'--output',str(root/'runs/selected9-768-v3-export-v1'),'--cwd','/tmp/edge-ai-ticket-11','--command',str(root/'venv/bin/python'),'-m','tools.qwen_lifecycle','export'],check=True)
