import hashlib,json,shutil,sys,time
from pathlib import Path
ROOT=Path('/home/orangepi/code/edge-ai')
OLD=ROOT/'studies/voice-interaction/experiments/rk3566/2026-10-22-voice-screening-v2-r1'
EXP=ROOT/'studies/voice-interaction/experiments/rk3566/2026-10-22-asr-three-samples-v1'
EXP.mkdir(exist_ok=False)
SRC=EXP/'measurement-source';SRC.mkdir()
for n in ['benchmark.py','workers.py','voice_v2.py','evaluation.py','evaluation_metrics.py','evaluation_report.py','report.py']:
 shutil.copy2(OLD/'measurement-source'/n,SRC/n)
shutil.copy2(__file__,SRC/'execute.py')
sys.path.insert(0,str(SRC))
import benchmark
from report import windows,distribution

def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
# Preserve the actual fixture document, including the separate warmup fixture.
shutil.copy2(OLD/'asr-fixtures.json',EXP/'asr-fixtures.json')
fixtures=json.loads((EXP/'asr-fixtures.json').read_text())
for f in fixtures['fixtures']:assert sha(Path(f['path']))==f['sha256']
suite=json.loads((OLD/'asr-screening.json').read_text())
for c in suite['cases']:
 c['fixtures']=str(EXP/'asr-fixtures.json')
 c['fixture_ids']=['command','fleurs-1805-1','fleurs-1965-2']
save(EXP/'asr-screening.json',suite)
save(EXP/'manifest.json',benchmark.inventory(suite))
shutil.copy2(OLD/'assets-manifest.json',EXP/'assets-manifest.json')
shutil.copy2(OLD/'runtime-manifest.json',EXP/'runtime-manifest.json')
save(EXP/'protocol.json',dict(id='rk3566-voice-screen-v2',purpose='Three voiced inputs per precision/pacing; same frozen runtime and metrics; new independent experiment',rounds=1,fixture_ids=suite['cases'][0]['fixture_ids'],precision=['mixed_int8','fp32'],scenarios=['throughput','realtime'],per_case_timeout_s=90,total_budget_s=600,threads=2,product_thresholds='NOT_CONFIRMED',command_review=dict(source='user conversation 2026-10-22',status='user_confirmed_correct',transcript='机器人请让底盘上前移动二十厘米',note='user confirms previous INT8 and FP32 outputs; not retroactively inserted as independent reference for CER')))
outdir=EXP/'asr';outdir.mkdir()
manifest=json.loads((EXP/'manifest.json').read_text())
byid={f['id']:f for f in fixtures['fixtures']};cases=[];start=time.monotonic()
save(EXP/'environment-before.json',benchmark.observe(0))
for c in suite['cases']:
 assert time.monotonic()-start<510
 print('Starting',c['id'],flush=True)
 result=benchmark.run_case(c,outdir,suite['python'])
 assert result['status']=='ok',result['status']
 folder=outdir/c['id'];events=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines()];resources=[json.loads(l) for l in (folder/'resources.jsonl').read_text().splitlines()]
 phases,unfinished=windows(events,resources,manifest['cpu_count'],manifest['host_memory']['MemTotal'])
 samples=[]
 for e in events:
  if e.get('event')!='sample' or e.get('stage')!='inference':continue
  f=byid[e['fixture']];finals=[x for x in e['finals'] if x['text'].strip()];last=finals[-1] if finals else None
  samples.append(dict(id=f['id'],path=f['path'],input_sha256=f['sha256'],reference=f.get('reference'),transcript=e['final_text'],compute_rtf=e['compute_rtf'],first_partial_s=e['first_partial_seconds'] if c['realtime'] else None,endpoint_wait_from_energy_anchor_s=last['elapsed_s']-f['energy_end_s'] if c['realtime'] and last and last['kind']=='endpoint' else None,finals=e['finals'],completed=True,expected_silence=False))
 assert len(samples)==3
 cases.append(dict(id=c['id'],module='asr',scenario='realtime' if c['realtime'] else 'throughput',candidate=dict(precision='mixed_int8' if 'int8' in c['id'] else 'fp32',backend='CPU',threads=2),execution=dict(status=result['status'],returncode=result['returncode']),phases=phases,quality=json.loads((folder/'quality.json').read_text()),samples=samples,completed_samples=len(samples),expected_samples=3,aggregate_metrics={key:distribution([s[key] for s in samples]) for key in ['compute_rtf','first_partial_s','endpoint_wait_from_energy_anchor_s']},source=dict(result=str((folder/'result.json').relative_to(EXP)),sha256=sha(folder/'result.json'))))
 print('Completed',c['id'],flush=True)
save(EXP/'results.json',dict(schema_version='asr-three-samples/1',rounds=1,cases=cases,host_memory_kib=manifest['host_memory']['MemTotal']))
save(EXP/'environment-after.json',benchmark.observe(0))
print('Finished all three-input ASR comparisons',flush=True)
