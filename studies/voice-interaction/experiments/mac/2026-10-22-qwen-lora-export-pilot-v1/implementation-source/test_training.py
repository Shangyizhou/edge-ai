"""Observable data, mask and stage-report invariants, without GPU work."""

import tempfile
import unittest
import json
import os
import threading
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from pathlib import Path

from .training import prepare_samples, validate_splits
from .stages import check_export_request, render_stages
from .runners import LlamaHttpRunner


class Tokenizer:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs['enable_thinking'] is False
        assert kwargs['return_dict'] is False
        prefix = [1, 2, 3]
        return prefix if kwargs.get('add_generation_prompt') else prefix + [4, 5]

    def decode(self, tokens):
        return str(tokens)


def sample(identity='a', group='train'):
    return {'id': identity, 'source_group': group, 'tools': [], 'messages': [
        {'role': 'user', 'content': '介绍你自己'},
        {'role': 'assistant', 'content': '我是小沫。'}]}


class TrainingTests(unittest.TestCase):
    def test_no_silent_truncation_and_exact_nonthinking_prefix(self):
        data, proof = prepare_samples([sample()], Tokenizer(), 5)
        self.assertEqual(data[0], ([1, 2, 3, 4, 5], 3))
        self.assertEqual(proof[0]['target_tokens'], 2)
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            prepare_samples([sample()], Tokenizer(), 4)

    def test_source_groups_cannot_leak_between_train_and_validation(self):
        with self.assertRaisesRegex(ValueError, 'source_group'):
            validate_splits([sample()], [sample('b')])
        valid = sample('b', 'valid')
        valid['messages'][0]['content'] = '你叫什么名字'
        validate_splits([sample()], [valid])

    def test_training_target_rejects_unknown_tool(self):
        record = sample()
        record['messages'][-1] = {'role': 'assistant', 'tool_calls': [
            {'type': 'function', 'function': {'name': 'invented', 'arguments': {}}}]}
        with self.assertRaisesRegex(ValueError, 'unknown tool'):
            prepare_samples([record], Tokenizer(), 10)

    def test_export_is_explicit_and_stage_report_does_not_execute(self):
        with self.assertRaises(ValueError):
            check_export_request({'schema': 'edge-model-export/request-v1',
                                  'run_id': 'x', 'operations': []})
        record = {'schema': 'edge-model-export/result-v1', 'run_id': '<x>',
                  'status': 'failed', 'stages': [{'operation': 'convert',
                    'status': 'failed', 'wall_seconds': 2,
                    'command': ['unused'], 'error': '<bad>'}]}
        page = render_stages([record])
        self.assertIn('&lt;bad&gt;', page)
        self.assertNotIn('<bad>', page)
        self.assertIn('failed', page)

    def test_local_http_transport_does_not_use_environment_proxy(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                wire = {'choices': [{'delta': {'content': '你好'},
                                     'finish_reason': 'stop'}]}
                data = ('data: '+json.dumps(wire)+'\n\ndata: [DONE]\n\n').encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with patch.dict(os.environ, {'http_proxy': 'http://127.0.0.1:9',
                                         'no_proxy': ''}):
                runner = LlamaHttpRunner({'candidate': {}, 'runner': {
                    'endpoint': 'http://127.0.0.1:'+str(server.server_port)}})
                reply = runner.generate([{'role':'user','content':'你好'}],
                                        [], {}, lambda event: None)
                self.assertEqual(reply['raw'], '你好')
                self.assertEqual(reply['finish_reason'], 'stop')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_failed_transform_preserves_evidence_and_cli_returns_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = {'schema': 'edge-model-export/request-v1', 'run_id': 'failure',
                       'artifacts': {}, 'operations': [{'kind': 'convert',
                        'inputs': [], 'output': {'id':'absent', 'path':str(root/'model')},
                        'command': [sys.executable, '-c',
                                    'import time; time.sleep(.2); raise SystemExit(3)']}]}
            request_path = root / 'request.json'
            request_path.write_text(json.dumps(request))
            completed = subprocess.run([sys.executable, '-m', 'tools.qwen_lifecycle',
                                       'export', str(request_path), str(root/'run')],
                                      capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 1)
            result = json.loads((root/'run/results.json').read_text())
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['stages'][0]['exit_code'], 3)
            self.assertTrue((root/'run/00-convert.log').exists())


if __name__ == '__main__':
    unittest.main()
