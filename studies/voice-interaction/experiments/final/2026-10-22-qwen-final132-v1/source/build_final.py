"""Run only after development smokes pass; preserve all final cohorts."""
import copy,hashlib,json,pathlib,datetime
R=pathlib.Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle'); W=pathlib.Path('/tmp/edge-ai-ticket-14'); P=R/'ticket14'; B='/home/orangepi/.local/share/edge-ai/qwen-ticket14'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
h=R/'inputs/selected9-data-v1/holdout.jsonl'; m=W/'studies/voice-interaction/research/2026-10-22-mac-qwen-plan/final-multicall-challenge.json'
assert sha(h)=='12ecc86b2bde791728312d8660ea66af26fd8e51477803bb52f0d7cb760de3a5';assert sha(m)=='22f20895471afba0887f641acf1229e9b87dfa371540818cc9bf66171d59e7eb'
rows=[json.loads(s) for s in h.read_text().splitlines()]; multi=json.loads(m.read_text())['samples']; suite=json.loads((R/'inputs/selected9-routing-only-suite.json').read_text());samples=[{'id':r['id'],'source_group':r['source_group'],'user':r['messages'][1]['content'],'expected':r['expected'],'cohort':'original-holdout'} for r in rows]+[dict(s,cohort='supplemental-multicall') for s in multi]
seen=set();groups=set()
for split in ['train','valid']:
 for r in map(json.loads,(R/('inputs/selected9-data-v3/'+split+'.jsonl')).read_text().splitlines()):seen.add(r['messages'][1]['content']);groups.add(r['source_group'])
assert not seen.intersection(s['user'] for s in samples);assert not groups.intersection(s['source_group'] for s in samples);assert len(samples)==132
suite.update(id='qwen-selected9-final132-v1',split='final',samples=samples);dump(P/'final-suite.json',suite)
audit={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'holdout_sha256':sha(h),'challenge_sha256':sha(m),'suite_sha256':sha(P/'final-suite.json'),'no_exact_user_overlap_train_valid':True,'no_source_group_overlap_train_valid':True,'counts':{'original':120,'supplement':12,'tool_requests':84,'expected_calls':100,'persona':36,'chat':12},'order':'original120 frozen order followed by supplemental12 frozen order'};dump(P/'cohort-audit.json',audit)
for device in ['mac','board']:
 for model in ['base','selected']:
  x=json.loads((R/'inputs/precision13-q4-validation-request.json').read_text()) if device=='mac' else json.loads((P/'dev-board-request.json').read_text());x['suite']=suite;x['run_id']='final14-'+device+'-'+model;x['stage']='independent final132; no selection or retuning';x['candidate']['parameter_count_stored']=596049920
  path=R/'artifacts/matched-base-dedup-v2/qwen3-base-q4_k_m.gguf' if model=='base' else R/'artifacts/selected9-768-v3/qwen3-selected9-768-v3-q4_k_m.gguf'
  expected='613697c3c0970385bc9e34a926fa30f39b37ae4471ca397a15666cebbff1d7ab' if model=='base' else '6f173f8a0c51b56c558ed47559a57a78b5c036391b63f9b8ed0731d54cc4b2f5';assert sha(path)==expected
  x['candidate'].update(model_path=str(path) if device=='mac' else B+'/artifacts/'+path.name,artifact_sha256=expected,device='Mac M5 / Metal' if device=='mac' else 'Orange Pi 3B RK3566 / ARM CPU',lineage='official same revision -> tiedweight dedup -> F16 -> Q4_K_M' if model=='base' else 'selected v3 adapter -> merged -> F16 -> Q4_K_M')
  if device=='mac':x['server']['port']=18134
  dump(P/(x['run_id']+'-request.json'),x)
dump(P/'launch-freeze.json',{'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'frozen before first final generation','selection_plan_sha256':sha(W/'studies/voice-interaction/research/2026-10-22-mac-qwen-plan/final-evaluation-plan.json'),'requests':{p.name:sha(p) for p in sorted(P.glob('final14-*-request.json'))},'suite':audit,'source_git':'dea19ef','skill_dispatcher_sha256':sha(pathlib.Path('/Users/syz/.codex/skills/edge-model-benchmark/scripts/run_benchmark.py'))})
