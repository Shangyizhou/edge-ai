from pathlib import Path
import json,hashlib,argparse
parser=argparse.ArgumentParser(description='Create a fresh synthetic workflow dataset; never overwrite a frozen version')
parser.add_argument('--assets',type=Path,required=True);parser.add_argument('--evidence',type=Path,required=True)
args=parser.parse_args()
r=Path(__file__).resolve().parents[2];a=args.assets.resolve();record=args.evidence.resolve()
if a.exists() or record.exists():parser.error('fresh asset and evidence directories required')
a.mkdir(parents=True,exist_ok=False);record.mkdir(parents=True,exist_ok=False)
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
# Snapshot old text evidence before any new execution. No weights/audio read.
roots=[r/'studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected9-adaptation-v1',r/'studies/voice-interaction/experiments/rk3566/2026-10-22-asr-three-samples-v1']
old={str(p):sha(p) for root in roots for p in root.rglob('*') if p.is_file()}
write(record/'historical-input-hashes.json',old)
tools=json.loads(Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle/inputs/tools.json').read_text())
write(a/'tools.json',tools)
system='你是机器人助手。设备操作使用提供的工具；角色与普通聊天用文字回答。'
actions=[('start_camera','恢复摄像头采集',{}),('stop_camera','暂停摄像头采集',{}),('enable_lidar','开启雷达融合',{}),('disable_lidar','关闭雷达融合',{}),('enable_tracking','启用目标跟随',{}),('disable_tracking','停用目标跟随',{}),('following_status','查询跟随状态',{}),('volume_set','把音量调到百分之三十',{'level':30}),('play_music','播放歌曲晚风',{'song_name':'晚风'})]
# Bind numeric/string property names to the actual schema, not guessed interfaces.
for n,t,args in actions:
 schema=next(x['function']['parameters'] for x in tools if x['function']['name']==n)
 if args and set(args)!=set(schema.get('properties',{})):
  print('SCHEMA PROPERTY MISMATCH',n,schema);raise SystemExit(2)
frames={'train':['练习面板现在申请：{x}。','请按这张操作卡办理：{x}。','我在做单项练习，本项需要{x}。','这一回合请处理{x}。'],'valid':['验证控制台请求如下：{x}。','请响应验证指令：{x}。'],'development':['现场测试单要求{x}，请生成对应调用。','下一张设备工单写着{x}，现在处理。'],'final':['新用户的设备申请是{x}，请接收这个请求。','交付演示环节需要{x}，请给出调用。']}
personas=[('请说你的名字。','我叫小沫。',['小沫']),('你的角色负责什么？','我是小沫，科研AI与机器人助手。',['小沫','科研']),('你由谁创造这个角色？','小沫是用户创造的角色，创建者真实姓名没有提供。',['用户']),('角色设定改变底层模型来源吗？','小沫是用户创造的角色，底层模型来自Qwen。',['用户','Qwen']),('你真实出生在哪里？','角色资料没有提供真实出生城市，我不能编造。',[]),('请简短介绍你的角色。','我是小沫，是用户创造的科研AI与机器人助手角色。',['小沫','用户'])]
questions={
 'train':['请说你的名字。','你的角色负责什么？','你由谁创造这个角色？','角色设定改变底层模型来源吗？','你真实出生在哪里？','请简短介绍你的角色。'],
 'valid':['给你的个人名片填一个名字。','资料里怎样描述你的工作定位？','你能提供角色创建人的真实姓名吗？','介绍角色时能把底座研发归给用户吗？','角色资料记载过出生地吗？','对新同学说明你是谁。'],
 'development':['如果叫你来帮忙，应该怎样称呼你？','你属于科研助手还是普通设备开关？','谁设定了小沫这个身份？','请区分你的人物设定与模型技术来源。','关于真实出生地点你掌握哪些信息？','首次见面，请自我介绍。','别人给你换名字之前，你叫什么？','你的科研机器人助手身份是什么？'],
 'final':['你会怎样向访客报上自己的称呼？','这个机器人助手的角色定位是怎样的？','角色创建者和底层模型开发者是一回事吗？','基础模型是否因为角色设定而换了来源？','没有资料的出生城市应当怎样回答？','请给第一次接触你的同事做介绍。','做姓名登记时你会报什么名字？','你能协助哪些类别的交流和任务？']}
chats={
 'train':['请给今天的学习留一句鼓励。','用一句话祝我调试顺利。','我们聊聊如何保持耐心。','我刚完成一个小任务。','请说一句简短的晚安。','送我一句关于坚持的话。'],
 'valid':['看书累了，给我一个休息建议。','今天我学会了一个新概念。'],
 'development':['周末可以做什么放松？','讲一句温和的问候。','我有点紧张，想听一句安慰。','陪我聊一句学习的乐趣。'],
 'final':['漫长的调试结束了，给我一句祝福。','聊聊怎样庆祝一点点进步。','我想安排一段安静的休息。','说一句适合早晨听的问候。']}
counts={'train':(36,18,6),'valid':(12,4,2),'development':(12,8,4),'final':(12,8,4)}
groups={}; outputs={}
for split,(nt,np,nc) in counts.items():
 rows=[]
 for i in range(nt):
  n,text,args=actions[i%len(actions)]; family=i//len(actions)
  group=f'{split}_action_frame{family}'; user=frames[split][family%len(frames[split])].format(x=text)
  if i>=9 and split!='train':
   if i==9:n,text,args='play_music','播放歌曲星光"现场"',{'song_name':'星光"现场"'};user=frames[split][1].format(x=text)
   elif i==10:n,text,args='volume_set','把音量调到百分之四十五',{'level':45};user=frames[split][1].format(x=text)
   else:n,text,args='start_camera','先恢复摄像头采集，再查询跟随状态',{};user=frames[split][1].format(x=text)
  calls=[{'name':n,'arguments':args}]
  if i==11 and split!='train':calls.append({'name':'following_status','arguments':{}})
  expected={'kind':'tool','calls':calls}; assistant={'role':'assistant','tool_calls':[{'type':'function','function':c} for c in calls]}
  rows.append((group,user,assistant,expected))
 for i in range(np):
  q,answer,contains=personas[i%len(personas)];family=i//len(personas)
  user=questions[split][i%len(questions[split])] if split!='train' else ['请回答这个角色问题：','我想核对角色资料：','只介绍自身身份：'][family]+q
  rows.append((f'{split}_persona_family{family}',user,{'role':'assistant','content':answer},{'kind':'persona','contains_all':contains,'rubric':'source-backed facts; automatic markers are diagnostic only'}))
 for i in range(nc):
  rows.append((f'{split}_chat_family',chats[split][i],{'role':'assistant','content':'祝你顺利，也记得适当休息。'},{'kind':'chat'}))
 data=[];samples=[]
 for i,(group,user,assistant,expected) in enumerate(rows):
  sid=f'{split}_{i:03d}';groups[group]=split
  data.append({'id':sid,'split':split,'source_group':group,'parent_group':group,'provenance':{'kind':'synthetic','method':'assistant-curated deterministic pilot; disjoint wording families, same known-tool intents','reviewer':'current assistant, schema checked; not human approved labels'},'label_status':'reviewed','tools':tools,'messages':[{'role':'system','content':system},{'role':'user','content':user},assistant]})
  samples.append({'id':sid,'source_group':group,'user':user,'expected':expected})
 folder=a/('heldout' if split=='final' else 'development-data');folder.mkdir(exist_ok=True)
 if split in ('train','valid'):
  path=folder/(split+'-source.jsonl');path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in data));outputs[split]=str(path)
 else:
  path=folder/(split+'-suite.json');write(path,{'schema':'edge-model-benchmark/suite-v1','id':'workflow-'+split,'split':split,'system':system,'tools':tools,'samples':samples});outputs[split]=str(path)
write(a/'dataset-index.json',{'version':'workflow-pilot-v1','synthetic':True,'limitation':'Tiny synthetic workflow test; no natural-user distribution or OS-isolated blinded claim','groups':groups,'counts':{k:sum(v) for k,v in counts.items()},'files':outputs})
write(a/'train-data-request.json',{'schema':'edge-ai-training-data/request-v1','version':'workflow-pilot-v1','purpose':'验证数据准备和32微步技术链路，不晋升生产模型','review_status':'accepted','sources':[outputs['train'],outputs['valid']],'reserved_groups':[g for g,s in groups.items() if s in ('development','final')]})
base=json.loads((r/'studies/voice-interaction/experiments/mac/2026-10-22-qwen-native-baseline-v1/short/request.json').read_text())
for name,suite in [('base-development',outputs['development']),('smoke',outputs['development'])]:
 req=json.loads(json.dumps(base));req['run_id']='workflow-'+name;req['suite_ref']=suite;req['generation'].update(max_tokens=128,context_tokens=2048)
 if name=='smoke':
  ss=json.loads(Path(suite).read_text());ss['samples']=ss['samples'][:1];write(a/'smoke-suite.json',ss);req['suite_ref']=str(a/'smoke-suite.json')
 write(a/(name+'-adapter.json'),req)
write(a/'evaluation-request.json',{'schema':'edge-ai-evaluation-plan/request-v1','profile':'native-tool-persona-v1','purpose':'development','question':'新数据与任务化交接是否能运行；原生格式、语义、人设分别观察','suite_ref':outputs['development'],'review_status':'accepted','learning_groups':[g for g,s in groups.items() if s in ('train','valid')],'scorer':{'version':'qwen-lifecycle-native-v1','rules':'native/JSON/Schema/Registry分层、精确工具参数、人设关键词仅诊断、普通聊天无调用'},'measurement':{'boundary':'request through pure intake; no tool execution','resources':'process tree; Mac RSS separate from MLX allocation','cache':'fresh MLX per case'},'budget':{'total_seconds':600}})
write(record/'data-plan.json',{'synthetic':True,'counts':{k:sum(v) for k,v in counts.items()},'external_data_index':str(a/'dataset-index.json'),'new_model_execution':'NOT_RUN','historical_inputs':len(old),'limitations':['Final set reserved, not OS-isolated','Synthetic wording families; pipeline test only','32 microsteps cannot establish learning capability']})
print(a,record)
