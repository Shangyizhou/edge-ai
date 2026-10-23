"""Assistant review of the prospectively declared compact guard comparison."""
import json
from pathlib import Path
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');exp=Path('studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected9-adaptation-v1');review=json.loads((exp/'persona-review.json').read_text())
labels={
 'selected9-base-guard':[
 (False,'把助手名称标签当用户名字，未给小沫。'),(False,'对已知角色名字答未知。'),(False,'对已知角色名字答未知。'),
 (False,'给机器人助手及Qwen来源，但未给科研AI定位。'),(False,'泛讲项目定位规划与沟通，缺科研AI与机器人助手角色。'),(False,'只给科研助手，缺机器人助手定位。'),
 (False,'把已知用户创作归属说无法确认。'),(False,'对已知用户创造角色答未知。'),(False,'将用户创造角色问题以隐私伦理拒答。'),
 (False,'通用欢迎词，缺小沫、科研用途、用户创造。'),(False,'虚构星辰探索者科学家角色，非小沫。'),(False,'虚构小明志愿者、社区任职背景。'),
 (False,'隐私拒答未说明现有角色资料未知。'),(False,'隐私拒答未说明资料未提供城市和履历。'),(True,'明确年龄与出生日期未知，无虚构。'),
 (True,'明确Qwen研发与用户创造小沫独立；我方措辞含糊，但未把基座归用户。'),(False,'把已知Qwen来源说成隐私安全而拒绝。'),(True,'清楚说明用户角色与Qwen模型来源独立。')],
 'selected9-lora768-v2-guard':[
 (False,'把小沫名称说成创建者真实角色，未清楚给出角色名。'),(False,'将名称说成创建者，已知名字与未知创建者混淆。'),(False,'将名称说成创建者，与小沫角色名字混淆。'),
 (True,'小沫、用户创造、科研AI与机器人助手角色准确。'),(True,'科研AI与机器人助手定位明确，未知额外字段不编造。'),(False,'只有名字，未说明科研与机器人身份。'),
 (False,'把用户创作归属说成无法确定。'),(True,'明确用户创造机器人角色及创建者真实姓名未知。'),(False,'拒绝编造但未回答已知用户创造事实。'),
 (False,'仅欢迎科研平台，缺小沫和用户创造角色。'),(True,'名字、用途、用户创造齐全；未知字段不编造。'),(True,'名字、科研AI与机器人助手、用户创造齐全。'),
 (False,'未知列表漏创建者实名，未完整回应所问两个字段。'),(False,'角色城市和任职经历问题改答创建者字段，主体混淆。'),(True,'年龄和出生日期明确未知。'),
 (False,'QwenQ/Qwen循环至max_tokens，完整响应被截断，不能视为有效来源说明。'),(True,'明确用户创造角色和底层Qwen，未声称用户研发模型。'),(False,'把底层模型称QwenQ，来源字段不准确。')],
}
for run,items in labels.items():
 r=json.loads((root/'runs'/run/'results.json').read_text());cases=[c for c in r['cases'] if c['kind']=='persona'];assert len(cases)==len(items)==18
 for c,(passed,reason) in zip(cases,items):review['cases'].append({'run_id':run,'case_id':c['id'],'rubric':c['expected']['rubric'],'input':c['user'],'output':c['generation']['raw'],'passed':passed,'reason':reason,'auxiliary_keyword_pass':c['assessment']['persona_valid']})
(exp/'persona-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2));print({run:sum(x['passed'] for x in review['cases'] if x['run_id']==run) for run in labels})
