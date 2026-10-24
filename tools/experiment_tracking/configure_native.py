"""Apply standard display metadata and derived comparison summaries in native MLflow."""
import json
from pathlib import Path
import mlflow
from mlflow import MlflowClient
from import_history import DEFAULT_HOME


def main():
    home=DEFAULT_HOME
    from catalog import load_view
    data=load_view(home)[0]
    mlflow.set_tracking_uri('sqlite:///'+str(home/'mlflow.db'))
    mlflow.set_experiment('edge-ai-qwen-history')
    c=MlflowClient()
    keys=['pilot32','selected9-v1','selected9-v2','selected9-v3','original195','original195-epoch3-warmstart','xiaomo235-3epochs','fit16-diagnostic','contract-smoke','corrected-qv','mlp-scale16','mlp-scale2','continuation8']
    backup=home/'backups/native-standard-metadata.json'
    if not backup.exists():
        backup.write_text(json.dumps({'runs':{r:c.get_run(r).to_dictionary() for r in data['runs'].values()},'models':{m:c.get_logged_model(m).to_dictionary() for m in data['models'].values()}},ensure_ascii=False,default=str))
    for i,key in enumerate(keys,1):
        rid=data['runs']['train:'+key];r=c.get_run(rid)
        c.set_tag(rid,'legacy_display_name',r.data.tags.get('legacy_display_name',r.data.tags['mlflow.runName']))
        c.set_tag(rid,'mlflow.runName',f'sft-{i:03d} · Qwen3-0.6B · LoRA SFT')
        c.set_tag(rid,'run_alias',f'sft-{i:03d}')
        c.set_tag(rid,'comparison_view','training')
        for name,value in {'method':'LoRA SFT','run_alias':f'sft-{i:03d}'}.items():
            if name not in r.data.params:c.log_param(rid,name,value)
        evs=[e for e in data['evaluations'] if e['train_key']==key and e['split']=='observed_development']
        if evs:
            ev=max(evs,key=lambda x:data['checkpoints'][x['model_key']]['step']);q=ev['summary']
            c.set_tag(rid,'summary_evaluation_run_id',data['runs']['eval:'+ev['key']])
            c.set_tag(rid,'summary_checkpoint',ev['model_key'])
            for name,value in {'dev_tool_exact_rate':q['tool_exact']/q['tool_samples'],'dev_false_call_rate':q['no_call_misroutes']/q['no_call_samples'],'summary_microstep':data['checkpoints'][ev['model_key']]['step']}.items():
                c.log_metric(rid,name,value,timestamp=r.info.start_time,step=0)
    for key,mid in data['models'].items():
        m=c.get_logged_model(mid)
        kind='base_weights' if key=='base' else ('lora_adapter' if not key.startswith('export:') else ('merged_weights' if key.endswith(':merged') else 'full_model'))
        precision='F16' if key.endswith(':f16') else 'Q4_K_M' if key.endswith((':q4',':q4_k_m')) else 'Q8_0' if key.endswith(':q8') else 'not_recorded'
        params={'artifact_type':kind,'artifact_format':'GGUF' if precision!='not_recorded' else 'safetensors','weight_precision':'BF16' if key=='base' else precision}
        missing={k:v for k,v in params.items() if k not in m.params}
        assert all(m.params[k]==v for k,v in params.items() if k in m.params)
        if missing:c.log_model_params(mid,missing)
        c.set_logged_model_tags(mid,{'comparison_group':'selected-quantization' if key in ['continuation8:step1408','export:merged','export:f16','export:q4','export:q8'] else 'historical-checkpoints'})
    description='''# Qwen 实验记录

[训练参数比较](http://127.0.0.1:5001/#/experiments/1?searchFilter=tags.comparison_view%20%3D%20%27training%27&compareRunsMode=TABLE) · [模型与成绩](http://127.0.0.1:5001/#/experiments/1/models) · [全部模型](http://127.0.0.1:5001/#/experiments/1/models?allModels=1) · [完整过程树](http://127.0.0.1:5001/#/experiments/1?view=process&searchFilter=&orderByKey=attributes.start_time&orderByAsc=false&startTime=ALL&lifecycleFilter=Active&modelVersionFilter=All%20Runs&datasetsFilter=W10%3D)

训练视图每行一次训练。参数独立列出，dev_tool_exact_rate / dev_false_call_rate 是最新已有开发检查点评分的派生摘要（0–1），不是新评测。summary_checkpoint 与 summary_evaluation_run_id 指向来源。Loss 曲线在训练详情的 Model metrics。

模型条目为外部权重引用；READY不等于质量达标。历史导入时间不是原实验时间。未重新训练、推理或判分。'''
    if (Path(__file__).resolve().parents[2]/'studies/voice-interaction/releases/current.json').exists():
        description += '\n\n[当前固定版本总说明](http://127.0.0.1:5002/release.html)；原始报告保留在历史入口。'
    c.set_experiment_tag('1','mlflow.note.content',description)
    (home/'native-standard-configuration.json').write_text(json.dumps({'training_runs_updated':len(keys),'model_reference_fields':len(data['models']),'no_training_or_inference':True,'original_ids_preserved':True},indent=2))
    print('Native metadata configured; original run/model IDs preserved.')

if __name__=='__main__':main()
