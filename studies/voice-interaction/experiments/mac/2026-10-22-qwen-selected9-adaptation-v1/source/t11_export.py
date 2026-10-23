import json
from pathlib import Path
r=Path('/Users/syz/.local/share/edge-ai/qwen-lifecycle')
s=(r/'inputs/pilot-seeded-export-request.json').read_text().replace('qwen3-pilot32-seeded-export-v3','qwen3-selected9-512-export-v1').replace('runs/pilot-train32-seeded-v2/adapter','runs/selected9-train512-v1/adapter').replace('artifacts/pilot32-seeded-v2','artifacts/selected9-512-v1').replace('qwen3-pilot32-','qwen3-selected9-512-').replace('/tmp/edge-ai-ticket-10','/tmp/edge-ai-ticket-11')
(r/'inputs/selected9-512-export-request.json').write_text(s)
