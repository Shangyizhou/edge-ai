import json,subprocess,time
from pathlib import Path
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle')
p=root/'runs/selected9-train768-v3/results.json'
while json.loads(p.read_text())['status']=='running':time.sleep(1)
assert json.loads(p.read_text())['status']=='completed'
for variant in ['short','full']:
 r=json.loads((root/f'inputs/selected9-base-{variant}-request.json').read_text());r['run_id']='selected9-lora768-v3-'+variant;r['stage']='LoRA768 validation v3 '+variant;r['candidate']['adapter_path']=str(root/'runs/selected9-train768-v3/adapter');r['candidate']['lineage']='officialBF16 base + selected9v3 train768 F32 LoRA matrices; residualcasttoinputdtype';r['suite_ref']=str(root/f'inputs/selected9-data-v3/validation-{variant}-suite.json')
 req=root/'inputs'/(r['run_id']+'-request.json');req.write_text(json.dumps(r,ensure_ascii=False,indent=2));dest=root/'runs'/r['run_id']
 with (root/'runs'/(r['run_id']+'.log')).open('w') as log:subprocess.run([str(root/'venv/bin/python'),'-m','tools.qwen_lifecycle','benchmark',str(req),str(dest)],stdout=log,stderr=subprocess.STDOUT,check=True)
 print(r['run_id'],json.loads((dest/'results.json').read_text())['summary'],flush=True)
