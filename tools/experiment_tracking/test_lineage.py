from pathlib import Path
"""Evidence invariants, not model or scoring tests."""
import unittest
from import_lineage import normalize


@unittest.skipUnless((Path(__file__).resolve().parents[2]/'studies/voice-interaction/experiments/mac/2026-10-23-qwen235-continuation8-v1/training/results.json').exists(), 'private historical evidence is restored separately')
class LineageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources, cls.trains, cls.evals, cls.stop, cls.exports, _, cls.old, cls.board = normalize()

    def test_checkpoints_are_unique_and_old_epochs_preserved(self):
        checkpoints = [c for t in self.trains for c in t['checkpoints']]
        self.assertEqual(len(checkpoints), 30)
        self.assertEqual(len({c['sha256'] for c in checkpoints}), 30)
        old = next(t for t in self.trains if t['key']=='xiaomo235-3epochs')
        self.assertEqual([(c['epoch'], c['step']) for c in old['checkpoints']], [(1,232),(2,464),(3,696)])
        selected = next(t for t in self.trains if t['key']=='continuation8')
        self.assertEqual([c['step'] for c in selected['checkpoints']], [696,1408])

    def test_warmstart_is_not_fresh_base(self):
        prior = next(t for t in self.trains if t['key']=='original195')
        warm = next(t for t in self.trains if t['key']=='original195-epoch3-warmstart')
        self.assertEqual(warm['result']['config']['resume_adapter_file'], prior['checkpoints'][-1]['path'])
        self.assertEqual(warm['result']['microsteps'], 192)

    def test_quantized_and_board_model_identity(self):
        selected = next(t for t in self.trains if t['key']=='continuation8')['checkpoints'][-1]
        exported = self.exports[0]['artifacts']['adapter']['files']
        self.assertEqual(next(f['sha256'] for f in exported if f['name']=='adapters.safetensors'), selected['sha256'])
        self.assertEqual(self.exports[0]['artifacts']['f16'], self.exports[1]['artifacts']['f16'])
        self.assertEqual(self.board['model_sha256'],self.exports[0]['artifacts']['q4']['files'][0]['sha256'])

    def test_stop_and_split_boundaries(self):
        self.assertEqual(self.stop['stop']['actual_updates'],13)
        self.assertTrue(self.stop['stop']['no_final_candidate_evaluation'])
        self.assertTrue(all(e['split'] in ('observed_development','seen_train_replay') for e in self.evals))
        self.assertTrue(all('sealed' not in p.lower() and 'private-test' not in p.lower() for p in self.sources.hashes))
        self.assertTrue(self.sources.unchanged())


if __name__ == '__main__':
    unittest.main()
