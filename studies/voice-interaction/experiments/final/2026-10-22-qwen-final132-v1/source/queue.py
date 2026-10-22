"""Serialize each device's frozen pair; log all exits, never tune from output."""
import datetime,json,pathlib,subprocess,sys
DEVICE=sys.argv[1]
if DEVICE=='mac':
 R=pathlib.Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');P=R/'ticket14';W='/tmp/edge-ai-ticket-14';py=str(R/'venv/bin/python');wrap='/Users/syz/.codex/skills/edge-model-benchmark/scripts/run_benchmark.py';out=R/'runs';module='tools.qwen_lifecycle.mac_run'
else:
 R=pathlib.Path('/home/orangepi/.local/share/edge-ai/qwen-ticket14');P=R/'inputs';W=str(R/'source');py='/home/orangepi/.local/share/edge-ai/qwen-ticket12/venv/bin/python';wrap=str(R/'edge-model-benchmark/scripts/run_benchmark.py');out=R/'runs';module='tools.qwen_lifecycle.board_run'
for model in ['base','selected']:
 name='final14-'+DEVICE+'-'+model;args=[py,wrap,'--request',str(P/(name+'-request.json')),'--output',str(out/name),'--cwd',W,'--command',py,'-m',module]
 print(json.dumps({'start':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':args}),flush=True);c=subprocess.run(args,cwd=W);print(json.dumps({'run':name,'exit':c.returncode,'end':datetime.datetime.now(datetime.timezone.utc).isoformat()}),flush=True)
 if c.returncode:sys.exit(c.returncode)
