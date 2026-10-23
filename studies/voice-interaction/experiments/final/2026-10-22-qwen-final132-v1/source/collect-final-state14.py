"""Read-only post-run host/owned-process proof; never stops processes."""
import json,pathlib,subprocess,sys
import psutil
E=pathlib.Path('/tmp/edge-ai-ticket-14/studies/voice-interaction/experiments/final/2026-10-22-qwen-final132-v1')
remote='''import datetime,hashlib,json,pathlib,platform,subprocess,sys
import psutil
owned=[]
for p in psutil.process_iter(['pid','name','cmdline']):
 try:
  a=p.info.get('cmdline') or []
  if any('/qwen-ticket14/' in x for x in a) and (p.info['name']=='llama-server' or any('queue.py' in x for x in a)):
   owned.append(p.info)
 except (psutil.NoSuchProcess,psutil.AccessDenied):pass
root=pathlib.Path('/home/orangepi/.local/share/edge-ai/qwen-ticket14')
git={}
for key,args in [('head',['rev-parse','HEAD']),('status',['status','--porcelain'])]:
 c=subprocess.run(['git','-C','/home/orangepi/code/ros-robot']+args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True);git[key]={'exit_code':c.returncode,'stdout':c.stdout,'stderr':c.stderr}
inputs=pathlib.Path('/home/orangepi/.local/share/edge-ai/qwen-ticket12/inputs')
source_files=[inputs/'registry_validate.py']+[p for p in (inputs/'ros-robot').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
source_hashes={str(p.relative_to(inputs)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
thermal={}
for p in pathlib.Path('/sys/class/thermal').glob('thermal_zone*/temp'):
 try:thermal[p.parent.name]=float(p.read_text())/1000
 except (OSError,ValueError):pass
print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'python':sys.version,'platform':platform.platform(),'memory':psutil.virtual_memory()._asdict(),'swap':psutil.swap_memory()._asdict(),'disk':psutil.disk_usage(str(root))._asdict(),'owned_model_or_queue_processes':owned,'production_git_read_only':git,'registry_snapshot_sha256':source_hashes,'thermal_zone_celsius':thermal,'model_files_preserved':[{'name':p.name,'bytes':p.stat().st_size} for p in sorted((root/'artifacts').glob('*.gguf'))],'scope':'post-run read-only state, no process termination or production write'}))
'''
argv=['ssh','orangepi-ts','/home/orangepi/.local/share/edge-ai/qwen-ticket12/venv/bin/python','-'];c=subprocess.run(argv,input=remote,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE);(E/'board-after.json').write_text(c.stdout);(E/'board-after-collection.json').write_text(json.dumps({'argv':argv,'exit_code':c.returncode,'stderr':c.stderr,'script':'source/collect-final-state14.py','scope':'remote source supplied on stdin; read-only state collection'},indent=2)+'\n');c.check_returncode();state=json.loads(c.stdout);assert not state['owned_model_or_queue_processes'],state['owned_model_or_queue_processes']
owned=[]
for p in psutil.process_iter(['pid','name','cmdline']):
 try:
  if p.info['name']=='llama-server' and any('qwen-lifecycle/artifacts/' in a for a in p.info.get('cmdline') or []):owned.append(p.info)
 except (psutil.NoSuchProcess,psutil.AccessDenied):pass
(E/'mac-after.json').write_text(json.dumps({'owned_model_processes':owned,'memory':psutil.virtual_memory()._asdict(),'swap':psutil.swap_memory()._asdict(),'scope':'post-run read-only; no claim of GPU utilization measurement'},indent=2)+'\n');assert not owned,owned
print('post-run owned model/queue processes absent; assets preserved')
