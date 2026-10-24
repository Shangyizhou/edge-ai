"""Validate release associations and generate version notes/cards from frozen catalog."""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from catalog import ROOT, CATALOG, DEFAULT_HOME, read_index

from paths import RELEASE_ROOT
RELEASES=RELEASE_ROOT


def load_release():
    current=json.loads((RELEASES/'current.json').read_text());path=(RELEASES/current['path']).resolve()
    if not path.is_relative_to(RELEASES.resolve()):raise ValueError('Release source escapes root')
    r=json.loads(path.read_text());_,records=read_index()
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,100}',r['release_id']):raise ValueError('Invalid release ID')
    assert r['release_id']==current['release_id']
    for key in ['selected_model_id','training_id']:
        assert r[key] in records
    for key in ['reference_model_ids','source_model_ids','dataset_ids','evaluation_ids']:
        assert all(id in records for id in r[key])
    assert r['training_id'] in records[r['selected_model_id']]['training_ids']
    assert r['statuses']['validation_status']=='development_gates_not_passed'
    decisions=[]
    for id in r['decision_ids']:
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,100}',id):raise ValueError('Invalid decision ID')
        p=path.parent/'decisions'/(id+'.json');d=json.loads(p.read_text());assert d['decision_id']==id
        assert all(x in records for k in ['training_ids','evaluation_ids'] for x in d[k])
        narrative=(p.parent/d['narrative_source']).resolve()
        if not narrative.is_relative_to(p.parent.resolve()):raise ValueError('Decision narrative escapes root')
        d['markdown']=narrative.read_text();decisions.append(d)
    return r,records,decisions,path.parent


def card(r,records,decisions,local=True,home=DEFAULT_HOME):
    training=records[r['training_id']];config=training['configuration'];data=training['dataset_summary'];base=training['execution_summary']['base_artifact'];chosen=records[r['selected_model_id']]
    evaluations=[records[id] for id in r['evaluation_ids']];q=[e for e in evaluations if e['view']['group']=='quantization'];board=next(e for e in evaluations if e['view']['group']=='deployment_snapshot')
    md='# '+r['title']+'\n\n'
    md+='<!-- Generated from release.json, catalog and decision Markdown; edit those sources. -->\n\n'
    md+='固定版本：`'+r['release_id']+'` · 记录日期：'+r['recorded_on']+'\n\n'
    md+='## 采用状态\n\n'
    for key,value in r['statuses'].items():md+='- **'+key+'**：`'+value+'`。'+r['status_notes'][key]+'\n'
    md+='\n## 来源与训练\n\n'
    md+='- 基座：'+base['model']+'，revision `'+base['revision']+'`。\n'
    md+='- 数据：'+str(data['train_samples'])+'条训练 / '+str(data['valid_samples'])+'条已观察开发；数据版本见下方HF固定引用。\n'
    md+='- 方法：LoRA，rank '+str(config['lora_parameters']['rank'])+'，MLX直接scale '+str(config['lora_parameters']['scale'])+'，学习率 '+str(config['learning_rate'])+'。\n'
    md+='- 模块：`'+', '.join(config['lora_parameters']['keys'])+'`；监督目标：'+training['loss_objective']+'。\n'
    actual=training['execution_summary'];md+='- 实际训练：'+str(actual['microsteps'])+'微步 / '+str(actual['optimizer_updates'])+'更新，选定1408微步检查点。\n'
    md+='- 项目训练ID：`'+training['id']+'`；所选制品ID：`'+chosen['id']+'`。\n'
    md+='- 执行代码：依据catalog中的冻结执行记录及measurement_sources，当前工作区HEAD不冒充训练版本。\n'
    md+='\n## 同源量化对照\n\n同一检查点、同50条已观察开发题、Mac llama.cpp；RSS为请求窗口采样。\n\n'
    md+='| 候选 | 工具正确 | 不调用误触发 | 文件MB | Mac峰RSS MiB |\n|---|---:|---:|---:|---:|\n'
    for e in sorted(q,key=lambda x:['f16','q8','q4'].index(x['view']['candidate'])):
        s=e['summary'];md+='| '+e['view']['candidate'].upper()+' | '+str(s['tool_exact'])+'/'+str(s['tool_samples'])+' | '+str(s['no_call_misroutes'])+'/'+str(s['no_call_samples'])+' | '+str(round(e['artifact_summary']['bytes']/1e6,1))+' | '+str(round(e['resources']['sampled_peak_rss_bytes']/1048576,1))+' |\n'
    md+='\n三者开发集单指令均9/10；这不能覆盖取消、不调用和多动作的退步。原质量门槛未过，开发集多次用于选配。\n\n'
    md+='## 能力与限制\n\n'
    md+='已测试：'+'；'.join(r['capabilities']['tested_scope'])+'。\n\n'
    for x in r['capabilities']['known_limitations']:md+='- '+x+'。\n'
    s=board['summary'];md+='\n## 板端历史快照\n\nRK3566既有'+str(s['smoke_cases'])+'条API请求：协议/Registry '+str(s['native_parser_registry_passed'])+'/'+str(s['smoke_cases'])+'，意图 '+str(s['exact_call_plans'])+'/'+str(s['smoke_cases'])+'；峰值PSS '+str(round(s['sampled_peak_pss_mib'],1))+' MiB。不是本次实时验收、完整ROS交互或动作执行。\n\n'
    md+='## 固定制品与数据引用\n\n'
    for name in ['adapter','dataset']:
        h=r['hf_references'][name];md+='- '+name+'：['+h['repo']+']('+h['url']+')，路径 `'+h['prefix']+'`，private='+str(h['private']).lower()+'。\n'
    files=chosen['reference']['artifact']['files'];md+='- 所选Q4：SHA256 `'+files[0]['sha256']+'`；尚未上传HF，不将adapter链接当作GGUF下载地址。旧根文件不自动成为本版制品。\n\n'
    md+='## 采用依据与实验结论\n\n'
    for d in decisions:md+=re.sub(r'^(#{1,4}) ',lambda m:'#'*(len(m.group(1))+2)+' ',d['markdown'],flags=re.M)+'\n结论强度：`'+d['evidence_strength']+'`。\n\n'
    md+='## 后续与恢复\n\n'+r['next_direction']+'\n\n部署恢复步骤引用已有板端部署记录；本次不改变服务或回滚指向。\n'
    if local and (home/'bindings/catalog-mlflow.json').exists():
        binding=json.loads((home/'bindings/catalog-mlflow.json').read_text())['records']
        rid=binding[r['training_id']]['run_id'];v=binding[r['selected_model_id']]['registry']
        md+='\n## MLflow详情（本机）\n\n- [训练参数和Loss](http://127.0.0.1:5001/#/experiments/1/runs/'+rid+'/model-metrics)\n- [所选模型版本](http://127.0.0.1:5001/#/models/'+v['name']+'/versions/'+str(v['version'])+')\n'
    return md


def markdown_html(md):
    lines=md.splitlines();out=[];table=False;details_open=False
    def inline(s):
        s=html.escape(s);s=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s);s=re.sub(r'\[([^]]+)\]\((https?://[^)]+)\)',r'<a href="\2">\1 ↗</a>',s);return re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
    for line in lines:
        if line.startswith('<!--'):continue
        if line.startswith('|'):
            cells=[x.strip() for x in line.strip('|').split('|')]
            if all(re.fullmatch(r'[-: ]+',x) for x in cells):continue
            if not table:out.append('<div class="scroll"><table>');table=True
            out.append('<tr>'+''.join('<td>'+inline(x)+'</td>' for x in cells)+'</tr>');continue
        if table:out.append('</table></div>');table=False
        if line.startswith('#'):
            n=len(line)-len(line.lstrip('#'));title=line[n:].strip()
            if n<=2 and details_open:out.append('</details>');details_open=False
            if n==2 and title in ['来源与训练','固定制品与数据引用','采用依据与实验结论']:
                out.append('<details><summary>'+inline(title)+' · 展开</summary>');details_open=True
            else:out.append(f'<h{min(n,3)}>'+inline(title)+f'</h{min(n,3)}>')
        elif line.strip():out.append('<p>'+inline(line)+'</p>')
    if table:out.append('</table></div>')
    if details_open:out.append('</details>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>小沫 · 固定版本说明</title><style>body{background:#f4f6fa;color:#1c3047;font:15px/1.8 system-ui;margin:0}main{max-width:1020px;margin:24px auto;background:white;padding:30px;border:1px solid #dbe4ef;border-radius:12px}details{border-top:1px solid #e0e8f1;padding:14px 0}summary{cursor:pointer;color:#285e98;font-weight:600}h1{font-size:28px}h2{font-size:20px;border-top:1px solid #e1e8f0;padding-top:18px}a{color:#245fa6}code{overflow-wrap:anywhere;background:#f3f6fa}td{padding:10px;border-bottom:1px solid #e0e8f1}table{border-collapse:collapse;width:100%}.scroll{overflow:auto}p{overflow-wrap:anywhere}@media(max-width:650px){main{padding:16px;margin:8px}}</style><main><p><a href="/">实验比较</a> · <a href="/lineage.html">历史过程树</a></p>'+''.join(out)+'</main></html>'


def generate(home=DEFAULT_HOME):
    r,records,decisions,directory=load_release()
    local=card(r,records,decisions,home=home);(directory/'MODEL_CARD.md').write_text(local)
    view=home/'view';view.mkdir(parents=True,exist_ok=True)
    (view/'release.html').write_text(markdown_html(local))
    (view/'release-preview.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=/release.html"><a href="/release.html">打开固定版本说明</a>')
    staging=home/'review-package'/r['release_id'];(staging/'hf-model').mkdir(parents=True,exist_ok=True);(staging/'hf-dataset').mkdir(exist_ok=True);(staging/'github').mkdir(exist_ok=True)
    (staging/'hf-model/README.md').write_text('---\nbase_model: Qwen/Qwen3-0.6B\ndatasets:\n- Shangyizhou/xiaomo-robotics-data\nlanguage:\n- zh\npipeline_tag: text-generation\n---\n\n'+card(r,records,decisions,local=False))
    (staging/'hf-model/release.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
    h=r['hf_references']['dataset'];training=records[r['training_id']]
    (staging/'hf-dataset/README.md').write_text('# 小沫机器人数据版本\n\n本次仅准备关联说明，不上传或覆盖既有数据。\n\n固定引用：['+h['repo']+']('+h['url']+')，路径 `'+h['prefix']+'`。\n\n235训练 /50已观察开发；同来源指令与称呼近似表达分组，避免跨集泄漏。开发数据反复用于选配，不作独立测试。原195条与审核40条来源、标注规则及许可沿用冻结版本；本次不生成样本、不重新划分或扩大许可。\n\n关联交付记录：`'+r['release_id']+'`。所选Q4未上传；不能从本关联说明推断数据或模型通过验收。\n')
    (staging/'github/RELEASE_NOTES.md').write_text(card(r,records,decisions,local=False))
    manifest={'release_id':r['release_id'],'review_only':True,'uploaded':False,'pushed':False,'files':{str(p.relative_to(staging)):hashlib.sha256(p.read_bytes()).hexdigest() for p in staging.rglob('*') if p.is_file() and p.name!='manifest.json'}}
    (staging/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'release_id':r['release_id'],'model_card':str(directory/'MODEL_CARD.md'),'review_package':str(staging),'remote_publish':False}))
    return r,records,decisions,directory


def sync_mlflow():
    import mlflow
    from mlflow import MlflowClient
    r,records,decisions,directory=generate();mlflow.set_tracking_uri('sqlite:///'+str(DEFAULT_HOME/'mlflow.db'));c=MlflowClient();bindings=json.loads((DEFAULT_HOME/'bindings/catalog-mlflow.json').read_text())['records']
    paths=[directory/'release.json',directory/'MODEL_CARD.md']
    for model in [r['selected_model_id']]+r['reference_model_ids']+r['source_model_ids']:
        b=bindings[model];v=b['registry'];tags={'release_id':r['release_id'],**r['statuses'],'release_document':'releases/'+r['release_id']+'/MODEL_CARD.md','remote_q4_status':'not_published'}
        tags['release_role']='selected_deployment_artifact' if model==r['selected_model_id'] else ('quality_reference' if model in r['reference_model_ids'] else 'source_adapter')
        if model!=r['selected_model_id']:tags['selection_status']='reference_only';tags['deployment_status']='not_claimed'
        previous=c.get_model_version(v['name'],v['version']).tags.get('release_ids','[]')
        tags['release_ids']=json.dumps(sorted(set(json.loads(previous)+[r['release_id']])))
        for k,value in tags.items():c.set_model_version_tag(v['name'],v['version'],k,value)
        c.set_logged_model_tags(b['model_id'],tags)
        marker='\n\n[固定版本总说明](http://127.0.0.1:5002/release.html)\n\n'
        old_description=c.get_model_version(v['name'],v['version']).description or ''
        base_description=old_description.split(marker,1)[1] if old_description.startswith('# '+r['release_id']) and marker in old_description else old_description
        intro=('用户选用Q4，保留质量限制。' if model==r['selected_model_id'] else ('所选训练检查点的来源适配器，不等同于已发布Q4文件。' if model in r['source_model_ids'] else '本交付记录的质量参照，未作为本版部署声明。'))
        prefix='# '+r['release_id']+'\n\n'+intro+marker+base_description
        if prefix!=old_description:c.update_model_version(v['name'],v['version'],description=prefix)
        old_note=c.get_logged_model(b['model_id']).tags.get('mlflow.note.content','')
        base_note=old_note.split(marker,1)[1] if old_note.startswith('# '+r['release_id']) and marker in old_note else old_note
        new_note='# '+r['release_id']+marker+base_note
        if new_note!=old_note:c.set_logged_model_tags(b['model_id'],{'mlflow.note.content':new_note})
    rid=bindings[r['training_id']]['run_id'];c.set_tag(rid,'release_id',r['release_id']);c.set_tag(rid,'release_role','source_training')
    for id in r['evaluation_ids']:
        c.set_tag(bindings[id]['run_id'],'release_id',r['release_id'])
    for path in paths:c.log_artifact(rid,str(path),'release/'+r['release_id'])
    for id in r['decision_ids']:
        for suffix in ['json','md']:c.log_artifact(rid,str(directory/'decisions'/(id+'.'+suffix)),'release/'+r['release_id']+'/decisions')
    selected=bindings[r['selected_model_id']]['registry'];c.set_registered_model_alias(selected['name'],'current-selected',selected['version'])
    c.set_experiment_tag('1','current_release_id',r['release_id'])
    c.set_experiment_tag('1','release_document','http://127.0.0.1:5002/release.html')
    note=c.get_experiment('1').tags.get('mlflow.note.content','')
    if '[当前固定版本总说明]' not in note:
        c.set_experiment_tag('1','mlflow.note.content',note+'\n\n[当前固定版本总说明](http://127.0.0.1:5002/release.html)；参数、曲线与历史过程继续保留。')
    print('MLflow release associations synchronized without creating runs, models or metric points.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sync-mlflow',action='store_true');args=p.parse_args();sync_mlflow() if args.sync_mlflow else generate()
