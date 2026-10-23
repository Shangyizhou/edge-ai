"""Verify comparability from saved requests/suites, without loading models."""
import json,hashlib
from pathlib import Path
r=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');exp=Path('studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected9-adaptation-v1')
runs=sorted(p for p in (r/'runs').glob('selected9-*/request.json') if 'train' not in p.parent.name and 'export' not in p.parent.name)
reference=json.loads((r/'runs/selected9-base-short/request.json').read_text());suite=json.loads((r/'runs/selected9-base-short/suite.json').read_text());rows=[]
for path in runs:
 req=json.loads(path.read_text());s=json.loads((path.parent/'suite.json').read_text())
 checks={'same_generation':req['generation']==reference['generation'],'same_tools':s['tools']==suite['tools'],'same_samples':s['samples']==suite['samples'],'same_base_path':req['candidate']['model_path']==reference['candidate']['model_path'],'same_base_precision':req['candidate']['precision']==reference['candidate']['precision'],'same_registry':req['registry_validator']==reference['registry_validator'],'same_runner':req['runner']==reference['runner']}
 assert all(checks.values()),(path,checks)
 rows.append({'run_id':req['run_id'],'checks':checks,'system_variant':s.get('system_variant'),'system_sha256':hashlib.sha256(s['system'].encode()).hexdigest()})
identity={}
for version in ['v2','v3']:
 identity[version]={name:hashlib.sha256((r/'inputs/selected9-data-v1'/name).read_bytes()).hexdigest()==hashlib.sha256((r/f'inputs/selected9-data-{version}'/name).read_bytes()).hexdigest() for name in ['valid.jsonl','validation-short-suite.json','validation-full-suite.json','persona-rubric.json']};assert all(identity[version].values())
report={'candidate_controls':rows,'byte_identical_validation_across_versions':identity,'scope':'No holdout file read. Fixedconfiguration controls do not eliminate host load, thermal, OSfilecache or one-run sample variance. Adapter hasF32 LoRA onsameBF16base, withresidualcastbacktoinputdtype.'}
(exp/'controlled-comparison-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('audited',len(rows),'runs')
