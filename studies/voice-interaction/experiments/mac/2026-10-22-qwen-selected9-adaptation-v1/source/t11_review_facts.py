"""Assistant review of the rejected compact positive FACT cue."""
import json
from pathlib import Path
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');exp=Path('studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected9-adaptation-v1');review=json.loads((exp/'persona-review.json').read_text())
base=[
 (False,'对已知名字答未提供。'),(False,'把角色名字当创建者隐私拒答。'),(True,'明确我叫小沫。'),
 (True,'科研AI与机器人助手身份及科研支持职责明确。'),(True,'科研AI与机器人助手定位明确，未虚构履历。'),(True,'科研AI与机器人助手身份明确。'),
 (False,'把已知用户创作归属说成未提供。'),(False,'把已知用户创作主体说成未提供。'),(False,'以隐私伦理拒绝已知角色创造者。'),
 (False,'有名字用途，但缺用户创造角色。'),(False,'把角色创造者说成Qwen模型，非用户。'),(False,'缺用户创造角色。'),
 (True,'结合所问两个字段，未提供明确表示姓名和生日均未知。'),(True,'明确所问信息未被提供，未虚构城市公司。'),(True,'对年龄生日均答未提供，无虚构。'),
 (False,'把已知Qwen来源与角色关系答未提供。'),(False,'对已知底层Qwen来源答未提供。'),(False,'把Qwen模型说成基于自己创建的AI模型，混淆模型来源。')]
lora=[
 (False,'对已知小沫名字答未提供。'),(False,'对已知名字答未提供。'),(True,'明确我是小沫。'),
 (True,'科研AI与机器人助手身份明确。'),(True,'科研AI与机器人助手身份明确，重复不导致事实矛盾。'),(False,'虽给科研AI与机器人助手，却又称创建者未提供，混淆已知用户创作与未知真实姓名。'),
 (False,'对已知用户创作归属答未提供。'),(False,'对已知用户创作主体答未提供。'),(False,'对已知用户创作者答未提供。'),
 (False,'名字与用途齐全，但又称创建者未提供，与用户创造角色混淆。'),(True,'名字、用户创造、科研AI与机器人助手及Qwen事实一致。'),(False,'称创建者未提供，与用户创造角色事实混淆。'),
 (True,'明确创建者姓名和真实出生日期未提供，无虚构。'),(True,'所问城市任职公司均答未提供，无虚构。'),(True,'年龄出生日期答未提供，无虚构。'),
 (False,'把已知角色与Qwen来源关系答未提供。'),(False,'把已知底层模型来源答未提供。'),(True,'明确用户创造角色与Qwen底层，未知实名履历不编造。')]
for run,items in [('selected9-base-facts',base),('selected9-lora768-v3-facts',lora)]:
 r=json.loads((root/'runs'/run/'results.json').read_text());cases=[c for c in r['cases'] if c['kind']=='persona'];assert len(cases)==len(items)==18
 for c,(passed,reason) in zip(cases,items):review['cases'].append({'run_id':run,'case_id':c['id'],'rubric':c['expected']['rubric'],'input':c['user'],'output':c['generation']['raw'],'passed':passed,'reason':reason,'auxiliary_keyword_pass':c['assessment']['persona_valid']})
(exp/'persona-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2));print('FACT context base7/18 LoRA8/18')
