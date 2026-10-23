"""Publish only explicit curated report files; never traverse study evidence."""

import argparse
import hashlib
import html
import json
import shutil
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path("tools/research_site/publication.json")
ALLOWED = {
    ".html",
    ".svg",
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".json",
}


def confined(base, value):
    value = unquote(value)
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or "\\" in value
        or not value
        or urlsplit(value).scheme
    ):
        raise ValueError("unsafe publication path")
    target = (base / str(relative)).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        raise ValueError("publication path escapes root")
    return target


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ("href", "src", "poster", "xlink:href") and value:
                self.links.append((tag, key, value))


def validate_html(path, output):
    text = path.read_text()
    if any(
        s in text
        for s in (
            "file://",
            "/Users/",
            "/home/orangepi/",
            "data:application/",
            "data:audio/",
        )
    ):
        raise ValueError(
            "local/private evidence reference in public report: " + str(path)
        )
    parser = Links()
    parser.feed(text)
    for tag, key, value in parser.links:
        url = urlsplit(value)
        if value.startswith("#"):
            continue
        if url.scheme in ("https", "http"):
            if tag != "a" or key != "href":
                raise ValueError("network resource required by offline report")
            continue
        if value.startswith("data:image/"):
            continue
        if url.scheme or url.netloc or value.startswith("/"):
            raise ValueError("unsupported public link")
        target = (path.parent / unquote(url.path)).resolve()
        try:
            target.relative_to(output.resolve())
        except ValueError:
            raise ValueError("link escapes published site")
        if not target.is_file():
            raise ValueError("broken public link: " + value)


def build(output, root=None):
    root = Path(root or ROOT).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("use a fresh output directory")
    if (
        output == root
        or root in output.parents
        and not output.name.startswith("_site")
    ):
        raise ValueError("build outside repo or to _site*")
    manifest = json.loads((root / MANIFEST).read_text())
    if manifest.get("schema") != "edge-ai-publication/v1":
        raise ValueError("unsupported publication schema")
    plan = []
    destinations = set()
    for row in manifest["files"]:
        source = confined(root, row["source"])
        target = confined(output, row["destination"])
        try:
            source.relative_to(
                (root / "studies/voice-interaction/reports").resolve()
            )
        except ValueError:
            raise ValueError("only curated reports may be published")
        if source.suffix not in ALLOWED or not source.is_file():
            raise ValueError("unsupported report file")
        if target.relative_to(
            output
        ).as_posix() in destinations or target.name in (
            "index.html",
            "reports.html",
            ".nojekyll",
        ):
            raise ValueError("duplicate or reserved publication destination")
        destinations.add(target.relative_to(output).as_posix())
        if hashlib.sha256(source.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(
                "public source changed; regenerate publication manifest"
            )
        plan.append((source, target))
    aliases = manifest.get("aliases", {})
    for name, dest in aliases.items():
        confined(output, name)
        confined(output, dest)
        if name in destinations or name in ("index.html", "reports.html"):
            raise ValueError("alias overwrites report")
        if dest not in destinations:
            raise ValueError("alias target is not published")
    for card in manifest["catalog"]:
        if card["href"] not in destinations:
            raise ValueError("catalog points outside manifest")
    output.mkdir(parents=True)
    for source, target in plan:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for name, dest in aliases.items():
        target = confined(output, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        import os

        href = os.path.relpath(confined(output, dest), target.parent)
        target.write_text(
            '<!doctype html><meta charset="utf-8"><title>报告入口已整理</title><p><a href="'
            + html.escape(href)
            + '">打开当前公开报告</a></p>'
        )
    cards = "".join(
        '<a class="card" href="'
        + html.escape(row["href"])
        + '"><h2>'
        + html.escape(row["title"])
        + "</h2><p>"
        + html.escape(row["description"])
        + "</p></a>"
        for row in manifest["catalog"]
    )
    page = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Edge AI 报告</title><style>body{font:16px/1.8 system-ui;background:#f3f6f7;color:#203b43;max-width:960px;margin:50px auto;padding:24px}.card{display:block;background:white;border:1px solid #dce5e7;border-radius:10px;padding:24px;margin:20px 0;color:inherit;text-decoration:none}h2{margin:0}a:focus-visible{outline:3px solid #087f77}</style><h1>端侧模型研究与工作流</h1><p>正式模型结论与工作流技术示例分开阅读。公开报告不自动包含原始实验、录音或内部文件。</p>'
        + cards
        + "</html>"
    )
    for name in ("index.html", "reports.html"):
        (output / name).write_text(page)
    (output / ".nojekyll").touch()
    for path in output.rglob("*.html"):
        validate_html(path, output)
    print(
        "Built",
        len(plan),
        "explicit public files;",
        len(manifest["catalog"]),
        "topic entries; no evidence traversal.",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.output)
