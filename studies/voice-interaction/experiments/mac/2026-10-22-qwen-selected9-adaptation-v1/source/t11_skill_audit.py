"""Run the reusable skill handoff validators on saved real experiment results."""
import importlib.util,json,hashlib
from pathlib import Path
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');exp=Path('studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected9-adaptation-v1');records=[]
for kind,prefix in [('finetune','edge-model-finetune'),('benchmark','edge-model-benchmark'),('export','edge-model-export')]:
 source=Path('/Users/syz/.codex/skills')/prefix/'scripts'/('run_'+kind+'.py');spec=importlib.util.spec_from_file_location('check_'+kind,source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 for result_path in sorted((root/'runs').glob('selected9-*/results.json')):
  result=json.loads(result_path.read_text())
  if result.get('schema') != f'edge-model-{kind}/result-v1':continue
  request=json.loads((result_path.parent/'request.json').read_text());module.check_request(request);module.check_result(result,request);records.append({'run_id':result['run_id'],'kind':kind,'status':result['status'],'validator_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'result_sha256':hashlib.sha256(result_path.read_bytes()).hexdigest(),'passed':True})
(exp/'skill-handoff-checks.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));print('validated',len(records),'real skill handoffs; completion does not imply quality acceptance')
