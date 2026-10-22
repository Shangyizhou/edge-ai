"""Add navigation to published copies, leaving experiment HTML unchanged."""
import html
from html.parser import HTMLParser
import os
import re


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def add_navigation(page, destination, output, reports):
    headings = []
    used_ids = set(re.findall(r'\bid=[\"\']([^\"\']+)', page))

    def heading(match):
        level, attrs, content = match.groups()
        existing = re.search(r'\bid=[\"\']([^\"\']+)', attrs)
        anchor = existing.group(1) if existing else 'report-heading-' + str(len(headings) + 1)
        if not existing:
            while anchor in used_ids:
                anchor += '-next'
            attrs += ' id="' + anchor + '"'
            used_ids.add(anchor)
        text = Text()
        text.feed(content)
        headings.append((level, anchor, ''.join(text.parts).strip()))
        return f'<h{level}{attrs}>{content}</h{level}>'

    # Replace the accepted report's previous rail with the shared navigation.
    page = re.sub(r'<nav\b[^>]*class="rail"[^>]*>.*?</nav>', '', page, flags=re.S)
    page = re.sub(r'<h([123])\b([^>]*)>(.*?)</h\1>', heading, page, flags=re.S | re.I)

    def relative(target):
        return html.escape(os.path.relpath(output / target, destination.parent).replace(os.sep, '/'), quote=True)

    links = ''.join(f'<a class="rn-level-{level}" href="#{html.escape(anchor, quote=True)}">{html.escape(title)}</a>'
                    for level, anchor, title in headings if level != '1' or len(headings) == 1)
    catalog = ''.join(f'<a href="{relative(path)}">{step:02d} · {html.escape(title)}</a>'
                      for step, (path, title) in enumerate(reports, 1))
    navigation = f'''<aside id="report-navigation" aria-label="报告导航"><details open><summary>报告导航</summary><div class="rn-content"><a href="{relative('reports.html')}">← 报告列表</a><h2>执行流程</h2><nav aria-label="切换报告">{catalog}</nav><h2>本页目录</h2><nav aria-label="章节跳转">{links}</nav><a href="#" class="rn-top">↑ 返回顶部</a></div></details></aside>'''
    style = '''<style id="report-navigation-style">
html{scroll-behavior:smooth;scroll-padding-top:24px}body{padding-right:270px!important}h1,h2,h3{scroll-margin-top:24px}body>.rail{display:none!important}
#report-navigation{position:fixed!important;inset:0 0 0 auto!important;width:250px!important;height:100vh;overflow:auto;box-sizing:border-box;background:#fbfcfc;color:#18313b;border:0;border-left:1px solid #dce5e7;border-radius:0;padding:24px 18px;margin:0;z-index:100;font:14px/1.6 system-ui,sans-serif;text-align:left}
#report-navigation summary{cursor:pointer;font-weight:700;font-size:17px}#report-navigation h2{font:700 13px/1.6 system-ui,sans-serif;color:#536873;margin:24px 8px 8px}#report-navigation nav{display:block;margin:0;padding:0;border:0;background:none}#report-navigation a{display:block;color:#36535b;text-decoration:none;border-radius:7px;padding:7px 9px;margin:3px 0;overflow-wrap:anywhere}#report-navigation a:hover,#report-navigation a:focus-visible{background:#e2f1ed;color:#066457}#report-navigation a[aria-current="location"]{background:#e2f1ed;color:#066457;font-weight:700}#report-navigation .rn-level-3{font-size:12px;padding-left:20px}#report-navigation .rn-top{margin-top:20px}
@media(min-width:901px){#report-navigation summary{display:none}}
@media(max-width:900px){body{padding-right:0!important;padding-top:65px!important}#report-navigation{inset:0 0 auto!important;width:100%!important;height:auto;max-height:75vh;border-left:0;border-bottom:1px solid #dce5e7;padding:12px 18px}#report-navigation .rn-content{max-height:60vh;overflow:auto}html{scroll-padding-top:80px}h1,h2,h3{scroll-margin-top:80px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
</style>'''
    script = '''<script>(function(){const rail=document.getElementById('report-navigation'),details=rail.querySelector('details'),mobile=matchMedia('(max-width:900px)');function layout(){details.open=!mobile.matches}layout();mobile.addEventListener('change',layout);rail.addEventListener('click',e=>{if(e.target.closest('a')&&mobile.matches)details.open=false});if('IntersectionObserver' in window){const links=[...rail.querySelectorAll('a[href^="#report-heading-"]')];const observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){links.forEach(a=>{if(a.hash==='#'+entry.target.id)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current')})}},{rootMargin:'-5% 0px -65% 0px'});links.forEach(a=>{const target=document.getElementById(a.hash.slice(1));if(target)observer.observe(target)})}})();</script>'''
    page = re.sub(r'</head>', lambda _: style + '</head>', page, count=1, flags=re.I)
    if '</body>' in page:
        return page.replace('</body>', navigation + script + '</body>', 1)
    return page + style + navigation + script
