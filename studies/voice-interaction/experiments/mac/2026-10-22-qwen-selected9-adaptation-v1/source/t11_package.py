"""Copy real evidence, render views and verify hashes; no model execution."""
import hashlib,json,re,shutil,subprocess
from html.parser import HTMLParser
from pathlib import Path
from tools.qwen_lifecycle.report import render
from tools.qwen_lifecycle.adaptation_report import render as paired
from tools.qwen_lifecycle.stages import render_stages
root=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle');exp=Path('studies/voice-interaction/experiments/mac/2026-10-22-qwen-selected9-adaptation-v1')
selected=json.loads((exp/'selection.json').read_text())
run_names=selected['paired_runs'];all_names=['selected9-base-short','selected9-base-full','selected9-lora512-short','selected9-lora512-full','selected9-lora768-v2-short','selected9-lora768-v2-full']
all_names += ['selected9-base-guard','selected9-lora768-v2-guard','selected9-lora768-v3-short','selected9-lora768-v3-full','selected9-base-facts','selected9-lora768-v3-facts','selected9-base-routing','selected9-lora768-v3-routing']
all_names += [n for n in run_names if n not in all_names]
results={}
for name in all_names:
 src=root/'runs'/name;dst=exp/'validation'/name
 if not dst.exists():shutil.copytree(src,dst,ignore=shutil.ignore_patterns('*.html'))
 results[name]=json.loads((src/'results.json').read_text())
for srcname,dstname in [(selected['training_run'],'training-selected'),(selected['export_run'],'export')]:
 src=root/'runs'/srcname;dst=exp/dstname
 if not dst.exists():shutil.copytree(src,dst,ignore=shutil.ignore_patterns('adapter','*.html'))
train=json.loads((exp/'training-selected/results.json').read_text());export=json.loads((exp/'export/results.json').read_text())
plotpy='/Users/syz/.cache/uv/archive-v0/FBo0nusP6AL2rf5C/bin/python'
subprocess.run([plotpy,'-m','tools.qwen_lifecycle.training_curve',str(exp/'training-selected/results.json'),str(exp/'loss-selected.svg')],check=True)
review=json.loads((exp/'persona-review.json').read_text());svg=(exp/'loss-selected.svg').read_text();svg=svg[svg.index('<svg'):]
(exp/'report.html').write_text(paired([results[n] for n in run_names],review,selected,train,svg))
(exp/'inference.html').write_text(render(list(results.values())))
(exp/'stages.html').write_text(render_stages([json.loads((exp/'training/results.json').read_text()),json.loads((exp/'training-v2/results.json').read_text()),train,export],(exp/'loss-selected.svg').read_bytes(),'report.html'))
for name in ['tools.json','persona.json','source-manifest.json','registry_validate.py','selected9-compact-guard-protocol.json','selected9-compact-facts-protocol.json','selected9-routing-protocol.json']:
 shutil.copy2(root/'inputs'/name,exp/'source'/name)
for name in ['datasets.py','adaptation_report.py','test_datasets.py']:
 shutil.copy2(Path('tools/qwen_lifecycle')/name,exp/'source'/('maintained-'+name+'.txt'))
for name in ['/tmp/t11_bench_v2.py','/tmp/t11_bench_v3.py','/tmp/t11_data_v3.py','/tmp/t11_control_audit.py','/tmp/t11_review_v3.py','/tmp/t11_review_facts.py','/tmp/t11_review_routing.py','/tmp/t11_facts_bench.py','/tmp/t11_routing_bench.py','/tmp/t11_export_selected.py','/tmp/t11_skill_audit.py','/tmp/t11_package.py']:
 shutil.copy2(name,exp/'source'/Path(name).name)
# Original evidence hashes must remain correct after copying.
checked=0
for result_path in list((exp/'validation').glob('*/results.json'))+[exp/'training/results.json',exp/'training-v2/results.json',exp/'training-selected/results.json',exp/'export/results.json']:
 result=json.loads(result_path.read_text())
 for record in result.get('evidence',[]):
  p=result_path.parent/record['path']
  assert p.exists(),p
  assert hashlib.sha256(p.read_bytes()).hexdigest()==record['sha256'],p
  checked+=1
class Refs(HTMLParser):
 def __init__(self):super().__init__();self.ids=set();self.refs=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.add(a['id'])
  if tag=='a' and 'href' in a:self.refs.append(a['href'])
refs_count=0
for p in exp.glob('*.html'):
 parser=Refs();parser.feed(p.read_text())
 for ref in parser.refs:
  if ref.startswith('data:') or '://' in ref:continue
  if ref.startswith('#'):assert ref[1:] in parser.ids,(p,ref)
  else:assert (p.parent/ref.split('#')[0]).exists(),(p,ref)
  refs_count+=1
 for token in ['@media','rail','viewport']:assert token in p.read_text(),(p,token)
manifest={'kind':'immutable-experiment-evidence','raw_hash_records_verified':checked,'local_html_refs_verified':refs_count,'browser_visual':'unverified; file preview policy denial, no workaround','files':[{'path':str(p.relative_to(exp)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(exp.rglob('*')) if p.is_file() and p.name!='evidence-manifest.json']}
(exp/'evidence-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print({'files':len(manifest['files']),'hashes_verified':checked,'refs_verified':refs_count})
