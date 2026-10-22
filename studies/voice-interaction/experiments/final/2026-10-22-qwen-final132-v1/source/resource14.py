"""Audit native counters and actual event sampling; reads immutable runs only."""
import json,pathlib,statistics
E=pathlib.Path('/tmp/edge-ai-ticket-14/studies/voice-interaction/experiments/final/2026-10-22-qwen-final132-v1')
def load(p):return json.loads(p.read_text())
def dist(values):
 values=[v for v in values if v is not None]
 return {'n':len(values),'min':min(values) if values else None,'median':statistics.median(values) if values else None,'max':max(values) if values else None}
audit=[]
for device in ['mac','board']:
 for model in ['base','selected']:
  name='final14-'+device+'-'+model;root=E/'runs'/name;result=load(root/'benchmark/results.json');intervals=[];temperatures={};samples=0;rows=[]
  budgets={r['id']:r for r in load(root/'context-budget.json')}
  for c in result['cases']:
   events=load(root/'benchmark/events'/(c['id']+'.json'));res=events['resources'];samples+=len(res)
   intervals.extend(b['monotonic_seconds']-a['monotonic_seconds'] for a,b in zip(res,res[1:]))
   for sample in res:
    for zone,v in sample.get('thermal_zone_celsius',{}).items():temperatures.setdefault(zone,[]).append(v)
   g=c.get('generation',{});u=g.get('native_usage',{});t=g.get('native_timings',{})
   rows.append({'id':c['id'],'status':c['status'],'prompt_full_usage':g.get('prompt_tokens'),'template_preflight_tokens':budgets[c['id']]['prompt_tokens'],'evaluated_prefill':g.get('evaluated_prefill_tokens'),'cached_native_usage':u.get('prompt_tokens_details',{}).get('cached_tokens'),'native_cache_n':t.get('cache_n'),'output_usage':g.get('output_tokens'),'native_predicted_n':t.get('predicted_n'),'decode_steps_from_native_definition':(t['predicted_n']-1) if 'predicted_n' in t else None,'native_prefill_tps':t.get('prompt_per_second'),'native_decode_tps':t.get('predicted_per_second'),'ttft_seconds':g.get('ttft_seconds'),'complete_response_seconds':g.get('wall_seconds'),'valid_call_seconds':c.get('valid_call_seconds')})
  loading=load(root/'server-load.json');memory_key='peak_pss_bytes' if device=='board' else 'peak_rss_bytes';peaks=[c.get('resources',{}).get(memory_key) for c in result['cases']]+[loading['resources'].get(memory_key)];peaks=[v for v in peaks if v is not None]
  audit.append({'overall_sampled_model_peak':{'kind':'PSS' if device=='board' else 'RSS','bytes':max(peaks) if peaks else None,'scope':'maximum across separate loading and per-case inference/intake-wait windows; sampled, not kernel HWM'},'run_id':name,'declared_wait_interval_seconds':.2,'actual_sampling_intervals_seconds':dist(intervals),'sample_count':samples,'thermal_zone_celsius':{z:dist(v) for z,v in temperatures.items()},'thermal_scope':'available Linux zones, exact type not normalized; Mac no measured GPU/thermal metric','server_load':load(root/'server-load.json'),'budget_max_prompt_plus_output':max(b['prompt_tokens']+b['maximum_output_tokens'] for b in budgets.values()),'cold_prefix_first_case':rows[0],'warm_following_cases':rows[1:],'counter_scope':'Full prompt usage and processed prefill are different. Native decode uses n_gen-1 steps. Cold means empty newserver KV, not controlled OS page cache. Actual intervals include sampling work plus200ms wait and short terminal gaps. Loading separate from inference/intake.'})
(E/'resource-audit.json').write_text(json.dumps({'schema':'edge-ai/native-resource-audit-v1','runs':audit},ensure_ascii=False,indent=2)+'\n')
