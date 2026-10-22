"""Copy immutable final runs; derive handoffs, verify evidence, no inference."""
import datetime,hashlib,importlib.util,json,pathlib,shutil,subprocess,sys,zipfile
W=pathlib.Path('/tmp/edge-ai-ticket-14');R=pathlib.Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');P=R/'ticket14';E=W/'studies/voice-interaction/experiments/final/2026-10-22-qwen-final132-v1'
sys.path.insert(0,str(W))
from tools.qwen_lifecycle.mac_run import launcher_handoff
from tools.qwen_lifecycle.final_report import render

def load(p):return json.loads(p.read_text())
def put(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for n in ['final14-mac-base','final14-mac-selected','final14-mac-base-launch-interrupted']:shutil.copytree(R/'runs'/n,E/'runs'/n,dirs_exist_ok=True)
for path in P.glob('*.json'):shutil.copy2(path,E/path.name)
external=E/'external-inputs';external.mkdir(exist_ok=True)
for name in ['board-schema-check.json','source-manifest.json','persona.json','tools.json','registry_validate.py','selected9-routing-protocol.json']:
 shutil.copy2(R/'inputs'/name,external/name)
shutil.copytree(R/'inputs/ros-robot',external/'ros-robot',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
data=E/'data';data.mkdir(exist_ok=True)
if not (data/'holdout-original.jsonl').exists():shutil.copy2(R/'inputs/selected9-data-v1/holdout.jsonl',data/'holdout-original.jsonl')
if not (data/'supplemental-multicall.json').exists():shutil.copy2(W/'studies/voice-interaction/research/2026-10-22-mac-qwen-plan/final-multicall-challenge.json',data/'supplemental-multicall.json')
assert sha(data/'holdout-original.jsonl')==load(E/'cohort-audit.json')['holdout_sha256'];assert sha(data/'supplemental-multicall.json')==load(E/'cohort-audit.json')['challenge_sha256']
registry_hashes=load(E/'board-after.json')['registry_snapshot_sha256']
assert registry_hashes['registry_validate.py']==sha(external/'registry_validate.py')
for record in load(external/'source-manifest.json')['files']:assert registry_hashes[record['path']]==sha(external/record['path'])==record['sha256'],record['path']
assert load(external/'board-schema-check.json')['tools']==load(E/'final-suite.json')['tools']
for path in P.glob('*.py'):shutil.copy2(path,E/'source'/path.name)
for path in (W/'tools/qwen_lifecycle').glob('*.py'):shutil.copy2(path,E/'source'/('current-'+path.name))
shutil.copy2(W/'tools/qwen_lifecycle/report.css',E/'source/current-report.css')
wrapper=pathlib.Path('/Users/syz/.codex/skills/edge-model-benchmark/scripts/run_benchmark.py');spec=importlib.util.spec_from_file_location('benchmark_handoff',wrapper);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
proof=[];results=[]
for device in ['mac','board']:
 for model in ['base','selected']:
  name='final14-'+device+'-'+model;d=E/'runs'/name;raw=d/'benchmark/results.json';result=load(raw);assert len(result['cases'])==132
  assert result.get('status') in ['completed','partial']
  request=load(d/'launcher-request.json');mod.check_result(result,request)
  assert result['suite_sha256']==sha(raw.parent/'suite.json')==load(E/'cohort-audit.json')['suite_sha256']
  assert result['request_sha256']==sha(raw.parent/'request.json')
  assert result['artifacts']['files'][0]['sha256']==request['candidate']['artifact_sha256']
  assert load(d/'runtime.json')['binary_sha256']==sha(pathlib.Path(request['server']['binary'])) if device=='mac' else load(d/'runtime.json')['binary_sha256']=='0cd701240687d518d7c67905d0c470f7cd4bf7fc89bffe6581e993a48cd88550'
  frozen=load(E/'launch-freeze.json')['requests'][name+'-request.json'];assert sha(d/'launcher-request.json')==frozen,(name,'launcher changed')
  for ref in result['evidence']:
   rp=raw.parent/ref['path'];assert rp.is_file() and sha(rp)==ref['sha256'],str(rp)
  if device=='mac':
   handoff=launcher_handoff(result,raw);handoff['derived_view']={'schema':'edge-ai/derived-handoff-v1','original_launcher_result_sha256':sha(d/'results.json'),'original_benchmark_result_sha256':sha(raw),'scope':'read-only reference rebase; not a new measurement','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()};put(d/'derived-handoff.json',handoff);mod.check_result(handoff,request)
   for ref in handoff['evidence']:assert sha(d/ref['path'])==ref['sha256']
  proof.append({'run_id':name,'cases':132,'canonical_result':str(raw.relative_to(E)),'sha256':sha(raw),'launcher_request_sha256':sha(d/'launcher-request.json'),'frozen_request_match':True,'evidence_references_verified':len(result['evidence']),'original_launcher_result_sha256':sha(d/'results.json'),'owned_process_exit':load(d/'owned-process-exit.json'),'measurement_source_hashes':{f:sha(d/'source'/f) for f in ['benchmark.py','protocol.py','runners.py','measure.py',device+'_run.py']}});results.append(result)
for source_name in ['benchmark.py','protocol.py','runners.py','measure.py']:
 assert len({p['measurement_source_hashes'][source_name] for p in proof})==1,source_name
for device in ['mac','board']:
 a=load(E/('final14-'+device+'-base-request.json'));b=load(E/('final14-'+device+'-selected-request.json'))
 for key in ['server','generation','runner','registry_validator','suite','sampling_interval_seconds']:assert a[key]==b[key],(device,key)
put(E/'handoff-static-proof.json',{'registry_source_match':{'source_commit':load(external/'source-manifest.json')['source_commit'],'snapshot_files_verified':len(load(external/'source-manifest.json')['files']),'validator_sha256':registry_hashes['registry_validate.py'],'selected_schemas_equal_actual_board_export':True},'source_skill_commit':'9982debfcc8f02ee9a20894b0a656c9e761d693a','dispatcher_actual_sha256':sha(wrapper),'schema_checks':'current installed check_result; structural checks, not authenticity proof','runs':proof})
source_ids={}
for skill,scripts in {'edge-model-benchmark':['run_benchmark.py'],'edge-model-prepare':['readiness.py'],'edge-model-selection':['render_benchmark_report.py']}.items():
 for name in scripts:
  p=pathlib.Path('/Users/syz/.codex/skills')/skill/'scripts'/name;dest=E/'source/skills'/skill/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest);source_ids[str(p)]={'sha256':sha(p),'snapshot':str(dest.relative_to(E))}
put(E/'source-identities.json',{'source_commit':'9982debfcc8f02ee9a20894b0a656c9e761d693a','measurement_repository_base':'dea19ef','measurement_protocol_base':'809d32d','view_renderer_base':'802d872','source_files':source_ids,'measurement_snapshots':'runs/*/source/; current-*.py is later maintained view code, not substituted measurement bytes'})
print('Copied and checked',len(results),'canonical runs')
