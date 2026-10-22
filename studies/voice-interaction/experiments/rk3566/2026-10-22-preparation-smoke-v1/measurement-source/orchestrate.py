import json,sys,shutil,hashlib,datetime,platform
from pathlib import Path
root=Path('/home/orangepi/code/edge-ai');prep=root/'studies/voice-interaction/research/2026-10-22-runtime-preparation';exp=root/'studies/voice-interaction/experiments/rk3566/2026-10-22-preparation-smoke-v1'
sys.path.insert(0,str(root/'tools/edge_benchmark'))
import benchmark
cache=Path('/home/orangepi/.cache/edge-voice-v2/runs/2026-10-22-preparation-smoke-v1');cache.mkdir(parents=True,exist_ok=False)
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
for name in ['assets-manifest.json','runtime-manifest.json','asr-fixtures.json']:
 shutil.copy2(prep/name,exp/name)
for name in ['benchmark.py','workers.py','voice_v2.py','voice_preflight.py','evaluation_metrics.py']:
 shutil.copy2(root/'tools/edge_benchmark'/name,exp/'measurement-source'/name)
source=exp/'measurement-source/smoke.py';shutil.copy2(source,cache/'smoke.py')
fixtures=json.loads((prep/'asr-fixtures.json').read_text())['fixtures'];f=next(x for x in fixtures if x['id']=='fleurs-1805-1')
plan=[]
for module,candidate in [('asr','asr-zh14m-int8'),('llm','llm-qwen25-q4'),('tts','tts-melo-fp32')]:
 c=json.loads((prep/(module+'-screening.json')).read_text())['cases'][0]
 c.update(id=module+'-smoke',kind='command',module=module,candidate=candidate,timeout=180)
 c['input']=dict(id=f['id'],path=f['path'],sha256=f['sha256'],reference=f['reference']) if module=='asr' else dict(text='请只回复：你好。' if module=='llm' else '你好，我是机器人。')
 cfg=cache/(module+'-input-config.json');save(cfg,c)
 c['command']=[json.loads((prep/'asr-screening.json').read_text())['python'],str(cache/'smoke.py'),str(cfg),'{output}']
 plan.append(c)
save(exp/'plan.json',dict(protocol='edge-model-prepare-smoke/v1',scope='one actual inference per baseline; non-realtime ASR; no warmup/repeats; no playback/ROS',per_module_process_budget_seconds=180,total_budget_seconds=540,min_memavailable_mib=600,cases=plan))
manifest=benchmark.inventory(dict(cases=plan,extra_assets=[str(cache/'smoke.py'),str(exp/'plan.json'),str(prep/'assets-manifest.json'),str(prep/'runtime-manifest.json'),f['path']],python=json.loads((prep/'asr-screening.json').read_text())['python']))
manifest.update(input_source='new minimal checks only; previous local benchmark results excluded',external_output=str(cache),measurement_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
save(exp/'manifest.json',manifest)
for c in plan:
 result=benchmark.run_case(c,cache,json.loads((prep/'asr-screening.json').read_text())['python'])
 target=exp/c['id'];target.mkdir()
 for file in (cache/c['id']).iterdir():
  if file.is_file() and file.suffix not in ['.wav','.pcm']:
   shutil.copy2(file,target/file.name)
 save(target/'external-media.json',dict(files=[dict(path=str(file),sha256=hashlib.sha256(file.read_bytes()).hexdigest(),bytes=file.stat().st_size) for file in (cache/c['id']).iterdir() if file.suffix in ['.wav','.pcm']]))
print('Smoke outputs retained:',exp,flush=True)
