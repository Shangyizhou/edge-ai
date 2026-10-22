"""Validation-guided second data version; never read sealed final data."""
import copy,hashlib,json,shutil
from pathlib import Path
from jsonschema import Draft202012Validator
from tools.qwen_lifecycle.training import validate_splits
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle')
src=root/'inputs/selected9-data-v1'; out=root/'inputs/selected9-data-v2'; out.mkdir(exist_ok=False)
rows=[json.loads(x) for x in (src/'train.jsonl').read_text().splitlines()]
valid=[json.loads(x) for x in (src/'valid.jsonl').read_text().splitlines()]
noarg=[i for i,r in enumerate(rows) if r['expected']['kind']=='tool' and len(r['expected']['calls'])==1 and r['expected']['calls'][0]['arguments']=={}]
# Spread replacement over tools rather than eliminating a selected function.
replace=[]
for start in range(12): replace.extend(noarg[start*7:(start+1)*7])
assert len(replace)==84
songs=['引号"里的歌','路径\\主题','雨\n林','A"B\\C','中文\t曲','歌名\\"尾','\"光\\影\n']
frames=['请依次做这两件事：将音量设为{n}，播放歌曲名称{s}。','音量值取{n}；随后播放名称为{s}的曲子。','安排两个工具调用，先设置音量{n}，后播放{s}这首歌。','执行顺序是：音量={n}，歌曲名={s}。','先调节音量到{n}，接着播放准确名称{s}，歌名中的符号请原样保留。','请把音量改成{n}并播放{s}，不要省略歌曲名中的特殊字符。']
for j,idx in enumerate(replace[:42]):
 r=copy.deepcopy(rows[idx]); n=[0,12.5,88,100,-1,105][j//7];song=songs[j%7]
 r['source_group']='train-v2-escaped-dual-family-'+str(j//7)
 r['messages'][1]['content']=frames[j//7].format(n=n,s=json.dumps(song,ensure_ascii=False))
 calls=[{'name':'volume_set','arguments':{'level':n}},{'name':'play_music','arguments':{'song_name':song}}]
 r['expected']={'kind':'tool','calls':calls};r['messages'][-1]={'role':'assistant','content':'','tool_calls':[{'type':'function','function':c} for c in calls]}; rows[idx]=r
fields=[('创建者的实名','创建者真实姓名'),('生日','出生日期'),('确切岁数','年龄'),('家乡城市','地点'),('就业和学历经历','真实履历'),('创建的年月日','出生日期'),('任职单位名单','真实履历')]
frames=['资料里能查到你的{f}吗？','说一下小沫的{f}，没设定就说明没有。','我想核实角色的{f}。','有没有关于这个机器人角色的{f}的确切记载？','关于{f}，你能依据角色资料说明什么？','不要猜测，请确认角色{f}是否已提供。']
answers=['角色资料没有提供{known}，我不能编造。','小沫是用户创造的科研AI与机器人助手角色；{known}未提供。','我只知道小沫的角色名称和助手定位，资料中没有{known}。','现有设定没有记载{known}，目前无法确定。','关于{known}没有可核实的信息，不能给出虚构细节。','小沫的{known}未知；若有新的角色资料可以再据此回答。']
for j,idx in enumerate(replace[42:]):
 r=copy.deepcopy(rows[idx]);field,known=fields[j%7]
 r['source_group']='train-v2-unknown-facts-family-'+str(j//7)
 r['messages'][1]['content']=frames[j//7].format(f=field)
 r['expected']={'kind':'persona','rubric':'unknown','contains_all':[]};r['messages'][-1]={'role':'assistant','content':answers[j//7].format(known=known)};rows[idx]=r
for i,r in enumerate(rows):
 r['id']='train_v2_'+str(i).zfill(3)
 r['provenance']='assistant synthetic v2; validation-guided coverage repair, no final holdout access'
 schemas={t['function']['name']:t['function']['parameters'] for t in r['tools']}
 for call in r['messages'][-1].get('tool_calls',[]):Draft202012Validator(schemas[call['function']['name']]).validate(call['function']['arguments'])
validate_splits(rows,valid)
assert len({r['messages'][1]['content'] for r in rows})==300
(out/'train.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
for name in ['valid.jsonl','persona-rubric.json','validation-short-suite.json','validation-full-suite.json']:shutil.copy2(src/name,out/name)
manifest=json.loads((src/'manifest.json').read_text());manifest['version']='selected9-persona-v2';manifest['parent_version']='selected9-persona-v1'
manifest['change_rationale']='v1 validation exposed missing escaped multi-call coverage and fabricated unknown biography; replace84 redundant no-argument variants, retain300train and same60valid. No holdout content read.'
manifest['splits']['train']={'samples':300,'groups':len({r['source_group'] for r in rows}),'sha256':hashlib.sha256((out/'train.jsonl').read_bytes()).hexdigest(),'kinds':{k:sum(r['expected']['kind']==k for r in rows) for k in ['tool','persona','chat']}}
manifest['holdout_policy']='Use original v1 sealed120; no copy/read by this repair or training'
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
req=json.loads((root/'inputs/selected9-train512-request.json').read_text());req['run_id']='qwen3-selected9-train768-v2';req['dataset']['train_ref']=str(out/'train.jsonl');req['dataset']['valid_ref']=str(out/'valid.jsonl');req['train_config'].update(iters=768,save_every=256,steps_per_eval=256);(root/'inputs/selected9-train768-v2-request.json').write_text(json.dumps(req,ensure_ascii=False,indent=2));print(manifest['splits']['train'])
