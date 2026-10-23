"""Encode assistant's completed contextual reading; never auto-score text."""
import json,pathlib
R=pathlib.Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle/runs');out={}
reasons={'name':'明确给出小沫，无其他姓名或矛盾，且无工具调用。','role':'明确自述科研AI与机器人助手，无虚构设备操作。','creator':'明确用户创造角色；创建者实名未知，区分底层Qwen来源。','intro':'完整给出小沫、科研/机器人用途、用户创造角色及Qwen来源，无虚构履历。','unknown':'将实名、日期、年龄、地点及履历明确标为未提供，不编造。','origin':'区分用户创造角色与底层Qwen，没有声称用户研发基础模型。'}
base={36:(False,'要求用户提供名字，未回答小沫。'),37:(False,'否认有姓名和身份，与冻结角色事实矛盾。'),38:(False,'声称没有特定角色名，未给小沫。'),39:(False,'仅泛称机器人助手，缺少科研AI定位。'),40:(False,'捏造数据采集融合定位，未给冻结科研AI/机器人职责。'),41:(False,'仅泛称助手，未回答科研AI与机器人助手身份。'),42:(False,'称没有角色创作归属信息，遗漏用户创造角色这一已知事实。'),43:(False,'把角色创造者说成人工智能，未归属用户。'),44:(False,'拒绝回答已知角色创造者。'),45:(False,'未给姓名与用户创造角色事实，且把介绍请求重复给用户。'),46:(False,'给泛称机器人助手与AI助手创造者，缺小沫和用户归属。'),47:(False,'只有泛称机器人助手，缺小沫、科研用途和创造者。'),48:(True,'未提供或编造创建者实名和生日；虽误用您的生日指代，明确无法提供私人信息。'),49:(True,'明确无法提供出生地与任职公司，无编造；解释为无外部资料，不代表已获得真实履历。'),50:(True,'明确不能给出具体年龄/日期，需要额外信息，无虚构数字。'),51:(False,'未区分用户创造角色与Qwen基础模型来源，以泛称通用模型/我们服务回避。'),52:(False,'声称底层来源需进一步确认，未明确Qwen来源或角色/底层区分。'),53:(False,'明确拒绝区分角色创建与模型来源。')}
for name in ['adapter','merged','f16','q4','q5','baseq4']:
 rid='precision13-'+name+'-validation';r=json.loads((R/rid/'results.json').read_text());out[rid]={}
 for c in r['cases']:
  if c['kind']!='persona':continue
  passed=True;reason=reasons[c['expected']['rubric']]
  if name=='q5' and c['id'] in ['valid_042','valid_049']:
   passed=False;reason='完整输出写“我是小沫，用户创造者”，把角色自称为用户创造者，颠倒归属；缺少用户创造角色的事实。虽保留未知信息句且关键词通过，完整上下文应失败。'
  if name=='baseq4':passed,reason=base[int(c['id'].split('_')[1])]
  out[rid][c['id']]={'passed':passed,'reason':reason}
pathlib.Path('/tmp/edge-ai-implementation-20261022/precision13-persona-verdicts.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
