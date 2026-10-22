import hashlib,json,shutil,sys,subprocess
from pathlib import Path
ROOT=Path('/home/orangepi/code/ros-robot');EXP=Path('/home/orangepi/code/edge-ai/studies/voice-interaction/experiments/rk3566/2026-10-22-qwen-business-fit-v1')
sys.path.insert(0,str(ROOT/'ros2_ws/src/robot_agent'))
from robot_agent.actions.capabilities import create_default_actions
from robot_agent.actions.perception import PerceptionActions
from robot_agent.conversation.local_model import LocalModel
reg=create_default_actions().registry
reg.register_perception(PerceptionActions(None))  # Schema construction only; invoke is never called.
tools=reg.schemas()
save=lambda p,d:p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
save(EXP/'tools-full.json',tools)
names={'volume_set','play_music','enable_lidar','disable_lidar','enable_tracking','start_following'}
subset=[t for t in tools if t['name'] in names]
save(EXP/'tools-subset.json',subset)
cases=[dict(id='ordered-parameters',text='先把音量调到30，再播放夜曲。',expected=[dict(name='volume_set',arguments=dict(level=30)),dict(name='play_music',arguments=dict(song_name='夜曲'))]),dict(id='negation-scope',text='不要开启跟随，只开启雷达融合。',expected=[dict(name='enable_lidar',arguments={})]),dict(id='explanation-only',text='只解释关闭雷达融合会发生什么，不要执行。',expected=[])]
save(EXP/'cases.json',cases)
for scope,catalog in [('full',tools),('subset',subset)]:
 for c in cases:
  (EXP/(scope+'-'+c['id']+'.txt')).write_text(LocalModel(None)._prompt(c['text'],catalog))
manifest=[]
files=list((ROOT/'ros2_ws/src/robot_agent/robot_agent/actions').glob('*.py'))+[ROOT/'ros2_ws/src/robot_agent/robot_agent/results.py',ROOT/'ros2_ws/src/robot_agent/robot_agent/conversation/local_model.py',ROOT/'ros2_ws/src/robot_agent/robot_agent/conversation/online_system_prompt.txt',ROOT/'ros2_ws/src/robot_inference/include/robot_inference/reply_grammar.hpp',ROOT/'ros2_ws/src/robot_inference/src/llm_node.cpp',ROOT/'ros2_ws/src/robot_agent/config/offline.json']
for src in files:
 if not src.is_file():continue
 dst=EXP/'project-source'/src.relative_to(ROOT);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 manifest.append(dict(path=str(src),snapshot=str(dst.relative_to(EXP)),sha256=hashlib.sha256(src.read_bytes()).hexdigest()))
save(EXP/'source-manifest.json',dict(repository='200166shang/ros-robot',commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),files=manifest,tools_count=len(tools),subset_count=len(subset),scope='read-only schema and prompt extraction; no invoke, ROS node, cloud provider or robot action'))
print('Full tools:',len(tools),'subset:',len(subset));print('Full prompt chars:',len((EXP/'full-negation-scope.txt').read_text()),'subset:',len((EXP/'subset-negation-scope.txt').read_text()))
print('Tools:',','.join(t['name'] for t in tools))
