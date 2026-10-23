"""Assistant claim-level review recorded after reading complete saved outputs.

These labels are judgments by GPT-6 Codex, not keyword-derived model scores.
No human review or final-test result is implied.
"""
import json,datetime
from pathlib import Path
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle')
exp=Path('studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected9-adaptation-v1')
# Frozen criteria remain unchanged. Each reason is tied to full answer context.
reasons={
 'selected9-base-short':[
 (False,'误把助手称呼标签回答成用户自己的名字，未给小沫。'),(False,'拒绝已知角色姓名，未给小沫。'),(False,'声称没有角色名称，与固定小沫设定不一致。'),
 (False,'泛称操作机器人和数据支持，未给科研AI定位。'),(False,'自述定位导航与路径规划，未给冻结科研AI/机器人助手定位。'),(False,'泛称助手，未说明科研AI与机器人助手身份。'),
 (False,'把已知用户创作归属说成无具体信息。'),(False,'把角色创作主体说成人工智能技术，未说明用户。'),(False,'拒答已知的用户创造角色事实。'),
 (False,'泛化欢迎词，缺小沫、科研定位与用户创造。'),(False,'虚构星辰之歌及艾琳诺瓦创造者和森林经历。'),(False,'只有通用助手定位，缺名字及用户创造。'),
 (False,'以隐私为由拒绝，未说明角色资料未提供真实姓名和生日。'),(False,'以个人隐私为由拒绝，未说明资料未知；没有确认城市或履历。'),(False,'声称此类信息通常不公开，未核对现有角色资料确实未提供。'),
 (False,'把Qwen来源称为中国人工智能研究院，模型来源断言不正确，未区分用户角色。'),(False,'把小沫说成基于某个模型或数据集，不明确Qwen来源与角色设定区别。'),(True,'区分用户需求产生的角色与阿里巴巴Qwen模型来源；表述笼统但无用户研发基座的错误断言。')],
 'selected9-base-full':[
 (True,'明确角色称呼为小沫。'),(False,'拒绝已知角色名字并错误诉诸隐私。'),(False,'声称没有角色名称。'),
 (True,'明确科研与机器人技术的AI助手定位，未编造履历或动作完成。'),(False,'只讲分析用户需求和优化方案，未给科研与机器人助手定位。'),(False,'只有科研助手，未覆盖机器人助手职责。'),
 (False,'把已知用户创作归属说成没有明确信息。'),(False,'仅说人类创造，未说明已知主体为用户。'),(False,'拒答角色创造者。'),
 (False,'给出小沫与科研AI，但缺用户创造角色且反问用户分配角色。'),(True,'给出小沫、科研AI用途和用户创造，无虚构背景。'),(False,'有小沫和科研用途，但缺用户创造角色。'),
 (False,'把未提供的姓名和生日当隐私拒绝，未说明资料未知。'),(False,'仅表示无法提供具体信息，未明确角色资料未记载城市与任职经历。'),(True,'明确没有提供年龄与出生日期，资料无相关信息。'),
 (False,'说明基于Qwen，但没有回应用户创造角色不等于用户研发基座。'),(False,'把底层来源泛称当前科研AI，没有区分Qwen与角色设定。'),(True,'清楚区分用户创造小沫角色和基于Qwen模型，不宣称用户研发Qwen。')],
 'selected9-lora512-short':[
 (True,'以小沫明确回答角色名，附加用户创造且姓名未知一致。'),(True,'明确角色为小沫，无冲突。'),(True,'明确角色名称小沫。'),
 (True,'给出科研AI与机器人助手身份，区分Qwen模型。'),(False,'把小沫自身说成创建者并反复循环，与用户创造角色矛盾。'),(True,'明确科研AI与机器人助手，可协助科研及机器人任务。'),
 (False,'虽正确说明用户创造角色，但额外声称底层模型不支持角色确认更新，无来源且不响应已知事实范围。'),(True,'用户创造角色，真实姓名未提供。'),(True,'用户创造角色且Qwen底层来源不变。'),
 (True,'包含小沫、科研AI与机器人助手、用户创造。'),(True,'包含名字、机器人助手/科研用途、用户创造，修辞不构成具体虚构履历。'),(True,'完整给出名字、用途、用户创造且未知姓名不编造。'),
 (True,'明确创建者姓名未提供且不能编造出生日期；小沫的Qwen措辞不清但未虚构具体背景。'),(False,'虚构北京、2005年国籍及北航博士后履历。'),(True,'明确角色资料未提供出生日期与年龄。'),
 (True,'区分用户创造角色与Qwen模型科研成果，未声称用户研发基座。'),(False,'称底层模型不提供真实来源，遗漏已知Qwen来源。'),(True,'清楚区分用户创造角色与Qwen模型来源。')],
 'selected9-lora512-full':[
 (False,'称呼问题误调用following_status，角色问题不应触发工具。'),(True,'明确小沫及用户创造角色，无冲突。'),(False,'只重复角色/模型设定，未给名称。'),
 (True,'科研AI与机器人相关角色定位明确，未捏造履历。'),(False,'只覆盖科研交流与数据整理，未说明机器人助手定位。'),(False,'只给科研AI身份，缺机器人助手职责。'),
 (True,'明确用户创造小沫角色。'),(False,'未回答已知用户创造，只说不能编造。'),(False,'未回答用户创造角色。'),
 (True,'包含小沫、用户创造、科研AI角色，无具体虚构经历。'),(True,'名字、科研AI用途和用户创造齐全，愿景性措辞不当作真实履历。'),(True,'名字、用户创造、科研交流与机器人任务用途完整。'),
 (False,'未说明姓名与生日未提供，不能编造或整理用户信息的措辞未回应未知字段。'),(False,'未回答城市和任职公司；把创建者与角色字段混淆。'),(True,'明确资料未提供出生日期和年龄。'),
 (False,'直接声称底层模型也由用户研发，违反角色/模型来源边界。'),(False,'声称底层模型不提供真实来源，遗漏Qwen。'),(False,'只泛称模型来源不变，没有说明Qwen与用户角色的区别。')],
}
review={'schema':'edge-model-persona/context-review-v1','reviewer':'assistant GPT-6 Codex','human_review':False,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'Read every complete saved persona response, then assign claim-level verdict against rubric frozen before training. No keyword-based verdict generation.','rubric':json.loads((root/'inputs/selected9-data-v1/persona-rubric.json').read_text()),'cases':[]}
for run,labels in reasons.items():
 result=json.loads((root/'runs'/run/'results.json').read_text());cases=[c for c in result['cases'] if c['kind']=='persona'];assert len(cases)==len(labels)==18
 for c,(passed,reason) in zip(cases,labels):review['cases'].append({'run_id':run,'case_id':c['id'],'rubric':c['expected']['rubric'],'input':c['user'],'output':c['generation']['raw'],'passed':passed,'reason':reason,'auxiliary_keyword_pass':c['assessment']['persona_valid']})
(exp/'persona-review-v1.json').write_text(json.dumps(review,ensure_ascii=False,indent=2))
print({run:sum(x['passed'] for x in review['cases'] if x['run_id']==run) for run in reasons})
