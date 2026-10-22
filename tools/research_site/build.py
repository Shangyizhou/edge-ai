"""Publish standalone HTML reports with a small static report index."""
import argparse
import html
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
VOICE = Path('studies/voice-interaction')
REPORTS = [
    ('selection.html', '模型选型', '候选模型、来源与本轮筛选结果；不代表板端验收通过。',
     VOICE / 'research/2026-10-22-local-stack/report.html'),
    ('readiness.html', '最小推理就绪', 'ASR 解码、LLM 生成和 TTS 合成的最小真实推理记录。',
     VOICE / 'experiments/rk3566/2026-10-22-preparation-smoke-v1/readiness/report.html'),
    ('voice-screening/report.html', '语音单模块评测',
     '主报告 · 结论、模型与后端、3 条样例、实际转写、速度和 CPU / 内存对照。公开版不含录音。',
     VOICE / 'reports/2026-10-22-voice-screening/report.html'),
]


def build(output):
    output = output.resolve()
    if output.exists():
        raise FileExistsError('Use a new output directory: ' + str(output))
    if output == ROOT or ROOT in output.parents and not output.name.startswith('_site'):
        raise ValueError('Build outside the repository or to an _site* directory')
    # Keep evidence files available to frozen reports, without rendering SOP pages.
    output.mkdir(parents=True)
    for path in (ROOT / 'studies').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo'):
            target = output / 'evidence' / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    cards = []
    for step, (destination, title, description, source) in enumerate(REPORTS, start=1):
        target = output / 'reports' / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        # Frozen reports keep their original relative evidence links at their
        # evidence URL. Only the self-contained presentation gets a short URL.
        if destination == 'voice-screening/report.html':
            shutil.copy2(ROOT / source, target)
            href = 'reports/' + destination
        else:
            href = 'evidence/' + source.as_posix()
        assert (output / href).is_file(), href
        cards.append(f'<a class="card" href="{html.escape(href)}"><small>步骤 {step:02d}</small><h2>{html.escape(title)}</h2><p>{html.escape(description)}</p><span>打开独立 HTML 报告 →</span></a>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Edge AI · 报告</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f6f6;color:#18313b;font:16px/1.75 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:60px 24px}small,span{color:#08776b}h1{font-size:38px;margin:8px 0}header p{color:#536873}nav{display:grid;gap:18px;margin-top:32px}.card{display:block;background:white;border:1px solid #dce5e7;border-radius:16px;padding:25px;color:inherit;text-decoration:none}.card:hover,.card:focus-visible{border-color:#08776b;outline:2px solid #08776b}h2{margin:0;font-size:23px}.card p{color:#536873}footer{margin-top:28px;color:#536873;font-size:14px}
</style><main><header><small>EDGE AI / REPORTS</small><h1>机器人端侧模型报告</h1><p>RK3566 · 按执行流程阅读：模型选型 → 最小推理就绪 → 单模块评测。</p></header><nav aria-label="报告列表">''' + ''.join(cards) + '''</nav><footer>2026-10-22 · 单模块测试不等于完整交互验收。报告按执行顺序排列，详细操作记录保留在仓库。</footer></main></html>'''
    (output / 'index.html').write_text(page)
    # Dedicated entry avoids cached copies of the retired root dashboard.
    (output / 'reports.html').write_text(page)
    (output / '.nojekyll').touch()
    print(f'Built report index and {len(REPORTS)} standalone report entries; no SOP pages rendered.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
