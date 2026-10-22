"""Build current skill-flow pages without importing archived measurements."""
import argparse
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import quote, unquote, urlsplit

import markdown
from markdown.extensions.toc import slugify_unicode

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).parent
VOICE = Path('studies/voice-interaction')


def measured_data():
    """Expose only current source pointers; comparisons remain in their reports."""
    experiment = VOICE / 'experiments/rk3566'
    paths = [p.relative_to(ROOT) for p in sorted((ROOT / experiment).glob('2026-10-22-*/results.json'))]
    return dict(scope='current_skill_flow', sources=[str(p) for p in paths],
                note='Different schemas and timing scopes are not pooled.')


def source_files():
    """Include local current work too; excluded history lives outside the repo."""
    files = {p.relative_to(ROOT) for p in ROOT.glob('*.md')}
    files.update(p.relative_to(ROOT) for p in (ROOT / 'tools').rglob('*.md'))
    files.update(p.relative_to(ROOT) for p in (ROOT / 'tools/edge_benchmark/schemas').glob('*.json'))
    for folder in ('studies', 'docs', 'archives'):
        files.update(p.relative_to(ROOT) for p in (ROOT / folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts
                     and p.suffix not in ('.pyc', '.pyo'))
    return sorted(files)


def build(output):
    output = output.resolve()
    if output.exists():
        raise FileExistsError('Use a new output directory: ' + str(output))
    if output == ROOT or ROOT in output.parents and not output.name.startswith('_site'):
        raise ValueError('Build outside the repository or to an _site* directory')
    files = source_files()
    docs = [p for p in files if p.suffix == '.md']
    assets = [p for p in files if p.suffix != '.md']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    display_revision = revision[:7] + ('-local' if dirty else '')
    aliases = {
        'index': ('当前结论', VOICE / 'README.md'),
        'solutions': ('我们怎么选', VOICE / 'research/README.md'),
        'models': ('模型与测试', VOICE / 'models.md'),
        'integration': ('接入边界', VOICE / 'integration.md'),
        'process': ('准备与推进', VOICE / 'plan.md'),
        'evidence': ('实验与证据', VOICE / 'experiments/rk3566/README.md'),
        'learn': ('从这里读起', VOICE / 'learn.md'),
        'quantization': ('量化与转换', VOICE / 'quantization.md'),
        'deployment': ('部署与训练交接', VOICE / 'deployment-guide.md'),
    }
    published = {str(p): 'read/' + str(p.with_suffix('.html')) for p in docs}
    published.update({str(p): 'evidence/' + str(p) for p in assets})
    output.mkdir(parents=True)
    for name in ('style.css', 'app.js'):
        shutil.copy2(SOURCE / name, output / name)
    (output / '.nojekyll').touch()
    (output / 'data.json').write_text(json.dumps(measured_data(), ensure_ascii=False))
    template = (SOURCE / 'layout.html').read_text()

    def render(destination, title, body, current=''):
        prefix = os.path.relpath(output, (output / destination).parent).replace(os.sep, '/') + '/'
        if prefix == './':
            prefix = ''
        page = template.replace('{{ROOT}}', prefix).replace('{{TITLE}}', html.escape(title)).replace('{{BODY}}', body).replace('{{REVISION}}', display_revision).replace('{{CURRENT}}', current)
        target = output / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page)

    def document(path, destination, current=''):
        text = (ROOT / path).read_text()
        md = markdown.Markdown(extensions=['extra', 'toc', 'sane_lists'], extension_configs={'toc': {'slugify': slugify_unicode}})
        content = md.convert(text)

        def link(match):
            url = html.unescape(match.group(2))
            if url.startswith(('#', 'https:', 'http:', 'mailto:', 'data:')):
                return match.group(0)
            parts = urlsplit(url)
            target = (ROOT / path.parent / unquote(parts.path)).resolve()
            try:
                relative = str(target.relative_to(ROOT))
            except ValueError:
                return 'data-external-path="' + html.escape(url, quote=True) + '" title="原始记录的本机路径，未随网站发布"'
            if relative in published:
                value = os.path.relpath(output / published[relative], (output / destination).parent)
            elif target.is_dir():
                value = 'https://github.com/Shangyizhou/edge-ai/tree/' + revision + '/' + quote(relative)
            elif 'sources' in path.parts:
                # Frozen upstream excerpts do not include the upstream directory tree.
                return 'data-source-relative="' + html.escape(url, quote=True) + '" title="上游来源快照的相对路径；完整上游文档见来源链接"'
            else:
                raise ValueError('Unpublished or missing current link: ' + str(path) + ' -> ' + url)
            if parts.fragment:
                value += '#' + parts.fragment
            return match.group(1) + '="' + html.escape(value, quote=True) + '"'

        content = re.sub(r'(href|src)="([^"]*)"', link, content)
        title = re.search(r'^# (.+)', text, re.M)
        title = title.group(1) if title else path.stem
        render(destination, title, '<article class="document"><a class="back" href="' + os.path.relpath(output / 'index.html', (output / destination).parent) + '">← 当前结论</a>' + content + '</article>', current)
        return title

    entries = []
    for path in docs:
        destination = published[str(path)]
        entries.append(dict(title=document(path, destination), path=destination))
    # Raw Markdown accompanies frozen HTML that links to README.md directly.
    for path in files:
        target = output / 'evidence' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, target)
    for name, (title, path) in aliases.items():
        document(path, name + '.html', name)
    (output / 'search.json').write_text(json.dumps(entries, ensure_ascii=False))
    failures = []

    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key not in ('href', 'src') or not value or value.startswith(('#', 'http:', 'https:', 'data:', 'mailto:', 'file:', '/')):
                    continue
                path = unquote(urlsplit(value).path)
                if path and not (self.file.parent / path).exists():
                    failures.append((str(self.file.relative_to(output)), value))

    for path in output.rglob('*.html'):
        relative_parts = path.relative_to(output).parts
        if relative_parts[0] == 'evidence' and 'sources' in relative_parts:
            continue  # Captured upstream HTML is evidence, not a mirrored site.
        parser = Links()
        parser.file = path
        parser.feed(path.read_text())
    if failures:
        raise ValueError('Broken links: ' + repr(failures[:20]))
    print(f'Built {len(docs)} current documents and {len(assets)} assets; local HTML links verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
