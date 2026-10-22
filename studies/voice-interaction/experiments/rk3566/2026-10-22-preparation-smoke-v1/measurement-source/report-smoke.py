import hashlib,json,shutil,subprocess,wave
from pathlib import Path
root=Path('/home/orangepi/code/edge-ai');study=root/'studies/voice-interaction';exp=study/'experiments/rk3566/2026-10-22-preparation-smoke-v1';old=study/'research/2026-10-22-readiness-contract';cache=Path('/home/orangepi/.cache/edge-voice-v2/runs/2026-10-22-preparation-smoke-v1')
python='/home/orangepi/venvs/sherpa-onnx/bin/python';skill=Path('/home/orangepi/.codex/skills/edge-model-prepare')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
shutil.copy2(old/'request.json',exp/'request.json');shutil.copytree(old/'evidence',exp/'evidence')
checks=json.loads((old/'checks.json').read_text());evidence=checks['evidence']
evidence.append(dict(id='current-preflight',kind='benchmark',location='preflight.json',sha256=sha(exp/'preflight.json'),description='本轮重新核对112个文件及冻结配置，实际检查无错误；不替代推理证据'))
for name in ['asr','asr-fp32','llm','tts']:
 case=name+'-smoke';folder=exp/case;result=json.loads((folder/'result.json').read_text());v=json.loads((folder/'validation.json').read_text())
 assert result['status']=='ok' and result['returncode']==0 and v['passed'] is True and v['inference_executed'] is True
 assert sha(folder/'input.json')==v['input_sha256']
 shutil.copy2(cache/(name+'-input-config.json'),folder/'source-config.json')
 if name=='asr' or name=='asr-fp32':
  inp=json.loads((folder/'input.json').read_text());assert sha(inp['path'])==inp['sha256']
  assert json.loads((folder/'asr-output.json').read_text())['transcript'].strip()
 elif name=='llm':
  response=json.loads((folder/'response.json').read_text());assert response['content'].strip()=='你好。'
 else:
  media=json.loads((folder/'external-media.json').read_text())['files']
  for m in media:assert sha(m['path'])==m['sha256']
  wav=cache/case/'generated.wav'
  with wave.open(str(wav)) as f:
   assert f.getnframes()==v['samples'] and f.getframerate()==v['sample_rate'] and f.getsampwidth()==2
 record=dict(candidate=v['candidate'],scope='on-device minimal actual inference; not performance/quality acceptance',input=v['input_sha256'],invocation=result['command'],exit_code=result['returncode'],validation=v,raw_files=[dict(path=str(f.relative_to(exp)),sha256=sha(f)) for f in sorted(folder.iterdir()) if f.is_file()],runtime_identity=dict(manifest='runtime-manifest.json',sha256=sha(exp/'runtime-manifest.json')),effective_input_limits=dict(repetitions=1,warmups=0,llm_output_cap_tokens=16 if name=='llm' else None,asr_realtime_pacing=False if name.startswith('asr') else None))
 save(folder/'inference-record.json',record)
 evidence.append(dict(id='smoke-'+name,kind='smoke',location=case+'/inference-record.json',sha256=sha(folder/'inference-record.json'),description='本轮实际推理：输入、命令、退出码、检查结果与原始输出哈希；仅功能最小样例'))
for c in checks['candidates']:
 module='asr' if c['id'].startswith('asr') else 'llm' if c['id'].startswith('llm') else 'tts'
 refs=['smoke-'+module]+(['smoke-asr-fp32'] if module=='asr' else [])
 c['checks']['smoke']=dict(status='PASS',reason={'asr':'INT8主候选及同包FP32对照均真实解码同一固定非静音样本，返回中文文本；未验收CER或流式端点。','llm':'官方Qwen2.5 Q4_K_M真实生成“你好。”，请求上限16 token、greedy；未验收综合指令质量。','tts':'Melo按固定中文文本生成68842个44.1kHz有限非零样本，PCM16 WAV可读；未做听感验收。'}[module],evidence=refs)
 for gate in ['assets','runtime','benchmark']:
  c['checks'][gate]['evidence'].append('current-preflight')
 c['checks']['benchmark']['reason']='本轮112文件哈希检查无错，现有工具源与实际运行库身份未改变；ASR配置的INT8/FP32两种制品均完成最小推理，冻结配置可交接。性能门槛仍待正式初筛。'
 c['next_action']='按已冻结配置执行一轮单模块小集初筛，保留逐条质量/等待/资源，再决定三轮复测；当前不启动ROS/YOLO共跑。'
checks['request_sha256']=sha(exp/'request.json');save(exp/'checks.json',checks)
for e in evidence:assert sha(exp/e['location'])==e['sha256'],e['id']
subprocess.run(['python3',str(skill/'scripts/readiness.py'),'report',str(exp/'request.json'),str(exp/'checks.json'),str(exp/'readiness')],check=True)
result=json.loads((exp/'readiness/readiness.json').read_text());assert result['status']=='READY_FOR_BENCHMARK' and len(result['benchmark_handoff']['candidates'])==3
save(exp/'artifact-hashes.json',[dict(path=str(f.relative_to(exp)),sha256=sha(f)) for f in sorted(exp.rglob('*')) if f.is_file()])
print(result['status'],[r['status'] for r in result['candidates']])
