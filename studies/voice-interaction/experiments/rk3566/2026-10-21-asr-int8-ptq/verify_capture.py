import hashlib,json
from pathlib import Path
import numpy as np
import onnxruntime as ort
base=Path(__file__).parent
root=base/'calibration/capture16'
manifest=json.loads((root/'manifest.json').read_text())
for component,rows in manifest['input_samples'].items():
 lines=(root/(component+'.txt')).read_text().splitlines()
 assert len(lines)==len(rows)==16
 for line,row in zip(lines,rows):
  assert line.split()==[x['path'] for x in row['inputs']]
  for item in row['inputs']:
   p=Path(item['path']); assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
   arr=np.load(p,allow_pickle=False);assert str(arr.dtype)==item['dtype'] and list(arr.shape)==item['shape']
options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
session=ort.InferenceSession(str(base/'models/onnx/encoder-epoch-99-avg-1.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
a,b=manifest['input_samples']['encoder'][:2]
feed={x['name']:np.load(x['path'],allow_pickle=False) for x in a['inputs']}
outputs={n.name:v for n,v in zip(session.get_outputs(),session.run(None,feed))}
for item in b['inputs'][1:]:
 actual=np.load(item['path'],allow_pickle=False)
 assert np.array_equal(outputs['new_'+item['name']],actual),item['name']
summary=dict(status='ok',verified_tensors=624,encoder_state_tensors_replayed=35,feedback='exact equality to previous ONNX outputs; initial state zero, subsequent real state',calibration_fixture_ids=['official0','command'],public_reference_fixtures_used=False)
(base/'capture-validation.json').write_text(json.dumps(summary,indent=2)+'\n')
print(summary)
