import json,pathlib
from gguf import GGUFReader
R=pathlib.Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle/artifacts');paths={'tuned':R/'selected9-768-v3/qwen3-selected9-768-v3-q4_k_m.gguf','base_matched':R/'matched-base-dedup-v2/qwen3-base-q4_k_m.gguf','base_duplicate_diagnostic':R/'matched-base-v1/qwen3-base-q4_k_m.gguf'}
data={}
for name,p in paths.items():
 r=GGUFReader(str(p));data[name]={'path':str(p),'tensors':[{'name':t.name,'type':str(t.tensor_type),'shape':t.shape.tolist()} for t in r.tensors],'metadata':{k:repr(v.contents()) for k,v in r.fields.items()}}
a=data['tuned'];b=data['base_matched'];diff={k:[a['metadata'].get(k),b['metadata'].get(k)] for k in a['metadata'].keys()|b['metadata'].keys() if a['metadata'].get(k)!=b['metadata'].get(k)}
out={'tuned_and_base_tensor_names_types_shapes_equal':a['tensors']==b['tensors'],'metadata_differences':diff,'all':data,'interpretation':'Matched layout/quantized tensor types/tokenizer metadata; general.name/source-file metadata may differ. Earlier duplicate tensor head preserved as diagnostic, excluded from matched #14 configuration.'};pathlib.Path('/tmp/edge-ai-implementation-20261022/precision13-gguf-layout.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(out['tuned_and_base_tensor_names_types_shapes_equal']);print(diff.keys());print({k:len(v['tensors']) for k,v in data.items()})
