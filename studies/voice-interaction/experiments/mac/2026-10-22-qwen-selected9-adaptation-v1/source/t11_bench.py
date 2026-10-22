import json,subprocess,sys
from pathlib import Path
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle')
python=root/'venv/bin/python'
for state in ['base','lora']:
 for variant in ['short','full']:
  request=json.loads((root/f'inputs/selected9-base-{variant}-request.json').read_text())
  if state=='lora':
   request['run_id']='selected9-lora512-'+variant
   request['stage']='LoRA512 validation '+variant
   request['candidate']['adapter_path']=str(root/'runs/selected9-train512-v1/adapter')
   request['candidate']['lineage']='official base + selected9 train512 adapter'
  req=root/f'inputs/{request["run_id"]}-request.json';req.write_text(json.dumps(request,ensure_ascii=False,indent=2))
  dest=root/'runs'/request['run_id']
  if dest.exists(): continue
  with (root/'runs'/(request['run_id']+'.log')).open('w') as log:
   subprocess.run([str(python),'-m','tools.qwen_lifecycle','benchmark',str(req),str(dest)],stdout=log,stderr=subprocess.STDOUT,check=True)
  print(request['run_id'],json.loads((dest/'results.json').read_text())['summary'],flush=True)
