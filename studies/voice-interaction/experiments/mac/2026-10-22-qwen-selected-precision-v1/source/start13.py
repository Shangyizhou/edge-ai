import json,pathlib
R=pathlib.Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle'); W=pathlib.Path('/tmp/edge-ai-ticket-13'); P=R/'inputs'; A=R/'artifacts/selected9-768-v3'; O=R/'artifacts/matched-base-v1'
def put(n,x): (P/n).write_text(json.dumps(x,ensure_ascii=False,indent=2))
x=json.loads((P/'selected9-lora768-v3-routing-request.json').read_text()); x['run_id']='precision13-merged-validation'; x['stage']='same MLX merged validation'; x['candidate']['model_path']=str(A/'merged'); x['candidate'].pop('adapter_path'); x['candidate']['lineage']='selected v3 merged BF16; same MLX controls'; put('precision13-merged-request.json',x)
e={'schema':'edge-model-export/request-v1','run_id':'precision13-export','artifacts':{'selected-f16':str(A/'qwen3-selected9-768-v3-f16.gguf'),'base':x['candidate']['model_path']},'operations':[],'sampling_interval_seconds':.1}
e['artifacts']['base']=str(pathlib.Path((R/'model-path.txt').read_text().strip()))
e['operations'].append({'kind':'quantize','inputs':['selected-f16'],'output':{'id':'selected-q5','path':str(A/'qwen3-selected9-768-v3-q5_k_m.gguf')},'command':[str(R/'llama.cpp/build/bin/llama-quantize'),e['artifacts']['selected-f16'],str(A/'qwen3-selected9-768-v3-q5_k_m.gguf'),'Q5_K_M','4']})
O.mkdir(exist_ok=True)
e['operations'].append({'kind':'convert','inputs':['base'],'output':{'id':'base-f16','path':str(O/'qwen3-base-f16.gguf')},'cwd':str(W),'command':[str(R/'venv/bin/python'),'-m','tools.qwen_lifecycle.convert_hf','--source',e['artifacts']['base'],'--tokenizer-source',e['artifacts']['base'],'--staging',str(O/'converter-input'),'--converter-python',str(R/'converter-venv/bin/python'),'--converter',str(R/'llama.cpp/convert_hf_to_gguf.py'),'--output',str(O/'qwen3-base-f16.gguf')]})
e['operations'].append({'kind':'quantize','inputs':['base-f16'],'output':{'id':'base-q4','path':str(O/'qwen3-base-q4_k_m.gguf')},'command':[str(R/'llama.cpp/build/bin/llama-quantize'),str(O/'qwen3-base-f16.gguf'),str(O/'qwen3-base-q4_k_m.gguf'),'Q4_K_M','4']})
put('precision13-export-request.json',e)
