import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
from html.parser import HTMLParser
import zipfile

root=Path('/tmp/edge-ai-ticket-12/studies/voice-interaction/experiments/rk3566/2026-10-22-qwen-pilot32-board-v1')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location('current_contract','/Users/syz/.codex/skills/edge-model-benchmark/scripts/run_benchmark.py');contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
roots=list((root/'runs').glob('*/results.json'));count=0;checked=0
for p in roots:
 r=json.loads(p.read_text());request=json.loads((p.parent/'launcher-request.json').read_text());contract.check_request(request);contract.check_result(r,request);count+=len(r['cases'])
 for ref in r['evidence']:
  assert sha(p.parent/ref['path'])==ref['sha256'],ref
  checked+=1
 assert sha(p.parent/r['benchmark_result']['path'])==r['benchmark_result']['sha256']
 for src in (p.parent/'source').glob('*.py'):
  assert src.read_bytes()==(Path('/tmp/edge-ai-ticket-12/tools/qwen_lifecycle')/src.name).read_bytes(),src
assert len(roots)==5 and count==23
class Parser(HTMLParser):
 def __init__(self):super().__init__();self.ids=set();self.refs=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:assert a['id'] not in self.ids;self.ids.add(a['id'])
  for key in ('href','src'):
   if key in a:self.refs.append(a[key])
refs=0
for p in [root/'report.html',root/'prepare/report.html',root/'prepare-cache/report.html']:
 parser=Parser();parser.feed(p.read_text())
 for target in parser.refs:
  if target.startswith('#'):assert target[1:] in parser.ids
  elif target.startswith(('data:','https://','http://')):pass
  else:assert (p.parent/target.split('#')[0]).exists(),target
  refs+=1
text=(root/'report.html').read_text();assert 'getAttribute("href")!=="#top"' in text
assert '@media' in text and 'position:fixed' in text.replace(' ','') and 'overflow-x:auto' in text.replace(' ','')
payload=re.search(r'href="data:application/json;base64,([^\"]+)"',text).group(1)
assert len(json.loads(base64.b64decode(payload)))==6
archive=re.search(r'href="data:application/zip;base64,([^\"]+)"',text).group(1)
with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive))) as z:
 assert z.testzip() is None
 assert all(not n.startswith('/') and '..' not in Path(n).parts for n in z.namelist())
 zipped=len(z.namelist())
assert '&lt;tool_call&gt;' in text or 'tool_calls' in text
for path in root.rglob('*.json'):json.loads(path.read_text())
for target in re.findall(r'\]\(([^)]+)\)',(root/'README.md').read_text()):
 if target.startswith('http'):continue
 if target=='qa.json':continue
 assert (root/target).exists(),target
qa={'status':'PASS','real_runs':5,'inference_executions':23,'current_benchmark_contract':'read-only validator after source skill update9982deb; no rerun','hashed_evidence_references_verified':checked,'collector_python_sources_match_05132f0':True,'html_local_references_and_anchors_checked':refs,'embedded_result_groups':6,'embedded_zip_members':zipped,'json_parse':'all JSON valid','escaping':'maintained renderer; complete outputs remain visible; raw JSON embedded escaped/base64','responsive_css':'fixed navigation, @media and inner overflow-x present','nav':'#top excluded from active chapter scan','raw_evidence_unchanged_by_render':True,'browser_visual':'unverified; file:// policy denied earlier; no workaround attempted','owned_processes':'build/queues/servers completed; device-after.txt targeted ps had no match'}
(root/'qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n')
files=[p for p in sorted(root.rglob('*')) if p.is_file() and p.name!='evidence-manifest.json' and '__pycache__' not in p.parts]
(root/'evidence-manifest.json').write_text(json.dumps({'schema':'edge-ai/evidence-manifest-v1','source_kind':'actual pilot device measurements + labelled derived views','files':[{'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(qa,ensure_ascii=False));print('manifest files',len(files))
