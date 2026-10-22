"""Offline static validation and byte-identical data-only re-render; no browser."""
import base64,hashlib,html.parser,io,json,pathlib,re,subprocess,time,urllib.parse,zipfile
W=pathlib.Path('/tmp/edge-ai-ticket-14');E=W/'studies/voice-interaction/experiments/final/2026-10-22-qwen-final132-v1';P=pathlib.Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle/ticket14')
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
class Parser(html.parser.HTMLParser):
 def __init__(self):super().__init__();self.ids=[];self.hrefs=[];self.external_resources=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.append(a['id'])
  if 'href' in a:self.hrefs.append(a['href'])
  if tag in ['script','img','link','iframe','audio','video','source']:
   ref=a.get('src',a.get('href',''))
   if ref and not ref.startswith('data:'):self.external_resources.append(ref)
proof=[]
for path in [E/'report.html',E/'inference-report.html',E/'preparation/output/report.html']:
 text=path.read_text();parser=Parser();parser.feed(text);assert len(parser.ids)==len(set(parser.ids)),str(path);assert not parser.external_resources,(path,parser.external_resources)
 for href in parser.hrefs:
  if href.startswith('#'):assert urllib.parse.unquote(href[1:]) in parser.ids,(path,href)
  elif not href.startswith(('data:','https:','http:','mailto:')):
   ref=urllib.parse.unquote(href.split('#')[0]);assert (path.parent/ref).is_file(),(path,href)
 proof.append({'path':str(path.relative_to(E)),'sha256':sha(path),'unique_ids':len(parser.ids),'hrefs_checked':len(parser.hrefs),'core_external_resources':0})
deferred=[]
for path in [E/'README.md',E/'reproduce.md',E/'integration-contract.md']:
 for href in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
  if not href.startswith(('http:','https:','#')):
   ref=path.parent/href.split('#')[0]
   if ref in [E/'manifest.json',E/'static-qa.json']:deferred.append(ref)
   else:assert ref.is_file(),(path,href)
doc=load(E/'lifecycle.json');assert len(doc['results'])==4 and all(len(r['cases'])==132 for r in doc['results']);assert len(doc['review']['cases'])==144;assert doc['review']['human_review'] is False
bundle=base64.b64decode(doc['evidence_bundle_base64']);assert hashlib.sha256(bundle).hexdigest()==doc['evidence_bundle_sha256']
with zipfile.ZipFile(io.BytesIO(bundle)) as z:
 names=z.namelist();assert len(names)==len(set(names));assert not any(n.startswith('/') or '..' in pathlib.PurePosixPath(n).parts for n in names)
 manifest=json.loads(z.read('raw-evidence-manifest.json'))
 for name,record in manifest['files'].items():
  data=z.read(name);assert len(data)==record['bytes'] and hashlib.sha256(data).hexdigest()==record['sha256'],name
 zipproof={'sha256':doc['evidence_bundle_sha256'],'bytes':len(bundle),'members':len(names),'manifest_members_verified':len(manifest['files'])}
start=time.perf_counter();target=P/'read-only-rerender.html';subprocess.run(['/usr/bin/python3','-m','tools.qwen_lifecycle.final_report',str(E/'lifecycle.json'),str(target)],cwd=W,check=True);assert sha(target)==sha(E/'report.html')
text=(E/'report.html').read_text();assert '@media(max-width:760px)' in text and 'position:fixed;right:0' in text and 'IntersectionObserver' in text and 'overflow-x:auto' in text;assert '<script src=' not in text
# Actual text-only check: JSON payload shown by the download must equal input data.
parser=Parser();parser.feed(text);download=next(h for h in parser.hrefs if h.startswith('data:application/json;base64,'));embedded=json.loads(base64.b64decode(download.split(',',1)[1]));assert embedded==doc
qa={'schema':'edge-ai/offline-static-qa-v1','html':proof,'paired_final_requests':528,'persona_context_reviews':144,'embedded_json_equal_input':True,'embedded_raw_zip':zipproof,'data_only_rerender':{'interpreter':'/usr/bin/python3','exit_code':0,'seconds':time.perf_counter()-start,'byte_identical':True,'sha256':sha(target),'scope':'standard Python reads JSON; no model/runtime/server/browser launch'},'layout_static':{'desktop_fixed_right_nav':True,'mobile_760px_sticky_nav':True,'table_local_overflow':True,'active_section_script':True,'anchors_and_local_links':True},'visual_validation':'UNVERIFIED: prior browser file preview denied; no HTTP/alternatebrowser/Playwright workaround','limitations':'Static source/layout/reference checks do not establish actual desktop/mobile rendering or visual acceptance.'};put(E/'static-qa.json',qa)
# Final manifest deliberately excludes itself; raw ZIP manifest was made before view embedding.
files=[p for p in sorted(E.rglob('*')) if p.is_file() and p.name!='manifest.json'];assert not any(p.is_symlink() for p in files);assert not any(p.suffix in ['.gguf','.safetensors','.wav','.mp4','.dylib','.so'] for p in files)
put(E/'manifest.json',{'schema':'edge-ai/final-experiment-manifest-v1','files':{str(p.relative_to(E)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in files},'scope':'all final experiment files except this manifest; historical files unchanged'})
assert all(p.is_file() for p in deferred)
print('Static QA passed; visual UNVERIFIED;',len(files),'manifestfiles;',zipproof)
