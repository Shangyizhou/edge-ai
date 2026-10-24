"""Version-pinned, reversible local MLflow 3.1.4 model-table defaults/persistence."""
import hashlib
import json
import shutil
from pathlib import Path
import mlflow
from mlflow import MlflowClient
from import_history import DEFAULT_HOME


def main():
    import sys
    if '--restore' in sys.argv:
        backup=DEFAULT_HOME/'backups/native-frontend-3.1.4'
        root=Path(mlflow.__file__).parent/'server/js/build'
        assert mlflow.__version__=='3.1.4'
        shutil.copy2(backup/'index.html',root/'index.html')
        print('Restored original MLflow entrypoint; metadata and model evidence retained.')
        return
    assert mlflow.__version__=='3.1.4', 'Patch requires exactly MLflow3.1.4'
    mlflow.set_tracking_uri('sqlite:///'+str(DEFAULT_HOME/'mlflow.db'))
    c=MlflowClient(); models=c.search_logged_models(['1'],max_results=100)
    visibility={k:False for k in ['status','source','source_run_id','registered_models','dataset']}
    for model in models:
        for key in model.params:visibility['params.'+key]=False
        for metric in model.metrics or []:
            dataset=json.dumps([metric.dataset_name,metric.dataset_digest],separators=(',',':'))+'.' if metric.dataset_name else ''
            visibility['metrics.'+dataset+metric.key]=False
    # Current native UI generates these exact column identifiers.
    for key in ['artifact_type','artifact_format','weight_precision']:visibility['params.'+key]=True
    digest='cdf644509133524d2c95d33c133fd1ae2655e41d1c936c7b594ca4e863c529cc'
    for key in ['tool_exact','no_call_misroutes','model_bytes','rss_mib','single_http_p50_seconds']:
        visibility['metrics.'+json.dumps(['observed_development50',digest],separators=(',',':'))+'.'+key]=True
    build=Path(mlflow.__file__).parent/'server/js/build/static/js'
    asset=build/'7951.1c03793d.chunk.js'
    backup=DEFAULT_HOME/'backups/native-frontend-3.1.4/7951.1c03793d.chunk.js'
    backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():shutil.copy2(asset,backup)
    source=backup.read_text()
    token='columnVisibility:{},rowVisibilityMode:o.oy.FIRST_10_RUNS'
    assert source.count(token)==1
    key='edge-ai.native.models.columns.v1'
    defaults=json.dumps(visibility,separators=(',',':'))
    getter='(()=>{if(!window.location.hash.startsWith("#/experiments/1/models"))return {};try{return JSON.parse(localStorage.getItem('+json.dumps(key)+'))||'+defaults+'}catch(e){return '+defaults+'}})()'
    source=source.replace(token,'columnVisibility:'+getter+',rowVisibilityMode:o.oy.FIRST_10_RUNS')
    token='if("SET_COLUMN_VISIBILITY"===t.type)return{...e,columnVisibility:t.columnVisibility};'
    assert source.count(token)==1
    source=source.replace(token,'if("SET_COLUMN_VISIBILITY"===t.type){try{localStorage.setItem('+json.dumps(key)+',JSON.stringify(t.columnVisibility))}catch(e){}return{...e,columnVisibility:t.columnVisibility}}')
    token='p=(0,s.t)(e),[f,A]=(0,a.useState)("")'
    assert source.count(token)==1
    source=source.replace(token,'p=(0,s.t)(e),[f,A]=(0,a.useState)(window.location.hash.startsWith("#/experiments/1/models")&&!window.location.hash.includes("allModels=1")?"tags.comparison_group = \'selected-quantization\'":"")')
    # New content-addressed filenames prevent the upstream 28-day static cache hiding the change.
    new_hash=hashlib.sha256(source.encode()).hexdigest()[:8]
    patched=build/('7951.'+new_hash+'.chunk.js')
    patched.write_text(source)
    asset.write_bytes(backup.read_bytes())
    root=build.parent.parent
    index=root/'index.html'
    index_backup=backup.parent/'index.html'
    if not index_backup.exists():shutil.copy2(index,index_backup)
    original_index=index_backup.read_text()
    import re
    main_name=re.search(r'main\.[a-f0-9]+\.js',original_index).group(0)
    original_main=(build/main_name).read_text()
    assert original_main.count('7951:"1c03793d"')==1
    new_main=original_main.replace('7951:"1c03793d"','7951:'+json.dumps(new_hash))
    experiment_asset=build/'experimentPage.7db6acf6.chunk.js'
    experiment_backup=backup.parent/experiment_asset.name
    if not experiment_backup.exists():shutil.copy2(experiment_asset,experiment_backup)
    experiment_source=experiment_backup.read_text()
    for variable in ['e','r']:
        token='getStoreForComponent("ExperimentPage",'+variable+')'
        assert experiment_source.count(token)==1
        suffix='+(window.location.hash.includes("comparison_view")?":training-standard-v1":"")'
        experiment_source=experiment_source.replace(token,'getStoreForComponent("ExperimentPage",'+variable+suffix+')')
    experiment_hash=hashlib.sha256(experiment_source.encode()).hexdigest()[:8]
    (build/('experimentPage.'+experiment_hash+'.chunk.js')).write_text(experiment_source)
    assert new_main.count('7419:"7db6acf6"')==1
    new_main=new_main.replace('7419:"7db6acf6"','7419:'+json.dumps(experiment_hash))
    original_columns='selectedColumns:[(0,i.GF)(o.RO.ATTRIBUTES,o.qo.SOURCE),(0,i.GF)(o.RO.ATTRIBUTES,o.qo.MODELS),(0,i.GF)(o.RO.ATTRIBUTES,o.qo.DATASET)],runsExpanded:{}'
    assert new_main.count(original_columns)==1
    training_columns=['params.`train_samples`','params.`learning_rate`','params.`rank`','params.`mlx_direct_scale`','params.`lora_modules`','params.`loss_objective`','metrics.`dev_tool_exact_rate`','metrics.`dev_false_call_rate`']
    default_columns=json.dumps(training_columns,separators=(',',':'))
    original_fallback='[(0,i.GF)(o.RO.ATTRIBUTES,o.qo.SOURCE),(0,i.GF)(o.RO.ATTRIBUTES,o.qo.MODELS),(0,i.GF)(o.RO.ATTRIBUTES,o.qo.DATASET)]'
    from catalog import load_view
    base_run=load_view(DEFAULT_HOME)[0]['runs']['base']
    scope='window.location.hash.startsWith("#/experiments/1")&&!window.location.hash.includes("view=process")'
    expanded='window.location.hash.includes("comparison_view")||window.location.hash.includes("historical_training")'
    replacement='selectedColumns:('+scope+'?'+default_columns+':'+original_fallback+'),runsExpanded:('+expanded+'?'+json.dumps({base_run:True})+':{})'
    new_main=new_main.replace(original_columns,replacement)
    main_hash=hashlib.sha256(new_main.encode()).hexdigest()[:8]
    new_main_name='main.'+main_hash+'.js'
    (build/new_main_name).write_text(new_main)
    index.write_text(original_index.replace(main_name,new_main_name))
    report={'mlflow_version':mlflow.__version__,'asset':str(patched),'entrypoint':str(index),'entrypoint_backup':str(index_backup),'backup':str(backup),'before_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'after_sha256':hashlib.sha256(patched.read_bytes()).hexdigest(),'storage_key':key,'defaults':visibility,'model_count':len(models),'source_map':'unmodified upstream map; patched expressions documented here','scope':'native logged-model list defaults and column persistence; no model execution'}
    (DEFAULT_HOME/'native-frontend-patch.json').write_text(json.dumps(report,indent=2))
    print('Patched native model-table defaults and column persistence; original asset backed up.')

if __name__=='__main__':main()
