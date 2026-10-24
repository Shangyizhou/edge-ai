"""Project-stable catalog identities and runtime-specific binding adapters."""
import hashlib
import json
from pathlib import Path
from paths import ROOT, DEFAULT_HOME, CATALOG_ROOT

CATALOG = CATALOG_ROOT
REPORTS = ROOT / 'studies/voice-interaction/reports'


def stable_id(kind, value):
    return kind + '-' + hashlib.sha256(value.encode()).hexdigest()[:24]


def read_index(root=None):
    root=Path(root or CATALOG)
    index=json.loads((root/'index.json').read_text())
    records={}
    for entry in index['records']:
        path=(root/entry['path']).resolve()
        if not path.is_relative_to(root.resolve()):raise ValueError('Catalog path escapes root')
        blob=path.read_bytes()
        if hashlib.sha256(blob).hexdigest()!=entry['sha256']:
            raise ValueError('Catalog hash mismatch: '+str(path))
        record=json.loads(blob)
        if record['id']!=entry['id'] or record['kind']!=entry['kind']:raise ValueError('Catalog identity mismatch')
        required={'dataset':['digest','sample_count'],'training':['configuration','execution_summary','dataset_ids'],'model':['identity','artifact_type','parent_ids'],'evaluation':['model_ids','summary','view']}
        if record['kind'] not in required or any(k not in record for k in required[record['kind']]):raise ValueError('Invalid catalog record')
        if record['id'] in records:raise ValueError('Duplicate catalog ID')
        records[record['id']]=record
    for record in records.values():
        for key in ('dataset_ids','parent_ids','model_ids','training_ids'):
            for target in record.get(key,[]):
                if target not in records:raise ValueError('Dangling '+target)
    visited=set();active=set()
    def visit(id):
        if id in active:raise ValueError('Cyclic catalog lineage')
        if id in visited:return
        active.add(id)
        for key in ('parent_ids','training_ids','model_ids'):
            for target in records[id].get(key,[]):visit(target)
        active.remove(id);visited.add(id)
    for id in records:visit(id)
    return index,records


def load_view(home=DEFAULT_HOME):
    """Existing UI adapter; canonical records never contain MLflow IDs."""
    index,records=read_index()
    bindings=json.loads((home/'bindings/catalog-mlflow.json').read_text())
    lineage={'runs':{},'models':{},'versions':{},'checkpoints':{},'training_keys':[], 'training_configs':{},'evaluations':[], 'sources':{},'existing_evaluation_runs':{}}
    lineage['runs'].update(bindings['auxiliary_runs'])
    quant={'comparison':[],'cases':{},'runs':{},'contexts':{}}
    run_labels={};facts={};cases={}
    for r in records.values():
        kind=r['kind'];origin=r['origin_key'];binding=bindings['records'].get(r['id'],{})
        if kind=='training' and r['execution_summary']['status']=='completed':
            lineage['training_keys'].append(origin)
            lineage['training_configs'][origin]={'config':r['configuration'],'dataset':r['dataset_summary'],'loss_id':r['loss_objective']}
            lineage['runs']['train:'+origin]=binding['run_id'];run_labels[origin]=r['display_alias'];facts[origin]=r['execution_summary']
        if kind=='model':
            lineage['models'][origin]=binding['model_id'];lineage['versions'][origin]=binding['registry']
            if r['artifact_type']=='lora_adapter':
                cp={**r['checkpoint'],'key':origin,'model_id':binding['model_id']}
                lineage['checkpoints'][origin]=cp
        if kind=='evaluation':
            q=r['summary'];b=r['view']
            if b['group']=='quantization':
                c=b['candidate'];quant['comparison'].append({'candidate':c,'quality':q,'resources':r['resources'],'artifact':r['artifact_summary']});quant['runs'][c]=binding['run_id'];lineage['existing_evaluation_runs'][c]=binding['run_id']
            elif b['group']=='checkpoint':
                e={'key':origin,'model_key':records[r['model_ids'][0]]['origin_key'],'train_key':records[r['training_ids'][0]]['origin_key'] if r['training_ids'] else None,'split':r['split'],'summary':q,'digest':records[r['dataset_ids'][0]]['digest']}
                lineage['evaluations'].append(e);lineage['runs']['eval:'+origin]=binding['run_id']
            if r.get('cases_source'):
                source=r['cases_source'];path=ROOT/source['path'];blob=path.read_bytes()
                if hashlib.sha256(blob).hexdigest()!=source['sha256']:raise ValueError('Cases source changed: '+str(path))
                cases[origin]=json.loads(blob)
                if b['group']=='quantization':quant['cases'][b['candidate']]=cases[origin]
    lineage['training_keys'].sort(key=lambda k:run_labels[k])
    source=index['view_context_source'];blob=(ROOT/source['path']).read_bytes()
    if hashlib.sha256(blob).hexdigest()!=source['sha256']:raise ValueError('Tool context source changed')
    quant['contexts']={r['id']:[t['function']['name'] for t in r['tools']] for r in map(json.loads,blob.decode().splitlines()) if r}
    order=['adapter','merged','f16','q8','q4'];quant['comparison'].sort(key=lambda r:order.index(r['candidate']))
    lineage['experiment_id']=bindings['experiment_id'];quant['experiment_id']=bindings['experiment_id']
    return lineage,quant,cases,run_labels,facts
