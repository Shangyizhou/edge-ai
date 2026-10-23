"""Assistant fact review of canonical-answer adaptation, preserving failures."""
import json
from pathlib import Path
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');exp=Path('studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected9-adaptation-v1');review=json.loads((exp/'persona-review.json').read_text())
short=[(False,'称呼标签问题误调用following_status；即使调用格式合法，也不是角色文本回答。')]
short += [(True,'完整给出小沫、用户创造的科研AI与机器人助手、Qwen底层模型及未知字段；回应本项预定事实且无虚构。') for _ in range(17)]
full=[
 (False,'称呼问题误调用volume_set(50)，不应对身份问题提交工具。'),(True,'明确小沫名称，附加未知字段未编造。'),(False,'称呼问题误调用following_status。'),
 (False,'只有科研AI，缺机器人助手职责。'),(True,'科研AI与机器人助手及科研/机器人用途完整。'),(False,'只给科研AI，缺机器人助手身份。'),
 (False,'创作归属问题误调用following_status。'),(True,'明确用户创造角色，真实姓名未知。'),(True,'明确用户创造科研AI角色，真实姓名未知。'),
 (True,'名字、用户创造、科研AI与机器人助手/Qwen定位明确。'),(True,'名字、科研AI角色与用户创造齐全，未虚构背景。'),(True,'名字、用户创造、科研AI与机器人角色明确。'),
 (False,'创建者姓名和生日问题误调用following_status。'),(True,'明确创建者实名、出生日期、年龄、地点、真实履历未提供；未虚构城市任职经历。'),(False,'年龄与生日问题误调用following_status。'),
 (False,'未说明Qwen模型来源与用户创造角色的区别，只给角色及未知字段。'),(False,'未回答底层Qwen来源。'),(True,'明确用户创造科研AI角色与底层Qwen模型，未把模型研发归给用户。')]
for run,items in [('selected9-lora768-v3-short',short),('selected9-lora768-v3-full',full)]:
 r=json.loads((root/'runs'/run/'results.json').read_text());cases=[c for c in r['cases'] if c['kind']=='persona'];assert len(cases)==len(items)==18
 for c,(passed,reason) in zip(cases,items):review['cases'].append({'run_id':run,'case_id':c['id'],'rubric':c['expected']['rubric'],'input':c['user'],'output':c['generation']['raw'],'passed':passed,'reason':reason,'auxiliary_keyword_pass':c['assessment']['persona_valid']})
(exp/'persona-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2));print('v3 short17/18, full9/18; no human acceptance')
