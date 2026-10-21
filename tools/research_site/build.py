"""Build a read-only GitHub Pages site from tracked research and measured JSON."""
import argparse
import html
import json
import os
import re
import shutil
import statistics
import subprocess
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import markdown
from markdown.extensions.toc import slugify_unicode

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).parent
VOICE = Path('studies/voice-interaction')
EXPERIMENT = VOICE / 'experiments/rk3566'


def load(path):
    return json.loads((ROOT / path).read_text())


def measured_data():
    path = EXPERIMENT / '2026-10-21-asr-lite-v1/evaluation/results.json'
    records = load(path)['records']
    groups = {}
    for record in records:
        if record['protocol']['tier'] != 'qualification':
            continue
        key = (record['protocol']['scenario'], record['candidate']['id'])
        groups.setdefault(key, []).append(record)
    comparisons = []
    for (scenario, candidate), rows in sorted(groups.items()):
        values = {}
        for name in ('cpu_capacity_percent', 'peak_pss_mib', 'ram_percent', 'compute_rtf'):
            samples = [
                (r['phases']['inference'] if name != 'compute_rtf' else r['metrics'])[name]['value']
                for r in rows
            ]
            if any(v is None for v in samples):
                raise ValueError('Missing measurement: ' + name)
            values[name] = dict(median=statistics.median(samples), min=min(samples), max=max(samples))
        comparisons.append(dict(scenario=scenario, candidate=candidate, backend=rows[0]['candidate']['backend'], precision=rows[0]['candidate']['precision'], rounds=len(rows), values=values))
    ptq = load(EXPERIMENT / '2026-10-21-asr-int8-ptq/functional-results.json')
    return dict(comparisons=comparisons, quality=ptq['records'], sources=[str(path), str(EXPERIMENT / '2026-10-21-asr-int8-ptq/functional-results.json')])


def build(output):
    output = output.resolve()
    if output.exists():
        raise FileExistsError('Use a new output directory: ' + str(output))
    if output == ROOT or ROOT in output.parents and not output.name.startswith('_site'):
        raise ValueError('Build outside the repository or to an _site* directory')
    tracked = [Path(p) for p in subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines()]
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    docs = [p for p in tracked if p.suffix == '.md' and (p.parts[0] in ('studies', 'docs') or p == Path('README.md'))]
    assets = [p for p in tracked if p.parts[0] == 'studies']
    published = {str(p): 'read/' + str(p.with_suffix('.html')) for p in docs}
    published.update({str(p): 'evidence/' + str(p) for p in assets if p.suffix != '.md'})
    output.mkdir(parents=True)
    shutil.copy2(SOURCE / 'style.css', output / 'style.css')
    shutil.copy2(SOURCE / 'app.js', output / 'app.js')
    (output / '.nojekyll').touch()
    (output / 'data.json').write_text(json.dumps(measured_data(), ensure_ascii=False))
    template = (SOURCE / 'layout.html').read_text()

    def render(destination, title, body, current=''):
        prefix = os.path.relpath(output, (output / destination).parent).replace(os.sep, '/') + '/'
        if prefix == './':
            prefix = ''
        page = template.replace('{{ROOT}}', prefix).replace('{{TITLE}}', html.escape(title)).replace('{{BODY}}', body).replace('{{REVISION}}', revision[:7]).replace('{{CURRENT}}', current)
        target = output / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page)

    entries = []
    for p in docs:
        md = markdown.Markdown(extensions=['extra', 'toc', 'sane_lists'], extension_configs={'toc': {'slugify': slugify_unicode}})
        content = md.convert((ROOT / p).read_text())
        destination = published[str(p)]
        def link(match):
            url = html.unescape(match.group(2))
            if url.startswith(('#', 'https:', 'http:', 'mailto:', 'data:')):
                return match.group(0)
            parts = urlsplit(url)
            target = (ROOT / p.parent / unquote(parts.path)).resolve()
            try:
                rel = str(target.relative_to(ROOT))
            except ValueError:
                return 'data-external-path="' + html.escape(url, quote=True) + '" title="测量时的外部源码路径，不属于本站"'
            if rel in published:
                value = os.path.relpath(output / published[rel], (output / destination).parent)
            else:
                value = 'https://github.com/Shangyizhou/edge-ai/blob/' + revision + '/' + quote(rel)
            if parts.fragment:
                value += '#' + parts.fragment
            return match.group(1) + '="' + html.escape(value, quote=True) + '"'
        content = re.sub(r'(href|src)="([^"]*)"', link, content)
        title = re.search(r'^# (.+)', (ROOT / p).read_text(), re.M)
        title = title.group(1) if title else p.stem
        entries.append(dict(title=title, path=destination))
        render(destination, title, '<article class="document"><a class="back" href="' + os.path.relpath(output / 'index.html', (output / destination).parent) + '">← 返回研究概览</a>' + content + '</article>')
    for p in assets:
        target = output / 'evidence' / p
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / p, target)
    (output / 'search.json').write_text(json.dumps(entries, ensure_ascii=False))
    for name, title in [('index', '研究概览'), ('models', '模型与资源'), ('process', '研究进度'), ('evidence', '资料与证据')]:
        render(name + '.html', title, (SOURCE / (name + '.html')).read_text(), name)
    # Check generated navigation and copied report links, without reaching external services.
    from html.parser import HTMLParser
    failures = []
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key not in ('href', 'src') or not value or value.startswith(('#', 'http:', 'https:', 'data:', 'mailto:')):
                    continue
                path = unquote(urlsplit(value).path)
                if path and not (self.file.parent / path).exists():
                    failures.append((str(self.file.relative_to(output)), value))
    for p in output.rglob('*.html'):
        parser = Links()
        parser.file = p
        parser.feed(p.read_text())
    if failures:
        raise ValueError('Broken links: ' + repr(failures[:20]))
    print(f'Built {len(docs)} readable documents and {len(assets)} evidence assets; local HTML links verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
