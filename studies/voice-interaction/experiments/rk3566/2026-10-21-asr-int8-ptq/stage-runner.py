import sys,json
from pathlib import Path
sys.path.insert(0,'/home/orangepi/code/edge-ai/tools/edge_benchmark')
from benchmark import run_case
base=Path(__file__).parent
stage=sys.argv[1]
command=json.loads((base/(stage+'-command.json')).read_text())
config=dict(id=stage,kind='command',command=command['command'],env=command.get('env',{}),timeout=command.get('timeout',480),threads=1,max_as_mib=4096)
root=base/'stages';root.mkdir(exist_ok=True)
result=run_case(config,root,sys.executable)
print(json.dumps({k:v for k,v in result.items() if k not in ('events','config','command')}))
sys.exit(0 if result['status']=='ok' else 1)
