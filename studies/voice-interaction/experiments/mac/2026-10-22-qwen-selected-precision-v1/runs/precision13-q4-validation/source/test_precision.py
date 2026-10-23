"""Pairing and local lifecycle safety at observable boundaries."""

import copy
import tempfile
import unittest
from pathlib import Path

from .mac_run import execute
from .precision_report import paired, render


class PrecisionTests(unittest.TestCase):
    def test_pairing_rejects_prompt_or_target_drift(self):
        original = {'cases': [{'id': 'x', 'user': '你好',
                               'expected': {}, 'messages': []}]}
        paired([original, copy.deepcopy(original)])
        for key, value in [('user', '别的输入'), ('expected', {'kind': 'chat'}),
                           ('messages', [{'role': 'system', 'content': 'facts'}])]:
            changed = copy.deepcopy(original)
            changed['cases'][0][key] = value
            with self.assertRaisesRegex(ValueError, 'unpaired'):
                paired([original, changed])

    def test_report_requires_contextual_persona_review(self):
        result = {'run_id': 'real', 'cases': [{'id': 'p', 'user': '姓名',
                  'expected': {}, 'messages': [], 'kind': 'persona'}]}
        with self.assertRaisesRegex(ValueError, 'contextual review'):
            render([result], {'cases': []}, [], {})

    def test_mac_launcher_rejects_remote_or_model_override(self):
        with tempfile.TemporaryDirectory() as directory:
            for i, argument in enumerate(['--host=0.0.0.0', '-m', '--hf-repo=x']):
                with self.assertRaises(ValueError):
                    execute({'server': {'argv': [argument], 'binary': 'forbidden'}},
                            Path(directory)/str(i))


if __name__ == '__main__':
    unittest.main()
