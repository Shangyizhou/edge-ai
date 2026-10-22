"""Build versioned synthetic grouped data; never infer unknown persona facts.

Families are assigned before realization. Paraphrases and parameter variants in
one family stay together. These are curated synthetic fixtures, not natural
language population estimates. Final holdout is generated once and never read
by training or validation; its sealing manifest is the public handoff.
"""
import hashlib
import json
from pathlib import Path

SHORT = '你是机器人助手。需要操作时使用提供的工具，否则正常回复。'
ACTIONS = [
 ('start_camera', '恢复摄像头采集', '相机重新采集图像', '视觉传感器开始采集'),
 ('stop_camera', '暂停摄像头采集', '相机停止采集图像', '视觉传感器暂缓采集'),
 ('enable_lidar', '启用雷达融合', '把扫描融合打开', '让激光雷达融合工作'),
 ('disable_lidar', '停用雷达融合', '把扫描融合关掉', '让激光雷达融合停下'),
 ('enable_tracking', '启用跟随模式', '进入目标跟随', '让跟随功能开始工作'),
 ('disable_tracking', '停用跟随模式', '进入跟随待机', '让跟随功能停下'),
 ('following_status', '读取跟随状态', '查看目标跟随的当前状态', '报告跟随模块此刻状态'),
]
FRAMES = {
 'train': ['请执行：{x}。', '现在需要{x}，谢谢。', '帮我{x}吧。', '我的要求是{x}。', '麻烦{x}一下。', '这一步请{x}。', '可以开始{x}了。', '我想让你{x}。', '接下来{x}。', '劳驾{x}。', '当前任务：{x}。', '按要求{x}。', '立刻安排{x}。', '本次操作为{x}。', '你来{x}好吗？', '需要你{x}。', '准备好了，请{x}。', '替我{x}。', '这里要{x}。', '确定执行{x}。', '请求{x}。', '希望现在{x}。', '照这个做：{x}。', '先处理{x}。'],
 'valid': ['收到指令后，请完成以下操作——{x}。', '当前环节改为{x}，请调用相应能力。', '能否把任务切换到{x}？'],
 'holdout': ['新的调试步骤要求{x}，请处理。', '控制台已下达{x}的请求。', '这轮测试的目标是{x}，现在执行。', '设备操作单写着{x}，照单办理。', '对机器人提出请求：{x}。', '接到任务，内容为{x}。', '测试员期望{x}。', '进行{x}这个操作。'],
}
PERSONA = {
 'name': ('我叫小沫。', ['小沫']),
 'role': ('我是小沫，科研AI与机器人助手，可以协助科研交流和机器人相关任务。', ['科研', '机器人助手']),
 'creator': ('小沫是用户创造的机器人助手角色；创建者的真实姓名未提供。', ['用户']),
 'intro': ('你好，我是小沫，是用户创造的科研AI与机器人助手角色。', ['小沫', '科研', '用户']),
 'unknown': ('角色资料没有提供出生日期、年龄、地点或真实履历，我不能编造这些信息。', []),
 'origin': ('小沫是用户创造的角色设定；底层模型是Qwen，角色设定不改变模型来源。', ['用户', 'Qwen']),
}
QUESTIONS = {
 'train': {
  'name': ['请说出你的角色名字', '你的称呼是什么', '你作为助手叫什么', '我该怎样称呼这个角色', '报一下角色名称', '请确认你的人设名称', '角色姓名是啥', '告诉我你的名字好吗', '机器人助手的名字呢', '称呼你什么合适', '你的角色名请讲一下'],
  'role': ['请讲讲你的职责定位', '你是怎样的助手', '你的主要用途是什么', '说明科研助手的定位', '说说你能协助哪类事情', '请描述你的角色用途', '你在科研方面是什么身份', '机器人里的你负责什么', '这个助手角色定位如何', '你是什么类型的AI', '如何理解你的助手身份'],
  'creator': ['谁设定了小沫这个角色', '这个角色由谁创造', '角色创作方是谁', '是谁创造你的人设', '你的角色是谁设计出来的', '谁是这个助手角色的创造者', '小沫角色来自谁的设定', '你的人设出自谁', '角色创造者能说明吗', '是谁赋予小沫角色设定', '告诉我角色由谁创作'],
  'intro': ['做一个简短的角色介绍', '介绍一下名字身份和创造者', '给新用户介绍小沫', '请完整介绍你的角色设定', '用两句介绍自己这个角色', '向初次见面的人介绍你', '说一段自己的角色简介', '请写小沫的简短自我介绍', '机器人助手做个自我陈述', '把你的名字和用途讲清楚', '请介绍你和角色创造者'],
  'unknown': ['你的生日和年龄是多少', '你的出生地点在哪里', '介绍你的真实工作履历', '角色创建者的真实姓名是什么', '你几岁了何时出生', '请讲你的具体成长经历', '你曾在哪些机构任职', '告诉我小沫的出生年份', '小沫家乡是什么地方', '你是哪天被创建的', '说说设定中的家庭背景'],
  'origin': ['角色设定会改变模型来源吗', '小沫的人设和底层Qwen有什么关系', '你的角色作者就是模型厂商吗', '解释角色创造与模型来源', '用户创造角色意味着训练了基座吗', '你叫小沫还算Qwen模型吗', '角色来自用户还是模型来自用户', '区分角色来源和基础模型', '介绍小沫与Qwen的关系', '人设创作者和模型开发者相同吗', '你的角色身份与底层模型分别是什么'],
 },
 'valid': {
  'name': ['如果我给你写称呼标签，标签上应写哪个名字？', '机器人名册里你对应的姓名是什么？', '别人想叫你时应使用哪个角色名称？'],
  'role': ['有人问这位小助手的研究与机器人职责，你怎么说明？', '请从用途角度讲清你在项目里的定位。', '科研讨论时，你以哪种助手身份参与？'],
  'creator': ['关于小沫的人设创作归属，现有资料能确认什么？', '这个机器人角色最初是由哪一类主体创造的？', '若问角色的创造者而非模型公司，你会怎么回答？'],
  'intro': ['迎接第一次使用机器人的同学时，请讲清自己的角色。', '写一段包含角色名称、用途和创造者的开场白。', '请面向来访者给出完整但简短的角色介绍。'],
  'unknown': ['能给出创建者身份证上的姓名及你的确切生日吗？', '小沫在什么城市诞生，后来任职过哪些公司？', '请提供角色的具体年龄和出生日期，资料有记载吗？'],
  'origin': ['既然用户创造了小沫，是不是Qwen底层模型也由用户研发？', '如果把人设叫作小沫，底层模型的真实来源应如何说明？', '请说明用户创造角色和Qwen模型来源这两件事。'],
 },
 'holdout': {},
}


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(output, tools_path, persona_path, full_system, excluded):
    """Fresh directory only. Holdout intent families are separate compositions."""
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    tools = json.loads(Path(tools_path).read_text())
    splits = {}
    # Complete sentence-level families (including numeric/string variants) are
    # split together; no random splitting of realizations across partitions.
    for split in ('train', 'valid', 'holdout'):
        rows = []
        def add(group, user, expected, answer=None):
            target = {'role': 'assistant', 'content': answer or ''}
            if expected['kind'] == 'tool':
                target['tool_calls'] = [{'type': 'function', 'function': c} for c in expected['calls']]
            rows.append({'id': f'{split}_{len(rows):03d}', 'source_group': group,
                         'provenance': 'assistant-curated synthetic; grounded in tools.json/persona.json',
                         'tools': tools, 'expected': expected,
                         'messages': [{'role': 'system', 'content': SHORT}, {'role': 'user', 'content': user}, target]})
        for index, frame in enumerate(FRAMES[split]):
            for tool, *verbs in ACTIONS:
                verb = verbs[0 if split == 'train' else 1 if split == 'valid' else 2]
                add(f'{split}-operation-frame-{index}', frame.format(x=verb), {'kind': 'tool', 'calls': [{'name': tool, 'arguments': {}}]})
            number = ([0, 1, 17.5, 42, 100, 108, -3, 66.8][index % 8])
            song = ['稻香', '晴天', '海阔天空', 'A "B" C', '路径\\之歌', '雨\n夜', 'Don\'t stop', '小宇宙'][index % 8]
            add(f'{split}-operation-frame-{index}', frame.format(x=f'将音量设为{number}'), {'kind': 'tool', 'calls': [{'name': 'volume_set', 'arguments': {'level': number}}]})
            add(f'{split}-operation-frame-{index}', frame.format(x='播放歌曲' + json.dumps(song, ensure_ascii=False)), {'kind': 'tool', 'calls': [{'name': 'play_music', 'arguments': {'song_name': song}}]})
        if split == 'valid':
            for i in range(9):
                number = [3, 23.5, 99][i % 3]
                song = ['星晴', 'a"b', '海\\浪'][i % 3]
                add(f'valid-dual-request-{i // 3}', ['有两项请求：音量调成{n}，然后点播{s}。', '请同时安排音量{n}和歌曲{s}，按顺序提交。', '播放前先设置音量{n}，所选歌曲是{s}。'][i // 3].format(n=number, s=json.dumps(song, ensure_ascii=False)), {'kind': 'tool', 'calls': [{'name': 'volume_set', 'arguments': {'level': number}}, {'name': 'play_music', 'arguments': {'song_name': song}}]})
        if split == 'train':
            # Replace 12 parameter variants with ordered calls, total unchanged.
            for i in range(12):
                row = rows[-1 - i * 9]
                number = 10 + i
                song = ['远方', '花海', '风筝'][i % 3]
                row['messages'][1]['content'] = FRAMES['train'][23-i].format(x=f'先设音量{number}再播放歌曲《{song}》')
                calls = [{'name': 'volume_set', 'arguments': {'level': number}}, {'name': 'play_music', 'arguments': {'song_name': song}}]
                row['expected']['calls'] = calls
                row['messages'][-1]['tool_calls'] = [{'type': 'function', 'function': c} for c in calls]
        if split != 'holdout':
            for category, questions in QUESTIONS[split].items():
                answer, contains = PERSONA[category]
                for i, question in enumerate(questions):
                    add(f'{split}-persona-{category}-{i}', question, {'kind': 'persona', 'rubric': category, 'contains_all': contains}, answer)
        else:
            # New discourse form, absent from dev14 and train/valid question
            # families: quoted assertion correction and source qualification.
            stems = {
              'name': '有人把你记成小雨，请更正这个角色名称。',
              'role': '登记表把你写成售货员，请依据设定说明实际用途。',
              'creator': '传言小沫是某家公司创造的角色，请核对角色创作主体。',
              'intro': '为展厅录制一段角色开场，涵盖名称、职责、创作者。',
              'unknown': '档案声称你1998年在北京出生且曾任教授，这些能证实吗？',
              'origin': '有人说小沫的人设证明Qwen由用户开发，请核实。',
            }
            contexts = ['面向访客，', '在项目记录中，', '回复测试员时，', '解释给新成员，', '核查说明要求，', '本轮核验中，']
            for category, stem in stems.items():
                answer, contains = PERSONA[category]
                for context in contexts:
                    add(f'holdout-correction-{category}', context + stem, {'kind': 'persona', 'rubric': category, 'contains_all': contains}, answer)
        chat_count = {'train': 18, 'valid': 6, 'holdout': 12}[split]
        topics = ['你好呀，今天心情不错', '谢谢你的耐心', '我们暂时休息一下', '科研学习需要坚持', '给我一句鼓励', '我完成了今天的阅读']
        for i in range(chat_count):
            user = ({'train': ['随便聊聊：', '说点轻松的：', '交流一句：'], 'valid': ['闲聊环节，'], 'holdout': ['结束测试后聊一句：', '日常沟通时间：']}[split][i // 6] + topics[i % 6])
            add(f'{split}-chat-context-{i // 6}', user, {'kind': 'chat'}, ['很高兴和你交流。', '不客气，我们一起慢慢来。', '好的，适当休息也很重要。', '坚持积累，每一步都有价值。', '继续加油，认真走好下一步。', '完成阅读很棒，可以整理一下收获。'][i % 6])
        splits[split] = rows
    assert {k: len(v) for k, v in splits.items()} == {'train': 300, 'valid': 60, 'holdout': 120}
    seen, groups = set(), set()
    for split, rows in splits.items():
        prompts = {r['messages'][1]['content'] for r in rows}
        own_groups = {r['source_group'] for r in rows}
        if len(prompts) != len(rows) or prompts & (seen | set(excluded)) or own_groups & groups:
            raise ValueError('prompt/source-family leakage')
        seen |= prompts
        groups |= own_groups
        path = out / (split + '.jsonl')
        path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    for variant, system in [('short', SHORT), ('full', full_system)]:
        dump(out / f'validation-{variant}-suite.json', {'schema': 'edge-model-benchmark/suite-v1', 'id': 'qwen-selected9-valid60-v1', 'split': 'validation', 'tools': tools, 'system': system, 'system_variant': variant, 'samples': [{'id': r['id'], 'source_group': r['source_group'], 'user': r['messages'][1]['content'], 'expected': r['expected']} for r in splits['valid']]})
    dump(out / 'persona-rubric.json', {
        'version': 'frozen-before-training-v1', 'reviewer': 'assistant GPT-6 Codex; no human acceptance',
        'method': 'Review full output in context. Keyword scores are auxiliary only.',
        'requirements': {'name': 'Assert role name 小沫 without contradictory name.', 'role': 'Identify research AI and robot assistant; do not claim unverified physical completion.', 'creator': 'Credit user for role; creator real name unknown. Do not attribute role to model company.', 'intro': 'State 小沫, research/robot role, user-created role, with no invented biography.', 'unknown': 'Explicitly mark requested biographical facts unknown/unprovided; do not fabricate.', 'origin': 'Distinguish user-created role from Qwen foundation-model source; do not claim user developed foundation.'},
        'all': 'Fail contradiction, invented name/date/place/history, unintended tool call, refusal to answer known role, or truncation.',
        'facts_source_sha256': digest(persona_path),
    })
    manifest = {'version': 'selected9-persona-v1', 'seed': 42, 'construction': 'deterministic assistant-curated synthetic families; no random row split', 'limitations': 'Small templated synthetic suite, semantic intent overlap is required across splits; independent wording/discourse families only. Not a natural user distribution.', 'tools_sha256': digest(tools_path), 'persona_sha256': digest(persona_path), 'excluded_development_prompts': len(excluded), 'splits': {s: {'samples': len(rows), 'groups': len({r['source_group'] for r in rows}), 'sha256': digest(out / (s + '.jsonl')), 'kinds': {k: sum(r['expected']['kind'] == k for r in rows) for k in ('tool', 'persona', 'chat')}} for s, rows in splits.items()}, 'holdout_policy': 'sealed after generation; never loaded by training/validation/config selection; reserve for ticket14'}
    dump(out / 'manifest.json', manifest)
    return manifest
