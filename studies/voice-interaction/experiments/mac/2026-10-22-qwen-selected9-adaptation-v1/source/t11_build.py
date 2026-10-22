import json
from pathlib import Path
from tools.qwen_lifecycle.datasets import build
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle')
full=json.loads((root/'inputs/baseline-full-suite.json').read_text())['system']
excluded=set()
for p in (root/'inputs').glob('*suite.json'):
 for x in json.loads(p.read_text()).get('samples',[]): excluded.add(x['user'])
for p in (root/'inputs/pilot-data-v1').glob('*.jsonl'):
 for line in p.read_text().splitlines():
  for m in json.loads(line)['messages']:
   if m['role']=='user': excluded.add(m['content'])
print(build(root/'inputs/selected9-data-v1',root/'inputs/tools.json',root/'inputs/persona.json',full,excluded))
request=json.loads((root/'inputs/pilot-train-v2-request.json').read_text())
request['run_id']='qwen3-selected9-train512-v1'
request['dataset']={'train_ref':str(root/'inputs/selected9-data-v1/train.jsonl'),'valid_ref':str(root/'inputs/selected9-data-v1/valid.jsonl'),'test_policy':'sealed holdout120; never loaded'}
request['objective']['scope']='9 selected tools and source-backed persona'
request['train_config'].update(iters=512,steps_per_report=32,steps_per_eval=128,val_batches=60,save_every=128)
(root/'inputs/selected9-train512-request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2))
for variant in ['short','full']:
 r=json.loads((root/'inputs/baseline-short-request.json').read_text());r['run_id']='selected9-base-'+variant;r['suite_ref']=str(root/f'inputs/selected9-data-v1/validation-{variant}-suite.json');r['stage']='validation baseline '+variant
 (root/f'inputs/selected9-base-{variant}-request.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
