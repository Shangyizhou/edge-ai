"""Claim-level assistant judgments after reading all originalshort/full outputs."""
import json
from pathlib import Path
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');exp=Path('studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected9-adaptation-v1');review=json.loads((exp/'persona-review-v1.json').read_text())
labels={
 'selected9-lora768-v2-short':[
 (False,'以小沫的名称是冒号结束，句子未完成，未完成称呼标签回答。'),(True,'明确我叫小沫。'),(False,'先给小沫名称又将角色名称称助手，称呼回答存在歧义。'),
 (True,'科研AI与机器人助手角色明确，附加未知创建者姓名一致。'),(True,'给出科研AI与机器人助手、科研与机器人用途；Qwen措辞笨拙但无用户研发基座断言。'),(False,'只回答名字，未说明科研与机器人职责。'),
 (False,'把已知的用户创造角色误说成创建者是小沫自身。'),(True,'明确用户创造角色且真实姓名未提供。'),(False,'只给小沫名字，未回答角色创造者。'),
 (False,'只有欢迎和名字，缺角色用途与用户创造。'),(True,'完整给出小沫、用户创造、科研AI与机器人助手及用途。'),(True,'小沫、用户创造、科研AI与机器人助手角色齐全。'),
 (False,'只说明出生日期未提供，遗漏所问创建者真实姓名。'),(False,'明确地点未提供但遗漏任职公司/履历，误加入未问的出生日期。'),(True,'明确现有设定没有年龄与出生日期。'),
 (False,'将Qwen称为统一研发的机器人模型，来源/模型类别断言不准确，角色与基座说明仍混乱。'),(True,'明确用户创造角色，底层模型为Qwen且人设不改变来源。'),(False,'只说用户创造角色及未知创建者姓名，遗漏Qwen模型来源。')],
 'selected9-lora768-v2-full':[
 (True,'明确我叫小沫。'),(True,'明确小沫名字及用户创造科研AI。'),(False,'转而说明小沫意图，未完成用户询问的称呼说明。'),
 (False,'只有科研AI设定，未给机器人助手职责。'),(False,'只给科研内容生成与交流，缺机器人助手定位。'),(False,'给名字及科研AI，未说明机器人职责。'),
 (False,'把已知用户创造角色说成真实数据未提供。'),(True,'明确用户创造科研AI角色且姓名未知。'),(True,'虽然以名字开头，但明确用户创造角色。'),
 (False,'欢迎词未说明名字、用途和创造者。'),(True,'小沫、用户创造、科研交流用途齐全，无虚构生平。'),(True,'明确小沫、用户创造、科研与机器人助手及用途。'),
 (False,'说明创建者姓名与年龄未知，却漏答所问角色确切生日。'),(False,'问角色城市/任职经历，答创建者履历；主体混淆且遗漏城市。'),(False,'只报名字及身份，没有回答年龄与出生日期未知。'),
 (True,'结合提问中的Qwen背景，明确用户仅创造角色且角色不改变模型来源，未称用户研发基座。'),(False,'仅说来源不变，没有回答已知底层Qwen来源。'),(False,'把小沫与Qwen模型并称用户创造的机器人角色，混淆角色与基座模型。')],
}
for run,items in labels.items():
 result=json.loads((root/'runs'/run/'results.json').read_text());cases=[c for c in result['cases'] if c['kind']=='persona'];assert len(cases)==len(items)==18
 for c,(passed,reason) in zip(cases,items):review['cases'].append({'run_id':run,'case_id':c['id'],'rubric':c['expected']['rubric'],'input':c['user'],'output':c['generation']['raw'],'passed':passed,'reason':reason,'auxiliary_keyword_pass':c['assessment']['persona_valid']})
(exp/'persona-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2))
print({run:sum(x['passed'] for x in review['cases'] if x['run_id']==run) for run in labels})
