import json,pathlib,shutil,hashlib,subprocess,sys
W=pathlib.Path('/tmp/edge-ai-ticket-13');R=pathlib.Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');E=W/'studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected-precision-v1'
def load(p):return json.loads(pathlib.Path(p).read_text())
def put(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
E.mkdir(parents=True,exist_ok=True)
for d in R.joinpath('runs').glob('precision13-*'):
 if d.is_dir() and (d/'results.json').exists():shutil.copytree(d,E/'runs'/d.name,dirs_exist_ok=True)
shutil.copytree(R/'runs/selected9-768-v3-export-v1',E/'runs/selected9-768-v3-export-v1',dirs_exist_ok=True)
(E/'source').mkdir(exist_ok=True)
for f in ['run13.py','run13q8.py','start13.py','package13.py','review13.py','run13matched.py']:
 shutil.copy2(pathlib.Path('/tmp/edge-ai-implementation-20261022')/f,E/'source'/f)
for f in ['mac_run.py','precision_report.py','normalize_tied.py']:
 shutil.copy2(W/'tools/qwen_lifecycle'/f,E/'source'/f)
shutil.copy2(R/'runs/precision13-dispatch.log',E/'dispatch.log')
names=['adapter','merged','f16','q4','q5','baseq4matched','q8'];results=[load(E/'runs'/('precision13-'+n+'-validation')/'results.json') for n in names]
review=load(W/'studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected9-adaptation-v1/persona-review.json');review['cases']=[];review['created_utc']='2026-10-22T08:48:20.411206+00:00';review['method']='Assistant inspected every complete persona output in this experiment against frozen rubric; explicit case verdicts assigned separately; keyword score auxiliary only.'
# Contextual verdicts are supplied after reading real outputs, never inferred from keywords.
verdicts=load(pathlib.Path('/tmp/edge-ai-implementation-20261022/precision13-persona-verdicts.json'))
for r in results:
 for c in r['cases']:
  if c['kind']=='persona':
   v=verdicts[r['run_id']][c['id']];review['cases'].append(dict(run_id=r['run_id'],case_id=c['id'],input=c['user'],output=c['generation']['raw'],rubric=c['expected']['rubric'],passed=v['passed'],reason=v['reason'],auxiliary_keyword_pass=c['assessment'].get('persona_valid')))
put(E/'persona-review.json',review)
from tools.qwen_lifecycle.precision_report import render,paired
from tools.qwen_lifecycle.report import resources,median
paired(results)
summary=[]
for r in results:
 rev=[x for x in review['cases'] if x['run_id']==r['run_id']];summary.append(dict(run_id=r['run_id'],quality=r['summary'],contextual_persona_pass=sum(x['passed'] for x in rev),resources=resources(r['cases']),medians={k:median(r['cases'],k) for k in ['prefill_tokens_per_second','decode_tokens_per_second','ttft_seconds','wall_seconds','prompt_tokens']},artifacts=r['artifacts']))
put(E/'comparison-summary.json',summary)
put(E/'tool-failures.json',[dict(run_id=r['run_id'],case=c) for r in results for c in r['cases'] if c['kind']=='tool' and not c.get('assessment',{}).get('expected_behavior')])
put(E/'merge-regression.json',dict(scope='same MLX adapter and BF16 merged 60 inputs',same_raw_output=sum(a['generation']['raw']==b['generation']['raw'] for a,b in zip(results[0]['cases'],results[1]['cases'])),differences=[dict(id=a['id'],adapter=a['generation']['raw'],merged=b['generation']['raw']) for a,b in zip(results[0]['cases'],results[1]['cases']) if a['generation']['raw']!=b['generation']['raw']]))
decision=load('/tmp/edge-ai-implementation-20261022/precision13-decision.json');put(E/'selection.json',decision)
exports=[load(E/'runs'/n/'results.json') for n in ['selected9-768-v3-export-v1','precision13-export','precision13-q8-export','precision13-matched-export-v2']]
(E/'report.html').write_text(render(results,review,exports,decision))
# Actual prepare evidence handoff: each result and configuration are hashed references.
prep=E/'preparation';prep.mkdir(exist_ok=True);request={'schema':'edge-model-prepare/request-v1','device':{'name':'MacBook Air M5','memory_bytes':17179869184},'requirements':{'scope':'real minimum inference and frozen executable validation config; no product acceptance'},'candidates':[]};evidence=[];checks=[]
for name,r in zip(names,results):
 rid=r['run_id'];rel=pathlib.Path('runs')/rid;conf=E/rel/('launcher-request.json' if name not in ['adapter','merged'] else 'request.json');smoke=E/'runs'/('precision13-'+name+'-prepare')/'results.json' if name not in ['adapter','merged'] else E/rel/'cases/valid_000.json';asset=E/rel/'assets-manifest.json';runtime=E/rel/'runtime.json' if name not in ['adapter','merged'] else E/rel/'results.json'
 if not asset.exists():asset=E/rel/'benchmark/assets-manifest.json'
 candidate={'id':name,'name':rid,'decision':'prepare','model':r['candidate']['model'],'artifact':r['candidate']['model_path'],'runtime':r['candidate']['actual_runtime'],'backend':r['candidate']['backend'],'precision':r['candidate']['precision']};request['candidates'].append(candidate)
 ids={}
 for kind,path in [('assets',asset),('runtime',runtime),('smoke',smoke),('benchmark_config',conf)]:
  ident=name+'-'+kind;ids[kind]=ident;evidence.append(dict(id=ident,kind=kind,location='../'+str(path.relative_to(E)),sha256=sha(path),description='Actual '+kind+' evidence for '+rid))
 checks.append(dict(id=name,acquisition={'model':'reuse','runtime':'reuse','reason':'pinned official revision / selected lineage; existing verified Mac Metal build'},checks={gate:{'status':'PASS','reason':'inspected actual '+gate+' evidence; minimum functional scope only','evidence':[ids['benchmark_config' if gate=='benchmark' else gate]]} for gate in ['assets','runtime','smoke','benchmark']},benchmark_configs=[ids['benchmark_config']],next_action='Use validation evidence for selection; final sealed evaluation reserved #14.'))
put(prep/'request.json',request);put(prep/'checks.json',{'schema':'edge-model-prepare/checks-v1','request_sha256':sha(prep/'request.json'),'evidence':evidence,'candidates':checks})
subprocess.run([sys.executable,'/Users/syz/.codex/skills/edge-model-prepare/scripts/readiness.py','report',str(prep/'request.json'),str(prep/'checks.json'),str(prep/'output')],check=True)
shutil.copy2(prep/'output/report.html',prep/'report.html')
print(E)
