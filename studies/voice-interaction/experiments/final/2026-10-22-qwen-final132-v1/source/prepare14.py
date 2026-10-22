"""Read-only readiness from actual pre-final development smokes."""
import hashlib,json,pathlib,subprocess,sys
E=pathlib.Path('/tmp/edge-ai-ticket-14/studies/voice-interaction/experiments/final/2026-10-22-qwen-final132-v1');D=E/'preparation';D.mkdir(exist_ok=True)
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
request={'schema':'edge-model-prepare/request-v1','device':{'name':'Orange Pi 3B RK3566','memory_bytes':4017020*1024},'requirements':{'scope':'selected and matchedbase Q4 dev smoke; minimal inference only, not final quality'},'candidates':[]};evidence=[];checks=[]
for model in ['base','selected']:
 name='final14-board-'+model;run=E/'runs'/(name+'-dev-smoke');r=json.loads((run/'results.json').read_text());assert r['summary']['samples']==r['summary']['native_calls']==r['summary']['schema_valid']==r['summary']['registry_valid']==1
 request['candidates'].append({'id':model,'name':name,'decision':'prepare','model':r['candidate']['model'],'artifact':r['candidate']['model_path'],'runtime':r['candidate']['actual_runtime'],'backend':'ARM CPU','precision':'Q4_K_M'})
 ids={}
 for kind,path in [('assets',run/'assets-manifest.json'),('runtime',run/'runtime.json'),('smoke',run/'results.json'),('benchmark_config',E/(name+'-request.json'))]:
  ident=model+'-'+kind;ids[kind]=ident;evidence.append({'id':ident,'kind':kind,'location':'../'+str(path.relative_to(E)),'sha256':sha(path),'description':'Actual pre-final development '+kind+'; exact finalconfig frozen separately'})
 checks.append({'id':model,'acquisition':{'model':'reuse','runtime':'reuse','reason':'SHAverified transferred matchedQ4; reused pinned CPU e3797b1 build after actual binary/library check'},'checks':{gate:{'status':'PASS','reason':'Inspected actual '+gate+' evidence; no production acceptance','evidence':[ids['benchmark_config' if gate=='benchmark' else gate]]} for gate in ['assets','runtime','smoke','benchmark']},'benchmark_configs':[ids['benchmark_config']],'next_action':'Run complete frozen132; never tune from final outputs.'})
put(D/'request.json',request);put(D/'checks.json',{'schema':'edge-model-prepare/checks-v1','request_sha256':sha(D/'request.json'),'evidence':evidence,'candidates':checks})
subprocess.run([sys.executable,'/Users/syz/.codex/skills/edge-model-prepare/scripts/readiness.py','report',str(D/'request.json'),str(D/'checks.json'),str(D/'output')],check=True)
