"""Import an explicit frozen evaluation batch; never execute models or scoring code."""
import argparse
import hashlib
import json
from pathlib import Path

from paths import ROOT, DEFAULT_HOME
SOURCE = ROOT / 'studies/voice-interaction/experiments/mac/2026-10-24-qwen235-q4-v1'
CANDIDATES = ('adapter', 'merged', 'f16', 'q8', 'q4')



def load_batch():
    paths = [SOURCE / 'comparison.json', SOURCE / 'inputs/system_prompt.txt', SOURCE / 'inputs/tools.json']
    paths += [SOURCE / f'evaluations/{c}/{f}.json' for c in CANDIDATES for f in ('scored-cases', 'summary', 'contextual-review')]
    provenance = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    digest = hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()
    comparison = json.loads(paths[0].read_text())
    cases = {c: json.loads((SOURCE / f'evaluations/{c}/scored-cases.json').read_text()) for c in CANDIDATES}
    reference = cases['f16']
    for c, rows in cases.items():
        assert len(rows) == 50 and len({r['id'] for r in rows}) == 50, c
        assert [(r['id'], r['user'], r['expected'], r['target_content']) for r in rows] == [(r['id'], r['user'], r['expected'], r['target_content']) for r in reference], c
        q = next(x['quality'] for x in comparison if x['candidate'] == c)
        assert sum(bool(r['expected']) for r in rows) == q['tool_samples'] == 27
        assert sum(r['pass'] for r in rows if r['expected']) == q['tool_exact']
        assert sum(bool(r['actual']) for r in rows if not r['expected']) == q['no_call_misroutes']
        assert sum(r['pass'] for r in rows) == q['overall']
    return comparison, cases, provenance, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=DEFAULT_HOME)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    comparison, cases, provenance, digest = load_batch()
    if args.dry_run:
        print(json.dumps({'candidates': list(CANDIDATES), 'cases': 250, 'source_digest': digest}))
        return
    import mlflow
    from mlflow import MlflowClient
    home = args.home.resolve()
    home.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri('sqlite:///' + str(home / 'mlflow.db'))
    client = MlflowClient()
    name = 'edge-ai-qwen-history'
    experiment = client.get_experiment_by_name(name)
    eid = experiment.experiment_id if experiment else client.create_experiment(name, artifact_location=(home / 'artifacts').as_uri())
    bundle = home / 'view'
    bundle.mkdir(exist_ok=True)
    mappings = {}
    for candidate in CANDIDATES:
        origin = 'qwen235-quant-v1:' + candidate + ':mac:development50'
        runs = client.search_runs([eid], filter_string=f"tags.origin_id = '{origin}'")
        if runs:
            assert len(runs) == 1 and runs[0].data.tags.get('source_digest') == digest, 'Source conflict: ' + origin
            assert runs[0].info.status == 'FINISHED', 'Incomplete import; inspect before retry: ' + origin
            mappings[candidate] = runs[0].info.run_id
            continue
        item = next(x for x in comparison if x['candidate'] == candidate)
        q = item['quality']
        with mlflow.start_run(experiment_id=eid, run_name=candidate.upper(), tags={'origin_id': origin, 'source_digest': digest, 'record_kind': 'historical_evaluation', 'device': 'Mac', 'split': 'observed_development50', 'execution_time': 'historical; UI timestamp is import time', 'runtime': 'MLX' if candidate in ('adapter', 'merged') else 'llama.cpp Metal', 'quality_gate': 'not_passed', 'reviewer': q['reviewer']}) as run:
            mappings[candidate] = run.info.run_id
            mlflow.log_params({'candidate': candidate, 'training': 'continuation8 step1408', 'samples': 50, 'tool_samples': 27, 'no_call_samples': 23, 'single_samples': 10, 'model_sha256': item['artifact'].get('sha256', 'see HF adapter reference')})
            mlflow.log_metrics({'single_correct': q['by_focus']['single']['tool_exact'], 'tool_correct': q['tool_exact'], 'no_call_misroutes': q['no_call_misroutes'], 'overall_correct': q['overall'], 'format_correct': q['format'], 'rss_mib': item['resources']['sampled_peak_rss_bytes'] / 1048576, 'single_http_p50_seconds': item['resources']['single_request_complete_seconds_median_n10'], **({'model_bytes': item['artifact']['bytes']} if 'bytes' in item['artifact'] else {})})
            mlflow.log_dict({'sources': provenance, 'source_digest': digest, 'resources_scope': item['resources'], 'historical': True}, 'origin.json')
            table_rows = [{'id': r['id'], 'input': r['user'], 'expected_calls': json.dumps(r['expected'], ensure_ascii=False), 'expected_text': r['target_content'], 'actual_calls': json.dumps(r['actual'], ensure_ascii=False), 'actual_text': r['content'], 'passed': r['pass'], 'errors': ', '.join(r['errors'])} for r in cases[candidate]]
            mlflow.log_table({key: [row[key] for row in table_rows] for key in table_rows[0]}, 'cases.json')
            for filename in ('scored-cases.json', 'summary.json', 'contextual-review.json'):
                mlflow.log_artifact(str(SOURCE / f'evaluations/{candidate}' / filename), artifact_path='frozen')
    # Re-read source hashes after import; fail if any original changed.
    assert load_batch()[3] == digest
    context_path = SOURCE / 'inputs/validation.jsonl'
    contexts = [json.loads(line) for line in context_path.read_text().splitlines() if line.strip()]
    assert {r['id'] for r in contexts} == {r['id'] for r in cases['f16']}
    data = {'comparison': comparison, 'cases': cases, 'runs': mappings, 'experiment_id': eid, 'contexts': {r['id']: [t['function']['name'] for t in r['tools']] for r in contexts}}
    (bundle / 'data.json').write_text(json.dumps(data, ensure_ascii=False))
    template = (Path(__file__).parent / 'view.html').read_text()
    (bundle / 'index.html').write_text(template.replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')))
    report = {'source_digest': digest, 'sources': provenance, 'runs': mappings, 'cases': 250, 'source_unchanged': True, 'mlflow_version': mlflow.__version__, 'experiment_id': eid, 'view_context_sha256': hashlib.sha256(context_path.read_bytes()).hexdigest()}
    (home / 'import-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if (home / 'lineage-import.json').exists():
        from build_dashboard import render
        render(home)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
