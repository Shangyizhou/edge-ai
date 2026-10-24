"""Public, synthetic metadata checks: no private dataset, MLflow or model required."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import catalog
import release


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write_catalog(self, rows):
        entries=[]
        for row in rows:
            name=row['id']+'.json';blob=json.dumps(row).encode();(self.root/name).write_bytes(blob)
            entries.append({'id':row['id'],'kind':row['kind'],'path':name,'sha256':hashlib.sha256(blob).hexdigest()})
        (self.root/'index.json').write_text(json.dumps({'schema':'edge-ai/catalog-index-v1','records':entries}))

    def test_stable_identity_not_database_identity(self):
        self.assertEqual(catalog.stable_id('model','same-weight-hash'),catalog.stable_id('model','same-weight-hash'))
        self.assertNotEqual(catalog.stable_id('model','a'),catalog.stable_id('model','b'))

    def test_valid_graph(self):
        self.write_catalog([{'id':'dataset-a','kind':'dataset','digest':'a'*64,'sample_count':1},{'id':'model-a','kind':'model','identity':'fixed-artifact','artifact_type':'base_weights','parent_ids':[]}])
        _,rows=catalog.read_index(self.root);self.assertEqual(len(rows),2)

    def test_hash_change_rejected(self):
        self.write_catalog([{'id':'dataset-a','kind':'dataset','digest':'a'*64,'sample_count':1}]);(self.root/'dataset-a.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):catalog.read_index(self.root)

    def test_dangling_relation_rejected(self):
        self.write_catalog([{'id':'model-a','kind':'model','identity':'a','artifact_type':'base_weights','parent_ids':['missing']}])
        with self.assertRaisesRegex(ValueError,'Dangling'):catalog.read_index(self.root)

    def test_cycle_rejected(self):
        self.write_catalog([{'id':'model-a','kind':'model','identity':'a','artifact_type':'weights','parent_ids':['model-b']},{'id':'model-b','kind':'model','identity':'b','artifact_type':'weights','parent_ids':['model-a']}])
        with self.assertRaisesRegex(ValueError,'Cyclic'):catalog.read_index(self.root)

    def test_index_path_escape_rejected(self):
        (self.root/'index.json').write_text(json.dumps({'records':[{'path':'../elsewhere.json'}]}))
        with self.assertRaisesRegex(ValueError,'escapes'):catalog.read_index(self.root)

    def test_record_identity_mismatch_rejected(self):
        self.write_catalog([{'id':'dataset-a','kind':'dataset','digest':'a'*64,'sample_count':1}]);idx=json.loads((self.root/'index.json').read_text());idx['records'][0]['id']='different';(self.root/'index.json').write_text(json.dumps(idx))
        with self.assertRaisesRegex(ValueError,'identity mismatch'):catalog.read_index(self.root)

    def test_html_escapes_content_and_preserves_links(self):
        text=release.markdown_html('# Example\n\n<script>alert(1)</script>\n\n[Evidence](https://example.org)')
        self.assertNotIn('<script>',text);self.assertIn('&lt;script&gt;',text);self.assertIn('href="https://example.org"',text)

    def test_release_source_path_escape_rejected(self):
        (self.root/'current.json').write_text(json.dumps({'path':'../private.json'}))
        with patch.object(release,'RELEASES',self.root):
            with self.assertRaisesRegex(ValueError,'escapes'):release.load_release()


if __name__=='__main__':unittest.main()
