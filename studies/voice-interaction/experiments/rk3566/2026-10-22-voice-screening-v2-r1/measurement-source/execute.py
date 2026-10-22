"""Execute the frozen, single-round voice screen serially; preserve all results."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path('/home/orangepi/code/edge-ai')
EXP = ROOT / 'studies/voice-interaction/experiments/rk3566/2026-10-22-voice-screening-v2-r1'
PREP = ROOT / 'studies/voice-interaction/research/2026-10-22-runtime-preparation'
CACHE = Path('/home/orangepi/.cache/edge-voice-v2/runs/2026-10-22-voice-screening-v2-r1')
sys.path.insert(0, str(ROOT / 'tools/edge_benchmark'))
import benchmark


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def main():
    CACHE.mkdir(parents=True, exist_ok=False)
    check = subprocess.run(['python3', str(ROOT / 'tools/edge_benchmark/voice_preflight.py'), str(PREP)], capture_output=True, text=True, check=True)
    (EXP / 'preflight.json').write_text(check.stdout)
    sources = ROOT / 'tools/edge_benchmark'
    for name in ['benchmark.py', 'workers.py', 'voice_v2.py', 'voice_preflight.py', 'evaluation.py', 'evaluation_metrics.py', 'evaluation_report.py']:
        shutil.copy2(sources / name, EXP / 'measurement-source' / name)
    for name in ['assets-manifest.json', 'runtime-manifest.json', 'asr-fixtures.json']:
        shutil.copy2(PREP / name, EXP / name)
    text_source = PREP.parent / '2026-10-22-preparation-v2/text-fixtures.json'
    shutil.copy2(text_source, EXP / 'text-fixtures.json')
    shutil.copy2(text_source.parent / 'benchmark-plan.json', EXP / 'protocol.json')
    baseline = benchmark.observe(0)
    save(EXP / 'environment-before.json', dict(observation=baseline, process_snapshot=subprocess.check_output(['ps', '-eo', 'pid,comm,pcpu,rss'], text=True)))
    suites = {}
    for module in ['asr', 'llm', 'tts']:
        source = PREP / (module + '-screening.json')
        shutil.copy2(source, EXP / source.name)
        suites[module] = json.loads(source.read_text())
        save(EXP / (module + '-manifest.json'), benchmark.inventory(suites[module]))
    save(EXP / 'execution-plan.json', dict(protocol='rk3566-voice-screen-v2', tier='screening', rounds=1, modules=['asr','llm','tts'], total_budget_s=1800, per_module_budget_s=600, output_directory=str(CACHE), scope='single module sequentially; no ROS/YOLO/playback; no automatic repeat', module_case_ids={k:[c['id'] for c in v['cases']] for k,v in suites.items()}))
    start = time.monotonic()
    pending = []
    for module, suite in suites.items():
        module_start = time.monotonic()
        module_out = CACHE / module
        module_out.mkdir()
        local = EXP / module
        local.mkdir()
        for case in suite['cases']:
            remaining = min(1800 - (time.monotonic() - start), 600 - (time.monotonic() - module_start))
            if remaining <= 0:
                pending.append(case['id'])
                continue
            actual = dict(case, timeout=min(case['timeout'], remaining), requested_timeout_seconds=case['timeout'], budget_limited=remaining<case['timeout'])
            result = benchmark.run_case(actual, module_out, suite['python'])
            destination = local / case['id']
            shutil.copytree(module_out / case['id'], destination, ignore=shutil.ignore_patterns('*.wav','*.pcm'))
            media = [dict(path=str(f), sha256=sha(f), bytes=f.stat().st_size) for f in (module_out / case['id']).iterdir() if f.suffix in ['.wav','.pcm']]
            save(destination / 'external-media.json', dict(files=media))
    save(EXP / 'pending.json', pending)
    save(EXP / 'environment-after.json', benchmark.observe(0))
    print('Single-round screen completed; pending:', pending, flush=True)


if __name__ == '__main__':
    main()
