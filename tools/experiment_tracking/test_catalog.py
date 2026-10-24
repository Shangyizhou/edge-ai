"""Catalog relation integrity and presentation independence from migration caches."""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from catalog import CATALOG, DEFAULT_HOME, read_index, load_view
from build_dashboard import render


@unittest.skipUnless((CATALOG/'index.json').exists(), 'private historical evidence is restored separately')
class CatalogTests(unittest.TestCase):
    def test_complete_stable_graph(self):
        _,records=read_index()
        self.assertEqual({k:sum(r['kind']==k for r in records.values()) for k in ['dataset','training','model','evaluation']},{'dataset':10,'training':14,'model':41,'evaluation':31})
        stopped=[r for r in records.values() if r['kind']=='training' and r['execution_summary']['status']=='USER_STOPPED']
        self.assertEqual(stopped[0]['execution_summary']['optimizer_updates'],13)
        binding=json.loads((DEFAULT_HOME/'bindings/catalog-mlflow.json').read_text())
        content=json.dumps(records)
        for r in binding['records'].values():
            for field in ['run_id','model_id']:
                if field in r:self.assertNotIn(r[field],content)

    def test_no_legacy_cache_needed_for_views(self):
        with tempfile.TemporaryDirectory() as t:
            home=Path(t);(home/'bindings').mkdir();shutil.copy2(DEFAULT_HOME/'bindings/catalog-mlflow.json',home/'bindings/catalog-mlflow.json')
            lineage,quant,cases,_,_=load_view(home)
            self.assertEqual(len(lineage['training_keys']),13)
            self.assertEqual(sum(len(r) for r in quant['cases'].values()),250)
            self.assertEqual(len(cases),29)
            render(home)
            for name in ['index.html','lineage.html','cases.html','comparison.html']:self.assertTrue((home/'view'/name).is_file())
            self.assertFalse((home/'lineage-import.json').exists())

    def test_dangling_parent_rejected_even_with_updated_hash(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'catalog';shutil.copytree(CATALOG,root)
            index=json.loads((root/'index.json').read_text());entry=next(e for e in index['records'] if e['kind']=='model');path=root/entry['path'];record=json.loads(path.read_text());record['parent_ids']=['missing-model'];blob=json.dumps(record).encode();path.write_bytes(blob);entry['sha256']=hashlib.sha256(blob).hexdigest();(root/'index.json').write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError,'Dangling'):read_index(root)


if __name__=='__main__':unittest.main()
