"""Render comparison-first local pages from existing imported records; no MLflow writes."""
import hashlib
import json
from pathlib import Path
from import_history import DEFAULT_HOME


def render(home=DEFAULT_HOME):
    directory = home / 'view'
    directory.mkdir(parents=True,exist_ok=True)
    from catalog import load_view
    lineage,quant,case_records,run_ids,training_facts=load_view(home)
    case_records = {key:[{field:row.get(field) for field in ('id','user','expected','actual','target_content','content','pass','errors')} for row in rows] for key,rows in case_records.items()}
    data = {'run_labels':run_ids,'training_facts':training_facts,'lineage':lineage,'quant':{key:quant[key] for key in ('comparison','runs','contexts')},'case_records':case_records}
    template = Path(__file__).parent
    for filename in ('dashboard.html','cases.html'):
        page_data = data if filename=='cases.html' else {**data,'case_records':{key:True for key in case_records}}
        content = (template / filename).read_text().replace('__DATA__',json.dumps(page_data,ensure_ascii=False).replace('<','\\u003c'))
        (directory / ('index.html' if filename=='dashboard.html' else filename)).write_text(content)
    (directory / 'lineage.html').write_text((template/'lineage.html').read_text().replace('__DATA__',json.dumps(lineage,ensure_ascii=False).replace('<','\\u003c')))
    (directory / 'comparison.html').write_text((template/'view.html').read_text().replace('__DATA__',json.dumps(quant,ensure_ascii=False).replace('<','\\u003c')))
    from release import RELEASES, generate
    if (RELEASES/'current.json').exists():generate(home)
    print(json.dumps({'training_rows':len(lineage['training_keys']),'evaluation_rows':len(lineage['evaluations'])+len(quant['comparison']),'case_tables':len(case_records),'database_writes':0}))


if __name__=='__main__':
    render()
