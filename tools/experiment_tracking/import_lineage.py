"""Build model lineage from explicitly allowlisted historical metadata. No model execution."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from import_history import ROOT, SOURCE, DEFAULT_HOME

MAC = ROOT / 'studies/voice-interaction/experiments/mac'
# Order matters only for the explicitly documented warm-start relationship.
TRAININGS = [
    ('pilot32', '2026-10-22-qwen-lora-export-pilot-v1', 'training'),
    ('selected9-v1', '2026-10-22-qwen-selected9-adaptation-v1', 'training'),
    ('selected9-v2', '2026-10-22-qwen-selected9-adaptation-v1', 'training-v2'),
    ('selected9-v3', '2026-10-22-qwen-selected9-adaptation-v1', 'training-selected'),
    ('original195', '2026-10-23-xiaomo300-cycle-v1', 'training/formal'),
    ('original195-epoch3-warmstart', '2026-10-23-xiaomo300-epoch3-v1', 'training'),
    ('xiaomo235-3epochs', '2026-10-23-xiaomo235-train-v1', 'training/formal'),
    ('fit16-diagnostic', '2026-10-23-qwen-fit16-v1', 'training'),
    ('contract-smoke', '2026-10-23-qwen-training-contract-smoke-v1', 'training'),
    ('corrected-qv', '2026-10-23-qwen235-corrected-v1', 'training'),
    ('mlp-scale16', '2026-10-23-qwen235-mlp-v1', 'training'),
    ('mlp-scale2', '2026-10-23-qwen235-mlp-scale2-v1', 'training'),
    ('continuation8', '2026-10-23-qwen235-continuation8-v1', 'training'),
]


class Sources:
    def __init__(self):
        self.hashes = {}

    def read(self, path):
        path = Path(path)
        blob = path.read_bytes()
        self.hashes[str(path)] = hashlib.sha256(blob).hexdigest()
        return json.loads(blob)

    def unchanged(self):
        return all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in self.hashes.items())


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def normalize():
    src = Sources()
    trainings = []
    evaluations = []
    for key, dirname, subdir in TRAININGS:
        p = MAC / dirname
        result = src.read(p / subdir / 'results.json')
        request = src.read(p / subdir / 'request.json')
        assert result['status'] == 'completed', key
        assert src.hashes[str(p / subdir / 'request.json')] == result['request_sha256'], key
        ledger = src.read(p / 'checkpoint-ledger.json') if (p / 'checkpoint-ledger.json').exists() else []
        checkpoints = []
        for entry in result['adapter']['files']:
            match = re.fullmatch(r'(\d+)_adapters.safetensors', entry['name'])
            if not match:
                continue
            step = int(match[1])
            rows = [r for r in ledger if r.get('step', r.get('microstep')) == step]
            if rows:
                assert rows[0].get('sha256', rows[0].get('adapter_sha256')) == entry['sha256']
            cp = {'key': key + ':step' + str(step), 'step': step, 'sha256': entry['sha256'], 'bytes': entry['bytes'], 'path': str(Path(result['adapter']['root']) / entry['name']), 'epoch': rows[0].get('epoch') if rows else None}
            checkpoints.append(cp)
            dirs = [(p / f'step{step}' / split, split) for split in ('validation', 'replay')]
            if key == 'original195':
                dirs += [(p / f'validation-step{step:04d}', 'validation')]
            if key == 'original195-epoch3-warmstart':
                dirs += [(p / 'validation', 'validation')]
            if key == 'xiaomo235-3epochs':
                dirs += [(p / f"epoch{cp['epoch']}", 'validation')]
            for folder, split in dirs:
                if (folder / 'summary.json').exists():
                    summary = src.read(folder / 'summary.json')
                    records = src.read(folder / 'scored-cases.json') if (folder / 'scored-cases.json').exists() else None
                    if records is not None:
                        assert len(records) == summary['samples'] and len({r['id'] for r in records}) == len(records)
                        assert sum(r['pass'] for r in records if r['expected']) == summary['tool_exact']
                    evaluations.append({'key': cp['key'] + ':' + split, 'model_key': cp['key'], 'train_key': key, 'split': 'seen_train_replay' if split == 'replay' else 'observed_development', 'summary': summary, 'cases': records, 'source': str(folder / 'summary.json'), 'digest': result['dataset']['train_sha256' if split == 'replay' else 'valid_sha256']})
        objective = result.get('loss_objective', {})
        loss_id = 'continuation8' if key == 'continuation8' else ('real-target-token-mean' if result.get('training_impl', '').startswith('project-v2') else 'legacy-padding-inclusive')
        trainings.append({'key': key, 'request': request, 'result': result, 'checkpoints': checkpoints, 'loss_id': loss_id, 'objective': objective, 'source': str(p / subdir / 'results.json')})
    # An existing base evaluation, not a new baseline run.
    baseline = MAC / '2026-10-23-xiaomo300-cycle-v1/baseline/summary.json'
    if baseline.exists():
        evaluations.append({'key': 'base:original195-baseline', 'model_key': 'base', 'train_key': None, 'split': 'observed_development', 'summary': src.read(baseline), 'cases': None, 'source': str(baseline), 'digest': next(t for t in trainings if t['key'] == 'original195')['result']['dataset']['valid_sha256']})
    replay = MAC / '2026-10-23-xiaomo235-train-replay-v1/replay'
    if (replay / 'summary.json').exists():
        evaluations.append({'key': 'xiaomo235-3epochs:step696:replay', 'model_key': 'xiaomo235-3epochs:step696', 'train_key': 'xiaomo235-3epochs', 'split': 'seen_train_replay', 'summary': src.read(replay / 'summary.json'), 'cases': src.read(replay / 'scored-cases.json'), 'source': str(replay / 'summary.json'), 'digest': next(t for t in trainings if t['key'] == 'xiaomo235-3epochs')['result']['dataset']['train_sha256']})
    stop_path = MAC / '2026-10-23-qwen235-decision8-v1/user-stop.json'
    stopped = {'stop': src.read(stop_path), 'request': src.read(Path.home() / '.local/share/edge-ai/qwen235-decision8-v1/training/request.json')}
    exports = [src.read(SOURCE / f / 'results.json') for f in ('export', 'export-q8')]
    for train_key, dirname in [('pilot32','2026-10-22-qwen-lora-export-pilot-v1'), ('selected9-v3','2026-10-22-qwen-selected9-adaptation-v1')]:
        legacy = src.read(MAC / dirname / 'export/results.json')
        legacy['lineage_train_key'] = train_key
        exports.append(legacy)
    deployment = src.read(ROOT / 'studies/voice-interaction/experiments/rk3566/2026-10-24-xiaomo235-q4-deployment-v1/summary.json')
    release = src.read(ROOT / 'studies/voice-interaction/research/2026-10-24-qwen235-artifact-release/release-summary.json')
    old_import = json.loads((DEFAULT_HOME / 'import-verification.json').read_text())
    assert all(t['result']['base_artifact']['revision'] == trainings[0]['result']['base_artifact']['revision'] for t in trainings)
    return src, trainings, evaluations, stopped, exports, release, old_import, deployment


class Importer:
    def __init__(self, home, eid):
        from mlflow import MlflowClient
        self.client = MlflowClient()
        self.eid = eid
        self.home = home
        self.runs = {}
        self.models = {}
        self.versions = {}

    def run(self, key, name, payload, kind, parent=None, params=None, metrics=None, tags=None, status='FINISHED'):
        c = self.client
        origin = 'lineage-v1:' + key
        digest = fingerprint(payload)
        existing = c.search_runs([self.eid], filter_string=f"tags.origin_id = '{origin}'")
        if existing:
            assert len(existing) == 1 and existing[0].data.tags['source_digest'] == digest, 'source conflict ' + key
            run = existing[0]
        else:
            run = c.create_run(self.eid, tags={'mlflow.runName': name, 'origin_id': origin, 'source_digest': digest, 'record_kind': kind, 'execution_time': 'UI timestamps/duration are import time, not historical execution', **({'mlflow.parentRunId': parent} if parent else {}), **(tags or {})})
        rid = run.info.run_id
        self.runs[key] = rid
        if run.data.tags.get('lineage_import_complete') != 'true':
            for k, v in (params or {}).items():
                if v is not None:
                    c.log_param(rid, k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v))
            for k, v in (metrics or {}).items():
                if isinstance(v, (float, int)):
                    c.log_metric(rid, k, v, timestamp=run.info.start_time, step=0)
            c.log_dict(rid, payload, 'lineage-record.json')
        return rid

    def input_models(self, rid, model_ids):
        from mlflow.entities import LoggedModelInput
        inputs = self.client.get_run(rid).inputs
        existing = {m.model_id for m in inputs.model_inputs} if inputs else set()
        missing = [LoggedModelInput(mid) for mid in dict.fromkeys(model_ids) if mid not in existing]
        if missing:
            self.client.log_inputs(rid, models=missing)

    def complete(self, rid, status='FINISHED'):
        self.client.set_tag(rid, 'lineage_import_complete', 'true')
        self.client.set_terminated(rid, status=status)

    def model(self, key, name, rid, reference, parent_models=None, params=None, kind='adapter', step=0):
        from mlflow.entities import LoggedModelOutput
        c = self.client
        digest = fingerprint(reference)
        models = c.search_logged_models([self.eid], filter_string=f"tags.lineage_key = '{key}'")
        if models:
            assert len(models) == 1 and models[0].tags['reference_digest'] == digest, 'model conflict ' + key
            model = models[0]
        else:
            model = c.create_logged_model(self.eid, name=name.replace('.', '_'), source_run_id=rid, model_type='external-' + kind + '-reference', tags={'lineage_key': key, 'reference_digest': digest, 'reference_only': 'true', 'loadable_mlflow_flavor': 'false', 'parent_model_ids': json.dumps(parent_models or []), 'quality_status': 'not_implied_by_READY', 'sha256': reference.get('sha256', 'see manifest')}, params={k: str(v) for k,v in (params or {}).items() if v is not None})
        desired = {k:str(v) for k,v in (params or {}).items() if v is not None}
        assert all(model.params[k] == v for k,v in desired.items() if k in model.params), 'Model parameter conflict '+key
        missing = {k:v for k,v in desired.items() if k not in model.params}
        if missing:
            c.log_model_params(model.model_id, missing)
        self.models[key] = model.model_id
        outputs = c.get_run(rid).outputs
        if not outputs or not any(o.model_id == model.model_id for o in outputs.model_outputs):
            c.log_outputs(rid, [LoggedModelOutput(model.model_id, step)])
        # Store an honest external-artifact reference, not a fake runnable MLmodel.
        artifact_path = 'model-references/' + model.model_id
        c.log_dict(rid, reference, artifact_path + '/artifact-reference.json')
        from urllib.parse import urlparse, unquote
        location = urlparse(model.artifact_location)
        assert location.scheme == 'file', 'Only local artifact storage supported'
        directory = Path(unquote(location.path)).resolve()
        assert directory.is_relative_to((self.home / 'artifacts').resolve())
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'artifact-reference.json').write_text(json.dumps(reference,ensure_ascii=False,indent=2))
        c.finalize_logged_model(model.model_id, 'READY')
        family = 'Qwen3-0.6B-base-reference' if kind == 'base' else 'xiaomo-Qwen3-0.6B-artifact-references'
        registered = [x for x in c.search_registered_models() if x.name == family]
        if not registered:
            c.create_registered_model(family, description='External weight metadata references only; not loadable with mlflow.pyfunc. READY means metadata indexed, not quality accepted.', tags={'reference_only':'true'})
        versions = [v for v in c.search_model_versions(f"name = '{family}'") if v.tags.get('lineage_key') == key]
        if versions:
            assert len(versions) == 1 and versions[0].tags['reference_digest'] == digest
            version = versions[0]
        else:
            version = c.create_model_version(family, f'runs:/{rid}/{artifact_path}', run_id=rid, model_id=model.model_id, tags={'lineage_key': key, 'reference_digest': digest, 'reference_only': 'true', 'format':kind, 'display_name':name}, description=json.dumps(reference, ensure_ascii=False))
        description = '# '+name+'\n\nExternal weight reference only; not a loadable MLflow flavor. READY means metadata indexed, not quality passed.\n\n[Open lineage overview](http://127.0.0.1:5002/lineage.html)\n\n[Source run](http://127.0.0.1:5001/#/experiments/'+str(self.eid)+'/runs/'+rid+')\n\n'
        for parent_id in parent_models or []:
            parent_key = next(k for k,v in self.models.items() if v==parent_id)
            pv = self.versions[parent_key]
            description += '- Parent: ['+parent_key+'](http://127.0.0.1:5001/#/models/'+pv['name']+'/versions/'+str(pv['version'])+')\n'
        description += '\nFull frozen artifact manifest is in the source run under model-references/'+model.model_id+'/artifact-reference.json.'
        c.update_model_version(family, version.version, description=description)
        c.set_logged_model_tags(model.model_id, {'mlflow.note.content':description, 'mlflow.model.isExternal':'true', 'mlflow.modelVersions':json.dumps([{'name':family,'version':version.version}])})
        self.versions[key] = {'name': family, 'version': version.version}
        return model.model_id

    def attach_metrics(self, rid, model_id, values, dataset_name=None, dataset_digest=None, step=0):
        c = self.client
        stamp = c.get_run(rid).info.start_time
        for key, value in values.items():
            if isinstance(value, (int,float)):
                # Reuse a preexisting metric timestamp/step when enriching imported evaluation runs.
                history = c.get_metric_history(rid, key)
                match = next((m for m in history if m.value == value), None)
                c.log_metric(rid, key, value, timestamp=match.timestamp if match else stamp, step=match.step if match else step, model_id=model_id, dataset_name=dataset_name, dataset_digest=dataset_digest)
        c.set_tag(rid, 'evaluated_model_id', model_id)


def score_metrics(q):
    return {k: q[k] for k in ('samples','tool_samples','no_call_samples','tool_exact','format','no_call_misroutes','text_semantic','overall') if isinstance(q.get(k), (int,float))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    src, trainings, evaluations, stopped, exports, release, old, deployment = normalize()
    if args.dry_run:
        print(json.dumps({'training_runs':len(trainings), 'checkpoints':sum(len(t['checkpoints']) for t in trainings), 'evaluations':len(evaluations), 'sources':len(src.hashes), 'stopped_runs':1}))
        return
    import mlflow
    mlflow.set_tracking_uri('sqlite:///' + str(DEFAULT_HOME / 'mlflow.db'))
    mlflow.set_experiment('edge-ai-qwen-history')
    imp = Importer(DEFAULT_HOME, old['experiment_id'])
    c = imp.client
    base = trainings[0]['result']['base_artifact']
    rid = imp.run('base', 'BASE · Qwen3-0.6B @c1899de', base, 'base_reference', params={'base_model':base['model'],'base_revision':base['revision']})
    base_id = imp.model('base', 'Qwen3-0.6B-original-BF16', rid, base, kind='base', params={'revision':base['revision']})
    imp.complete(rid)
    checkpoint_records = {}
    for t in trainings:
        key, result = t['key'], t['result']
        cfg = result['config']; lora = cfg['lora_parameters']; data = result['dataset']
        warm = cfg.get('resume_adapter_file')
        parent_model = next((checkpoint_records[k]['model_id'] for k in checkpoint_records if checkpoint_records[k]['path'] == warm), base_id)
        assert not warm or parent_model != base_id, 'Unresolved warm-start source ' + str(warm)
        params = {'base_model':base['model'],'base_revision':base['revision'],'train_sha256':data['train_sha256'],'valid_sha256':data['valid_sha256'],'train_samples':data['train_samples'],'valid_samples':data['valid_samples'],'loss_objective':t['loss_id'],'rank':lora['rank'],'mlx_direct_scale':lora['scale'],'lora_modules':lora['keys'],'continuation_weight':cfg.get('continuation_weight',1),'learning_rate':cfg['learning_rate'],'num_layers':cfg['num_layers'],'batch_size':cfg['batch_size'],'grad_accumulation_steps':cfg.get('grad_accumulation_steps'),'seed':cfg.get('seed'),'max_seq_length':cfg.get('max_seq_length'),'resume_adapter_file':warm or 'none','optimizer_state': 'reset on warm-start' if warm else 'fresh', 'training_impl':result.get('training_impl','historical upstream')}
        train_rid = imp.run('train:'+key, 'TRAIN · '+key, {'request':t['request'],'result':result}, 'historical_training', parent=imp.runs['base'], params=params, metrics={k:result[k] for k in ('microsteps','optimizer_updates','training_wall_seconds','trainable_parameters') if k in result}, tags={'base_model_id':base_id,'input_model_id':parent_model,'loss_objective':t['loss_id'],'lineage_browser':'http://127.0.0.1:5002/lineage.html'})
        imp.input_models(train_rid, [parent_model])
        pending = c.get_run(train_rid).data.tags.get('lineage_import_complete') != 'true'
        if pending:
            for event in result['metrics']:
                up = event.get('upstream',{})
                step = up.get('completed_microsteps', event.get('microstep'))
                if not isinstance(step,int):
                    continue
                for metric in ('train_loss','val_loss'):
                    if isinstance(up.get(metric),(int,float)):
                        name = ('train_loss__'+t['loss_id'] if metric=='train_loss' else ('validation_loss_real_token' if t['loss_id']!='legacy-padding-inclusive' else 'legacy_validation_loss_preupdate'))
                        c.log_metric(train_rid,name,up[metric],timestamp=c.get_run(train_rid).info.start_time,step=step)
        for cp in t['checkpoints']:
            parents = [parent_model]
            ref = {**cp, 'base_revision':base['revision'], 'train_run_id':train_rid, 'training_parameters':params,'source_evidence':t['source'],'availability':'historical manifest; no weight reload performed'}
            if key == 'continuation8' and cp['step']==1408:
                ref['hf']={'repo':'Shangyizhou/xiaomo-qwen3-0.6b','revision':'10109cc14697a2dd2968676855350f5dc2ea0862','path':'releases/xiaomo235-cont8-e6-v1/adapter/adapters.safetensors'}
            mid = imp.model(cp['key'], key+'-step'+str(cp['step']),train_rid,ref,parents,params={'microstep':cp['step'],'recorded_epoch':cp['epoch'],**params}, step=cp['step'])
            checkpoint_records[cp['key']]={**cp,'model_id':mid,'train_run_id':train_rid}
        imp.complete(train_rid)
    # Stopped run has no fabricated checkpoint or quality score.
    cfg = stopped['request']['train_config']; stop = stopped['stop']
    sr = imp.run('train:decision8-stopped','TRAIN · decision8 · USER STOPPED',stopped,'historical_training',parent=imp.runs['base'],params={'rank':cfg['lora_parameters']['rank'],'mlx_direct_scale':cfg['lora_parameters']['scale'],'learning_rate':cfg['learning_rate'],'loss_objective':'decision8','base_revision':base['revision']},metrics={'microsteps':stop['last_completed_microstep'],'optimizer_updates':stop['actual_updates']},tags={'base_model_id':base_id,'no_final_checkpoint':'true'})
    imp.input_models(sr, [base_id])
    imp.complete(sr,'KILLED')
    for e in evaluations:
        model_id = base_id if e['model_key']=='base' else checkpoint_records[e['model_key']]['model_id']
        parent = imp.runs['base'] if e['train_key'] is None else imp.runs['train:'+e['train_key']]
        er = imp.run('eval:'+e['key'],'EVAL · '+e['key'],e,'historical_evaluation',parent=parent,params={'split':e['split'],'dataset_sha256':e['digest'],'samples':e['summary']['samples']},tags={'quality_gate':'not_claimed','split':e['split'],'device':'Mac','evaluated_model_id':model_id})
        imp.input_models(er, [model_id])
        imp.attach_metrics(er,model_id,score_metrics(e['summary']),e['split'],e['digest'])
        imp.complete(er)
    # Export the already-selected checkpoint's lineage, without executing conversion commands.
    selected = checkpoint_records['continuation8:step1408']['model_id']
    export_models = {'adapter': selected, 'base':base_id}
    selected_sha = checkpoint_records['continuation8:step1408']['sha256']
    assert next(f['sha256'] for f in exports[0]['artifacts']['adapter']['files'] if f['name']=='adapters.safetensors') == selected_sha
    export_runs = {}
    for index, export in enumerate(exports):
        train_key = export.get('lineage_train_key', 'continuation8')
        legacy = index >= 2
        local_models = export_models if not legacy else {'base':base_id}
        if legacy:
            digest = next(f['sha256'] for f in export['artifacts']['adapter']['files'] if f['name']=='adapters.safetensors')
            cp_key = next(k for k,v in checkpoint_records.items() if k.startswith(train_key+':') and v['sha256']==digest)
            local_models['adapter'] = checkpoint_records[cp_key]['model_id']
        else:
            digest = selected_sha
        xr = imp.run('export:'+str(index),'EXPORT · '+train_key+' · '+('F16-to-Q8' if index==1 else 'merge-F16-Q4'),export,'historical_export',parent=imp.runs['train:'+train_key],params={'source_checkpoint_sha256':digest})
        for stage in export['stages']:
            out = stage['output_id']; manifest = export['artifacts'][out]
            parent_ids=[local_models[k] for k in stage['inputs']]
            imp.input_models(xr, parent_ids)
            ref={'artifact':manifest,'stage':stage,'parent_model_ids':parent_ids,'remote_availability':'not_checked' if legacy else 'not_published','source_checkpoint_sha256':digest}
            model_key = 'export:'+train_key+':'+out if legacy else 'export:'+out
            mid=imp.model(model_key,train_key+'-'+out.upper(),xr,ref,parent_ids,kind=out,params={'precision':out,'base_revision':base['revision'],'training_run_id':imp.runs['train:'+train_key]})
            local_models[out]=mid
            if not legacy:
                export_runs[out]=xr
        imp.complete(xr)
    # Enrich the original five evaluation runs in place, preserving their IDs and points.
    for candidate, er in old['runs'].items():
        mid = export_models[candidate]
        for k,v in {'evaluated_model_id':mid,'base_model_id':base_id,'training_run_id':imp.runs['train:continuation8'],'checkpoint_microstep':'1408','precision':candidate,'mlflow.parentRunId':imp.runs['train:continuation8'] if candidate=='adapter' else export_runs[candidate]}.items():
            c.set_tag(er,k,v)
        imp.input_models(er, [mid])
        original=c.get_run(er)
        imp.attach_metrics(er,mid,{**original.data.metrics, 'tool_exact':original.data.metrics['tool_correct'], 'format':original.data.metrics['format_correct'], 'overall':original.data.metrics['overall_correct']},'observed_development50',trainings[-1]['result']['dataset']['valid_sha256'])
    assert deployment['model_sha256'] == exports[0]['artifacts']['q4']['files'][0]['sha256']
    dr = imp.run('deployment:q4-snapshot', 'SNAPSHOT · RK3566 Q4 · historical 3 cases', deployment, 'historical_deployment_snapshot', parent=imp.runs['export:0'], params={'device':'RK3566','model_sha256':deployment['model_sha256'],'scope':'model API and pure Registry validation; not ROS acceptance'}, tags={'device':'RK3566','snapshot_only':'true','evaluated_model_id':export_models['q4']})
    imp.input_models(dr, [export_models['q4']])
    imp.attach_metrics(dr,export_models['q4'],{k:deployment[k] for k in ['smoke_cases','exact_call_plans','native_parser_registry_passed','sampled_peak_pss_mib','sampled_peak_rss_mib']})
    imp.complete(dr)
    # Registry aliases describe the user's historical selection, never quality acceptance or live deployment.
    version=imp.versions['continuation8:step1408'];c.set_registered_model_alias(version['name'],'user-selected-adapter',version['version'])
    version=imp.versions['export:q4'];c.set_registered_model_alias(version['name'],'user-selected-q4',version['version'])
    for t in trainings:
        key = t['key']
        rows = [cp for cp in checkpoint_records.values() if cp['key'].startswith(key+':')]
        note = '# '+key+'\n\n历史训练记录；本次仅导入，没有执行模型。\n\n'
        note += '[查看完整谱系](http://127.0.0.1:5002/lineage.html) · [查看基座](http://127.0.0.1:5001/#/models/Qwen3-0.6B-base-reference/versions/1)\n\n'
        note += '训练配置见 Parameters；loss 横轴是微步，旧版验证发生在更新前，不与保存权重强行对齐。\n\n'
        for cp in rows:
            v = imp.versions[cp['key']]
            note += '- 微步 '+str(cp['step'])+'：[模型版本 '+str(v['version'])+'](http://127.0.0.1:5001/#/models/'+v['name']+'/versions/'+str(v['version'])+')，SHA '+cp['sha256'][:12]+'\n'
        c.set_tag(imp.runs['train:'+key], 'mlflow.note.content', note)
    assert src.unchanged(), 'Historical evidence changed during import'
    report={'runs':imp.runs,'models':imp.models,'versions':imp.versions,'checkpoints':checkpoint_records,'training_keys':[t['key'] for t in trainings],'training_configs':{t['key']:{'config':t['result']['config'],'dataset':t['result']['dataset'],'loss_id':t['loss_id']} for t in trainings},'evaluations':[{k:v for k,v in e.items() if k not in ('cases',)} for e in evaluations],'sources':src.hashes,'sources_unchanged':True,'existing_evaluation_runs':old['runs'],'no_execution':True,'reference_only':True}
    (DEFAULT_HOME/'lineage-import.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    template=(Path(__file__).parent/'lineage.html').read_text()
    (DEFAULT_HOME/'view/lineage.html').write_text(template.replace('__DATA__',json.dumps(report,ensure_ascii=False).replace('<','\\u003c')))
    from build_dashboard import render
    render(DEFAULT_HOME)
    print(json.dumps({'training_runs':len(trainings),'checkpoints':len(checkpoint_records),'evaluations':len(evaluations),'models':len(imp.models),'sources':len(src.hashes)}))


if __name__=='__main__':
    main()
