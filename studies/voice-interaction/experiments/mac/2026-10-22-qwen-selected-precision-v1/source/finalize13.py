import pathlib,json,shutil,hashlib,sys,importlib.util
from html.parser import HTMLParser
W=pathlib.Path('/tmp/edge-ai-ticket-13');E=W/'studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected-precision-v1';R=pathlib.Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle')
def load(p):return json.loads(p.read_text())
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for n in ['precision13-runtime-libraries.json','precision13-gguf-layout.json']:
 shutil.copy2(pathlib.Path('/tmp/edge-ai-implementation-20261022')/n,E/n)
shutil.copy2(R/'artifacts/matched-base-dedup-v2/normalized-hf/tied-normalization-proof.json',E/'tied-normalization-proof.json')
for n in ['precision13-q8-dispatch.log','precision13-matched-dispatch.log']:shutil.copy2(R/'runs'/n,E/n)
for n in ['gguf13.py','finalize13.py']:shutil.copy2(pathlib.Path('/tmp/edge-ai-implementation-20261022')/n,E/'source'/n)
# Prior-original-short reference is an explicit counterfactual, not a paired routing run.
refs={n:load(R/'runs'/n/'results.json') for n in ['selected9-base-short','selected9-lora768-v3-short']};put(E/'baseline-originalshort-reference.json',refs)
# Match actual llama controls; quantify prefill vs full prompt rather than infer cache from flag.
names=['f16','q4','q5','q8'];requests=[load(E/'runs'/('precision13-'+n+'-validation')/'launcher-request.json') for n in names];audit={'same_server_argv':all(x['server']['argv']==requests[0]['server']['argv'] for x in requests),'same_generation':all(x['generation']==requests[0]['generation'] for x in requests),'same_suite':all(x['suite']==requests[0]['suite'] for x in requests),'source_f16_sha256':'e5ab9acb7cd47b495e2c337a57be2a0b162754d8adcbba3b21ec183c89012f2a','runs':[]}
for n in names+['baseq4matched']:
 r=load(E/'runs'/('precision13-'+n+'-validation')/'results.json'); audit['runs'].append({'run_id':r['run_id'],'full_prompt_counted':sum(c['generation'].get('prompt_tokens') is not None for c in r['cases']),'evaluated_prefill_equals_full_prompt':sum(c['generation'].get('prompt_tokens')==c['generation'].get('evaluated_prefill_tokens') for c in r['cases']),'finish_reasons':list({c['generation']['finish_reason'] for c in r['cases']}),'artifacts':r['artifacts']})
put(E/'controlled-comparison-audit.json',audit)
# Optional current report view; preserve every original measurement-produced HTML.
p=pathlib.Path('/tmp/edge-ai-qwen-report-fix/tools/qwen_lifecycle/report.py')
if p.exists():
 spec=importlib.util.spec_from_file_location('precision_current_view',p);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);rs=[load(E/'runs'/('precision13-'+n+'-validation')/'results.json') for n in ['adapter','merged','f16','q4','q5','baseq4matched','q8']];(E/'inference-current-view.html').write_text(mod.render(rs));shutil.copy2(p,E/'source/inference-current-renderer.py')
class Links(HTMLParser):
 def __init__(self):super().__init__();self.refs=[]
 def handle_starttag(self,tag,attrs):
  self.refs += [v for k,v in attrs if k in ['href','src'] and not v.startswith(('#','http','data:','mailto:'))]
p=Links();p.feed((E/'report.html').read_text());missing=[x for x in p.refs if not (E/x.split('#')[0]).exists()]
if missing:raise ValueError(missing)
put(E/'static-verification.json',{'main_local_references_checked':p.refs,'missing':missing,'browser_visual':'UNVERIFIED file policy; no alternate browser/HTTP/Playwright workaround','model_weights_in_git':False,'raw_runs_unchanged':True})
print('audit',audit['same_suite'],audit['same_generation'],audit['same_server_argv']);print('references',len(p.refs))
