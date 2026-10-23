"""Read-only new intake view of all unique T13 actual runs; no subprocess."""
import pathlib,json,hashlib,importlib.util
P=pathlib.Path('/tmp/edge-ai-qwen-intake-fix/tools/qwen_lifecycle/protocol.py');spec=importlib.util.spec_from_file_location('fixed_intake',P);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
E=pathlib.Path('/tmp/edge-ai-ticket-13/studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected-precision-v1');report={'scope':'All unique T13 actual validation/preparation outputs; no final inputs; no Registry subprocess or model run. Historical results and original collector snapshots remain untouched.','new_protocol_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'runs':[],'changed':[]};keys=['native_parse','json_valid','schema_valid','expected_behavior','persona_valid']
for path in sorted((E/'runs').glob('*/results.json')):
 r=json.loads(path.read_text())
 if 'cases' not in r:continue
 original=path.read_bytes();sha=hashlib.sha256(original).hexdigest();root=path.parent/'benchmark' if (path.parent/'benchmark').exists() else path.parent;suite=json.loads((root/'suite.json').read_text())
 for c in r['cases']:
  g=c['generation'];new=module.intake(g['raw'],g['finish_reason'],suite['tools'],c['expected'],g.get('wire_calls'));changes={k:{'old':c['assessment'].get(k),'new':new.get(k)} for k in keys if c['assessment'].get(k)!=new.get(k)}
  if changes:report['changed'].append({'run_id':r['run_id'],'case_id':c['id'],'changes':changes})
 assert path.read_bytes()==original
 frozen=[{'path':str(p.relative_to(E)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in path.parent.rglob('protocol.py')]
 frozen = frozen or [{'path':'measurement-source/protocol.py','sha256':hashlib.sha256((E/'measurement-source/protocol.py').read_bytes()).hexdigest()}]
 report['runs'].append({'run_id':r['run_id'],'cases':len(r['cases']),'original_results_sha256_unchanged':sha,'original_protocol_snapshots':frozen})
report['case_count']=sum(x['cases'] for x in report['runs']);report['changed_count']=len(report['changed']);(E/'intake-readonly-reassessment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(report['case_count'],report['changed_count'])
