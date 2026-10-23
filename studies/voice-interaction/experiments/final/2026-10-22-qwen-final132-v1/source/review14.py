"""Package explicit assistant verdicts after reading full responses, not keywords."""
import json,pathlib,datetime
R=pathlib.Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');P=R/'ticket14';E=pathlib.Path('/tmp/edge-ai-ticket-14/studies/voice-interaction/experiments/final/2026-10-22-qwen-final132-v1')
def load(p):return json.loads(p.read_text())
rubric=load(pathlib.Path('/tmp/edge-ai-ticket-14/studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected9-adaptation-v1/persona-review.json'))['rubric']
review={'schema':'edge-model-persona/context-review-v1','reviewer':'assistant GPT-6 Codex','human_review':False,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'Assistant read every full saved response in user context and supplied explicit per-case verdicts. Keyword scores auxiliary only. Claims record requested known fact/unknown boundary and additional factual assertions separately.','rubric':rubric,'cases':[]}
for device in ['mac','board']:
 for model in ['base','selected']:
  name='final14-'+device+'-'+model;rp=E/'runs'/name/'results.json';vp=P/(device+'-'+model+'-verdicts.json')
  if not rp.exists() or not vp.exists():continue
  r=load(rp);v=load(vp)
  for c in r['cases']:
   if c['kind']!='persona':continue
   verdict=v[c['id']];extra_bad=(device=='mac' and model=='base' and c['id'] in ['holdout_072','holdout_105']) or (device=='mac' and model=='selected' and c['id']=='holdout_084') or verdict.get('unsupported_assertion',False)
   review['cases'].append({'run_id':name,'case_id':c['id'],'input':c['user'],'output':c.get('generation',{}).get('raw',''),'native_calls':c.get('assessment',{}).get('reply',{}).get('tool_calls',[]),'rubric':c['expected']['rubric'],'passed':verdict['passed'],'reason':verdict['reason'],'claims':[{'claim':'Requested '+c['expected']['rubric']+' fact or unknown boundary','passed':verdict['passed'],'finding':verdict['reason']},{'claim':'Additional factual assertions remain supported / no invented biography','passed':not extra_bad,'finding':('Unsupported explicit identity/provenance assertion; see full contextual reason.' if extra_bad else 'No additional invented identity, creator real name, birth year, location or life history asserted; this does not fill missing requested facts.')}],'auxiliary_keyword_pass':c.get('assessment',{}).get('persona_valid')})
(E/'persona-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
print({n:sum(c['passed'] for c in review['cases'] if c['run_id']==n) for n in {c['run_id'] for c in review['cases']}})
