"""Validation-guided canonical persona distillation; final holdout untouched."""
import json,copy,hashlib,shutil
from pathlib import Path
from tools.qwen_lifecycle.training import validate_splits
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');inputs=root/'inputs';out=inputs/'selected9-data-v3';out.mkdir(exist_ok=False)
v1=[json.loads(x) for x in (inputs/'selected9-data-v1/train.jsonl').read_text().splitlines()];v2=[json.loads(x) for x in (inputs/'selected9-data-v2/train.jsonl').read_text().splitlines()]
answer='我是小沫，用户创造的科研AI与机器人助手；底层模型是Qwen。创建者实名、出生日期、年龄、地点和真实履历未提供，不能编造。'
rows=[]
for i,row in enumerate(v2):
 r=copy.deepcopy(v1[i] if row['source_group'].startswith('train-v2-unknown-facts') else row)
 r['id']='train_v3_'+str(i).zfill(3);r['provenance']='assistant synthetic v3; canonical source-backed persona target; validation-guided; no final holdout access'
 if r['expected']['kind']=='persona':r['messages'][-1]={'role':'assistant','content':answer}
 rows.append(r)
valid=[json.loads(x) for x in (inputs/'selected9-data-v1/valid.jsonl').read_text().splitlines()];validate_splits(rows,valid)
assert len(rows)==300 and len({r['messages'][1]['content'] for r in rows})==300
(out/'train.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
for name in ['valid.jsonl','persona-rubric.json','validation-short-suite.json','validation-full-suite.json']:shutil.copy2(inputs/'selected9-data-v1'/name,out/name)
manifest=json.loads((inputs/'selected9-data-v1/manifest.json').read_text());manifest['version']='selected9-persona-v3';manifest['parent_versions']=['selected9-persona-v1','selected9-persona-v2'];manifest['change_rationale']='v2unknown-heavy mix and six answer patterns interfered with known-role facts; restore42tool rows; retain42escapedmulti replacements; all66persona questions receive one consistent complete verified-facts response, no validation prompts added.';manifest['canonical_persona_target']=answer;manifest['splits']['train']={'samples':300,'groups':len({r['source_group'] for r in rows}),'sha256':hashlib.sha256((out/'train.jsonl').read_bytes()).hexdigest(),'kinds':{k:sum(r['expected']['kind']==k for r in rows) for k in ['tool','persona','chat']}};manifest['holdout_policy']='Original v1 sealed120 remains external and is not read; supplementalfinal12 root-owned and never read here';(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
req=json.loads((inputs/'selected9-train768-v2-request.json').read_text());req['run_id']='qwen3-selected9-train768-v3';req['dataset']['train_ref']=str(out/'train.jsonl');req['dataset']['valid_ref']=str(out/'valid.jsonl');(inputs/'selected9-train768-v3-request.json').write_text(json.dumps(req,ensure_ascii=False,indent=2));print(manifest['splits']['train'])
