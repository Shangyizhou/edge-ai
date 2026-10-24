"""Version-card provenance and remote-review boundary checks, without model execution."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import release


@unittest.skipUnless((release.RELEASES/'current.json').exists(), 'private historical evidence is restored separately')
class ReleaseTests(unittest.TestCase):
    def test_chosen_weights_and_status_remain_distinct(self):
        r,records,decisions,_=release.load_release()
        self.assertEqual(r['statuses']['selection_status'],'user_selected_with_limits')
        self.assertEqual(r['statuses']['validation_status'],'development_gates_not_passed')
        model=records[r['selected_model_id']]
        self.assertEqual(model['origin_key'],'export:q4')
        self.assertEqual(model['reference']['artifact']['files'][0]['sha256'],'e5e283a9285ffb8f3fd2539fec3e4734474c8a5b0ba42ae4a586c1188df325c6')
        self.assertEqual(len(decisions),2)
        self.assertEqual(r['hf_references']['selected_q4']['publication_status'],'not_published')

    def test_remote_card_has_no_local_or_runtime_links(self):
        r,records,decisions,_=release.load_release()
        text=release.card(r,records,decisions,local=False)
        for forbidden in ['127.0.0.1','localhost','/Users/syz/']:
            self.assertNotIn(forbidden,text)
        self.assertIn(r['hf_references']['dataset']['commit'],text)
        self.assertIn('20/27',text)
        self.assertIn('11/23',text)
        self.assertIn('尚未上传HF',text)

    def test_invalid_model_reference_stops_generation(self):
        r,_,_,_=release.load_release()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'r1').mkdir();r['selected_model_id']='missing-model'
            (root/'current.json').write_text(json.dumps({'release_id':r['release_id'],'path':'r1/release.json'}))
            (root/'r1/release.json').write_text(json.dumps(r))
            with patch.object(release,'RELEASES',root):
                with self.assertRaises(AssertionError):release.load_release()


if __name__=='__main__':unittest.main()
