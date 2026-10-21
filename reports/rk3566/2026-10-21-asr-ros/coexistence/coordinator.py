import json,os,pathlib,subprocess,time,signal,hashlib
root=pathlib.Path('/home/orangepi/.cache/ros-robot-edge-benchmark/runs/asr-ros-yolo-01');root.mkdir()
gate=root/'start-gate';speech=root/'speech';vision=root/'vision';vision.mkdir()
c=json.loads(pathlib.Path('/home/orangepi/code/edge-ai/tools/edge_benchmark/asr-streaming.json').read_text())['cases'][1]['members'][0];c['gate_file']=str(gate)
(vision/'config.json').write_text(json.dumps(c,indent=2)+'\n')
args=['/usr/bin/python3','/home/orangepi/code/ros-robot/.scratch/asr-rknn-integration/validation/replay.py','/home/orangepi/.cache/ros-robot-edge-benchmark/build/asr-ros/asr_node','/home/orangepi/.cache/ros-robot-edge-benchmark/npu/historical/5ff8b9e4d971c082a808b229bf0e3060b1f2c926/sherpa-onnx-rk3566-streaming-zipformer-small-bilingual-zh-en-2023-02-16','/home/orangepi/.cache/ros-robot-edge-benchmark/streaming/fixtures',str(speech),'--continuous-only','--gate-file',str(gate)]
logs=[(root/'speech.log').open('w'),(root/'vision.log').open('w')]
sp=subprocess.Popen(args,env=dict(os.environ,ROS_DOMAIN_ID='179',ROS_LOCALHOST_ONLY='1'),stdout=logs[0],stderr=logs[0])
vp=subprocess.Popen(['/usr/bin/python3','/home/orangepi/code/edge-ai/tools/edge_benchmark/workers.py',str(vision/'config.json'),str(vision)],env=dict(os.environ,**c['env']),stdout=logs[1],stderr=logs[1])
try:
 deadline=time.monotonic()+25
 while not ((speech/'ready').exists() and (vision/'ready').exists()):
  assert sp.poll() is None and vp.poll() is None,'child exited before gate'
  assert time.monotonic()<deadline,'ready timeout'
  time.sleep(.02)
 gate.write_text('start');opened=time.monotonic()
 print('both ready; gate opened',flush=True)
 sr=sp.wait(timeout=55);vr=vp.wait(timeout=10);assert sr==vr==0,(sr,vr)
 (root/'coordination.json').write_text(json.dumps({'speech_command':args,'gate_open_monotonic':opened,'speech_returncode':sr,'vision_returncode':vr,'asr_probe_sha256':hashlib.sha256(pathlib.Path(args[1]).read_bytes()).hexdigest()},indent=2)+'\n')
 print(root,flush=True)
finally:
 for p in (sp,vp):
  if p.poll() is None:
   p.send_signal(signal.SIGINT)
   try:p.wait(timeout=6)
   except subprocess.TimeoutExpired:p.kill();p.wait()
 for log in logs:log.close()
