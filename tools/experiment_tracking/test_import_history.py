from pathlib import Path
"""Read-only regression checks on the explicit frozen batch."""
import unittest
from import_history import load_batch


@unittest.skipUnless((Path(__file__).resolve().parents[2]/'studies/voice-interaction/experiments/mac/2026-10-24-qwen235-q4-v1/comparison.json').exists(), 'private historical evidence is restored separately')
class HistoryTest(unittest.TestCase):
    def test_frozen_scores_and_identity(self):
        comparison, cases, sources, digest = load_batch()
        self.assertEqual(len(cases), 5)
        self.assertEqual(sum(map(len, cases.values())), 250)
        expected = {'f16': (24, 4), 'q8': (24, 5), 'q4': (20, 11)}
        for row in comparison:
            if row['candidate'] in expected:
                self.assertEqual((row['quality']['tool_exact'], row['quality']['no_call_misroutes']), expected[row['candidate']])
        self.assertEqual(len(digest), 64)
        self.assertEqual(len(sources), 18)
        self.assertTrue(all('2026-10-24-qwen235-q4-v1' in p for p in sources))


if __name__ == '__main__':
    unittest.main()
