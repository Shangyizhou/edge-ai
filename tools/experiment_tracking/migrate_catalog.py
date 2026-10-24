"""One-way, allowlisted history migration into stable catalog metadata. No model execution."""
import hashlib
import json
from pathlib import Path
from catalog import ROOT, DEFAULT_HOME, CATALOG, REPORTS, stable_id, read_index


def migrate(home=DEFAULT_HOME, target=CATALOG):
    legacy=json.loads((home/'lineage-import.json').read_text());quant=json.loads((home/'view/data.json').read_text())
    records={};bindings={'schema':'edge-ai/catalog-bindings-v1','experiment_id':quant['experiment_id'],'records':{}}
    def add(r, binding=None):
        if r['id'] in records:
            assert records[r['id']]==r,'Conflicting record '+r['id']
        records[r['id']]=r
        if binding:bindings['records'][r['id']]=binding
        return r['id']
    def source(path):
        p=Path(path);blob=p.read_bytes()
        try:loc={'path':p.relative_to(ROOT).as_posix()}
        except ValueError:loc={'external_path':str(p)}
        return {**loc,'sha256':hashlib.sha256(blob).hexdigest()}
    def load(path):
        p=Path(path);blob=p.read_bytes();assert hashlib.sha256(blob).hexdigest()==legacy['sources'][str(p)]
        return json.loads(blob)
    def dataset(digest,n):
        return add({'schema':'edge-ai/catalog-record-v1','id':'dataset-sha256-'+digest,'kind':'dataset','origin_key':digest,'digest':digest,'sample_count':n,'content_policy':'reference only; original dataset retained; no sealed test input'})
    facts={};result_sources={}
    for path in legacy['sources']:
        if path.endswith('/results.json'):
            r=load(path)
            if r.get('schema')=='edge-model-finetune/result-v1':
                facts[r['config']['adapter_path']]=r;result_sources[r['config']['adapter_path']]=source(path)
    train_ids={};model_ids={}
    for key in legacy['training_keys']:
        cfg=legacy['training_configs'][key];r=facts[cfg['config']['adapter_path']];id=stable_id('training',key);train_ids[key]=id
        ids=[dataset(r['dataset'][k+'_sha256'],r['dataset'][k+'_samples']) for k in ['train','valid']]
        add({'schema':'edge-ai/catalog-record-v1','id':id,'kind':'training','origin_key':key,'display_alias':'sft-'+str(legacy['training_keys'].index(key)+1).zfill(3),'configuration':cfg['config'],'dataset_summary':cfg['dataset'],'dataset_ids':ids,'parent_ids':[],'loss_objective':cfg['loss_id'],'execution_summary':{k:r.get(k) for k in ['microsteps','optimizer_updates','training_wall_seconds','base_artifact','status']},'evidence':[result_sources[cfg['config']['adapter_path']]],'publication':'private'}, {'run_id':legacy['runs']['train:'+key]})
    # Each model identity comes from its frozen artifact-reference manifest, not the registry version.
    for key,mid in legacy['models'].items():
        binding={'model_id':mid,'registry':legacy['versions'][key]}
        refs=list((home/'artifacts/models'/mid/'artifacts').glob('artifact-reference.json'))
        assert len(refs)==1
        ref=json.loads(refs[0].read_text());semantic={k:v for k,v in ref.items() if k not in ['train_run_id','parent_model_ids','training_parameters','hf']}
        if key=='base':identity=ref['model']+'@'+ref['revision'];kind='base_weights'
        elif key in legacy['checkpoints']:identity=ref['sha256'];kind='lora_adapter'
        else:identity=json.dumps(ref['artifact']['files'],sort_keys=True);kind='merged_weights' if key.endswith(':merged') else 'full_model'
        model_ids[key]=stable_id('model',identity)
        if key in legacy['checkpoints']:
            cp=legacy['checkpoints'][key];semantic={k:cp[k] for k in ['step','sha256','bytes','path','epoch']}
        add({'schema':'edge-ai/catalog-record-v1','id':model_ids[key],'kind':'model','origin_key':key,'artifact_type':kind,'identity':identity,'reference':semantic,'parent_ids':[],'training_ids':[],'checkpoint':semantic if kind=='lora_adapter' else None,'publication':'private'},binding)
    for key,id in model_ids.items():
        r=records[id]
        if key=='base':continue
        if key in legacy['checkpoints']:
            train=key.split(':step')[0];r['training_ids']=[train_ids[train]]
            warm=records[train_ids[train]]['configuration'].get('resume_adapter_file')
            r['parent_ids']=[next((model_ids[k] for k,v in legacy['checkpoints'].items() if v['path']==warm),model_ids['base'])]
        elif key.startswith('export:'):
            parts=key.split(':');train='continuation8' if len(parts)==2 else parts[1];out=parts[-1]
            prefix='export:' if len(parts)==2 else 'export:'+train+':'
            if out=='merged':r['parent_ids']=[model_ids['base'],model_ids[next(k for k in legacy['checkpoints'] if k.startswith(train+':') and legacy['checkpoints'][k]['step']==max(c['step'] for k2,c in legacy['checkpoints'].items() if k2.startswith(train+':')))]]
            elif out=='f16':r['parent_ids']=[model_ids[prefix+'merged'],model_ids['base']]
            else:r['parent_ids']=[model_ids[prefix+'f16']]
            r['training_ids']=[train_ids[train]]
    for key,id in train_ids.items():
        warm=records[id]['configuration'].get('resume_adapter_file')
        records[id]['parent_ids']=[next((model_ids[k] for k,v in legacy['checkpoints'].items() if v['path']==warm),model_ids['base'])]
    for e in legacy['evaluations']:
        id=stable_id('evaluation',e['key']);path=Path(e['source']);cases=path.parent/'scored-cases.json'
        ds=dataset(e['digest'],e['summary']['samples'])
        r={'schema':'edge-ai/catalog-record-v1','id':id,'kind':'evaluation','origin_key':e['key'],'model_ids':[model_ids[e['model_key']]],'training_ids':[train_ids[e['train_key']]] if e['train_key'] else [],'dataset_ids':[ds],'split':e['split'],'summary':e['summary'],'resources':{},'evidence':[source(path)],'cases_source':source(cases) if str(cases) in legacy['sources'] else None,'view':{'group':'checkpoint'},'publication':'private'}
        add(r,{'run_id':legacy['runs']['eval:'+e['key']]})
    for item in quant['comparison']:
        candidate=item['candidate'];key='quant:'+candidate;path=ROOT/'studies/voice-interaction/experiments/mac/2026-10-24-qwen235-q4-v1/evaluations'/candidate
        ds=dataset(legacy['training_configs']['continuation8']['dataset']['valid_sha256'],50)
        add({'schema':'edge-ai/catalog-record-v1','id':stable_id('evaluation',key),'kind':'evaluation','origin_key':key,'model_ids':[model_ids['continuation8:step1408' if candidate=='adapter' else 'export:'+candidate]],'training_ids':[train_ids['continuation8']],'dataset_ids':[ds],'split':'observed_development','summary':item['quality'],'resources':item['resources'],'artifact_summary':item['artifact'],'cases_source':source(path/'scored-cases.json'),'evidence':[source(path/'summary.json')],'view':{'group':'quantization','candidate':candidate},'publication':'private'},{'run_id':quant['runs'][candidate]})
    stop_path=ROOT/'studies/voice-interaction/experiments/mac/2026-10-23-qwen235-decision8-v1/user-stop.json'
    stop=load(stop_path)
    request_path=Path.home()/'.local/share/edge-ai/qwen235-decision8-v1/training/request.json'
    request=load(request_path)
    add({'schema':'edge-ai/catalog-record-v1','id':stable_id('training','decision8-stopped'),'kind':'training','origin_key':'decision8-stopped','display_alias':None,'configuration':request['train_config'],'dataset_summary':{},'dataset_ids':[],'parent_ids':[model_ids['base']],'loss_objective':'decision8','execution_summary':{'status':'USER_STOPPED','microsteps':stop['last_completed_microstep'],'optimizer_updates':stop['actual_updates']},'evidence':[source(stop_path),source(request_path)],'publication':'private'}, {'run_id':legacy['runs']['train:decision8-stopped']})
    board_path=ROOT/'studies/voice-interaction/experiments/rk3566/2026-10-24-xiaomo235-q4-deployment-v1/summary.json'
    board=load(board_path)
    add({'schema':'edge-ai/catalog-record-v1','id':stable_id('evaluation','deployment:q4-snapshot'),'kind':'evaluation','origin_key':'deployment:q4-snapshot','model_ids':[model_ids['export:q4']],'training_ids':[train_ids['continuation8']],'dataset_ids':[],'split':'historical_board_smoke','summary':board,'resources':{},'evidence':[source(board_path)],'view':{'group':'deployment_snapshot'},'publication':'private'}, {'run_id':legacy['runs']['deployment:q4-snapshot']})
    bindings['auxiliary_runs']={k:v for k,v in legacy['runs'].items() if not k.startswith(('train:','eval:'))}
    bindings['auxiliary_runs']['train:decision8-stopped']=legacy['runs']['train:decision8-stopped']
    # Canonical report source: selected decision, not a duplicate of execution reports.
    phase={'schema':'edge-ai/phase-report-v1','id':'xiaomo-qwen-selection-2026-10-24','title':'小沫 Qwen：所选检查点与量化取舍','publication':'private','selected_model_id':model_ids['export:q4'],'reference_model_ids':[model_ids['export:f16'],model_ids['export:q8']],'training_ids':[train_ids['continuation8']],'evaluation_ids':[stable_id('evaluation','quant:'+c) for c in ['f16','q8','q4']],'decision':'用户选择Q4；保留质量损失说明，不代表通过原质量门槛。','historical_report':'experiments/mac/2026-10-24-qwen235-q4-v1/report.html','generation_policy':'generate offline summary from catalog; public release requires separate review'}
    target.mkdir(parents=True,exist_ok=True);entries=[]
    sub={'dataset':'datasets','training':'training-runs','model':'model-artifacts','evaluation':'evaluations'}
    for id,r in sorted(records.items()):
        rel=Path(sub[r['kind']])/(id+'.json');p=target/rel;p.parent.mkdir(exist_ok=True);blob=json.dumps(r,ensure_ascii=False,indent=2)+'\n'
        if p.exists() and p.read_text()!=blob:raise ValueError('Catalog conflict; preserve record before revision: '+str(p))
        p.write_text(blob);entries.append({'id':id,'kind':r['kind'],'path':rel.as_posix(),'sha256':hashlib.sha256(blob.encode()).hexdigest()})
    context=source(ROOT/'studies/voice-interaction/experiments/mac/2026-10-24-qwen235-q4-v1/inputs/validation.jsonl')
    index={'schema':'edge-ai/catalog-index-v1','publication':'private','records':entries,'view_context_source':context,'scope':'existing imported Qwen evidence; ASR/TTS, sealed final suites and unlisted experiments not ingested','source_snapshot_hashes':legacy['sources']}
    (target/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
    (home/'bindings').mkdir(exist_ok=True);(home/'bindings/catalog-mlflow.json').write_text(json.dumps(bindings,ensure_ascii=False,indent=2))
    report_dir=REPORTS/phase['id'];report_dir.mkdir(parents=True,exist_ok=True);
    if not (report_dir/'report.json').exists():
        (report_dir/'report.json').write_text(json.dumps(phase,ensure_ascii=False,indent=2)+'\n')
    read_index(target)
    print(json.dumps({'records':len(records),'by_kind':{kind:sum(r['kind']==kind for r in records.values()) for kind in sub},'bindings_outside_git':True,'no_source_moves_or_deletions':True}))

if __name__=='__main__':migrate()
