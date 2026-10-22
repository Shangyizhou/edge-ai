import array,hashlib,html,json,math,subprocess,sys,wave
from pathlib import Path
root=Path('/home/orangepi/code/edge-ai');exp=root/'studies/voice-interaction/experiments/rk3566/2026-10-22-voice-screening-v2-r1';cache=Path('/home/orangepi/.cache/edge-voice-v2/runs/2026-10-22-voice-screening-v2-r1')
media=json.loads((exp/'tts/melo-fp32/external-media.json').read_text())['files'];tasks=json.loads((exp/'text-fixtures.json').read_text())['tts'];checks=[];audiohtml=[]
for i,task in enumerate(tasks):
 item=next(x for x in media if Path(x['path']).name==str(i)+'.wav');p=Path(item['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
 with wave.open(str(p)) as f:
  rate=f.getframerate();channels=f.getnchannels();width=f.getsampwidth();n=f.getnframes();raw=f.readframes(n)
 assert channels==1 and width==2 and n>0
 pcm=array.array('h');pcm.frombytes(raw)
 if sys.byteorder!='little':pcm.byteswap()
 assert any(pcm)
 checks.append(dict(id=task['id'],path=str(p),sha256=item['sha256'],passed=True,sample_rate=rate,channels=channels,sample_width_bytes=width,frames=n,audio_duration_s=n/rate,nonzero_samples=sum(x!=0 for x in pcm),peak_abs_pcm16=max(abs(x) for x in pcm),scope='PCM16 header/frame/nonzero integrity only; no pronunciation or naturalness judgement'))
 audiohtml.append('<section><h2>'+html.escape(task['id'])+'</h2><p>'+html.escape(task['text'])+'</p><audio controls preload="none" src="tts/melo-fp32/'+str(i)+'.wav"></audio></section>')
(exp/'tts-integrity.json').write_text(json.dumps(dict(samples=checks,listening_review='NOT_EVALUATED'),ensure_ascii=False,indent=2)+'\n')
(cache/'listening.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>TTS固定文本试听</title><style>body{font:17px/1.7 system-ui;max-width:850px;margin:35px auto;padding:20px}section{padding:18px;border:1px solid #ccd;margin:16px 0}audio{width:100%}</style><h1>Melo FP32 初筛四条文本</h1><p>此页用于本机人工试听。PCM有效不代表数字、日期、否定句发音正确；主观质量尚未评审。</p>'+''.join(audiohtml))
subprocess.run(['python3',str(exp/'measurement-source/report.py')],check=True)
d=json.loads((exp/'results.json').read_text())
for c in d['cases']:
 print(c['id'],c['execution'],c['completed_samples'],c['aggregate_metrics'])
 print('ACTIVE', {k:v for k,v in c['phases'].get('inference',{}).items() if k!='individual_windows'})
