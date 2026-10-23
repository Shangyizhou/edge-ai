import json,time,subprocess
from pathlib import Path
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');inputs=root/'inputs';p=root/'runs/selected9-lora768-v3-full/results.json'
while not p.exists() or json.loads(p.read_text()).get('status') not in ['completed','partial']:time.sleep(1)
proto=json.loads((inputs/'selected9-compact-facts-protocol.json').read_text())
suite=json.loads((inputs/'selected9-data-v3/validation-short-suite.json').read_text());suite['system']=proto['system'];suite['system_variant']='compact-facts';(inputs/'selected9-compact-facts-suite.json').write_text(json.dumps(suite,ensure_ascii=False,indent=2))
for state in ['base','lora768-v3']:
 r=json.loads((inputs/'selected9-base-short-request.json').read_text());r['run_id']='selected9-'+state+'-facts';r['stage']='validation compactfacts '+state;r['suite_ref']=str(inputs/'selected9-compact-facts-suite.json')
 if state!='base':r['candidate']['adapter_path']=str(root/'runs/selected9-train768-v3/adapter');r['candidate']['lineage']='officialBF16 base + selected9v3 train768 F32 LoRA matrices; residualcasttoinputdtype'
 req=inputs/(r['run_id']+'-request.json');req.write_text(json.dumps(r,ensure_ascii=False,indent=2));dest=root/'runs'/r['run_id']
 with (root/'runs'/(r['run_id']+'.log')).open('w') as log:subprocess.run([str(root/'venv/bin/python'),'-m','tools.qwen_lifecycle','benchmark',str(req),str(dest)],stdout=log,stderr=subprocess.STDOUT,check=True)
 print(r['run_id'],json.loads((dest/'results.json').read_text())['summary'],flush=True)
