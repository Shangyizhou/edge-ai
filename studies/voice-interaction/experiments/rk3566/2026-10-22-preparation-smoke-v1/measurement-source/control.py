import json,sys,shutil,datetime
from pathlib import Path
root=Path('/home/orangepi/code/edge-ai');exp=root/'studies/voice-interaction/experiments/rk3566/2026-10-22-preparation-smoke-v1';cache=Path('/home/orangepi/.cache/edge-voice-v2/runs/2026-10-22-preparation-smoke-v1')
sys.path.insert(0,str(root/'tools/edge_benchmark'))
import benchmark
c=json.loads((cache/'asr-input-config.json').read_text());c.update(id='asr-fp32-smoke',kind='command',candidate='asr-zh14m-fp32-control')
c['encoder']=c['encoder'].replace('.int8.onnx','.onnx');c['joiner']=c['joiner'].replace('.int8.onnx','.onnx')
cfg=cache/'asr-fp32-input-config.json';cfg.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n')
c['command']=[ '/home/orangepi/venvs/sherpa-onnx/bin/python',str(cache/'smoke.py'),str(cfg),'{output}']
(exp/'control-plan.json').write_text(json.dumps(dict(reason='Existing ASR benchmark configuration includes FP32 control. Confirm minimal inference for that deployed artifact as well before handoff; no performance comparison.',process_budget_seconds=180,case=c),ensure_ascii=False,indent=2)+'\n')
result=benchmark.run_case(c,cache,'/home/orangepi/venvs/sherpa-onnx/bin/python')
target=exp/c['id'];target.mkdir()
for f in (cache/c['id']).iterdir():
 if f.is_file() and f.suffix not in ['.wav','.pcm']:shutil.copy2(f,target/f.name)
