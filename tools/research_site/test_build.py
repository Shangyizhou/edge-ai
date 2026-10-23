"""Offline publication boundary; no server or deployment needed."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import build
from report_navigation import add_navigation


class PublicationBoundaryTests(unittest.TestCase):
    def test_offline_trees_pruned_and_existing_catalog_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'repository'
            root.mkdir()
            # Populate every excluded prefix, including the future final run.
            for prefix in build.UNPUBLISHED_DIRECTORIES:
                for name in ('nested/result.json', 'nested/report.html',
                             'nested/sources/upstream.html', 'nested/source.py'):
                    target = root / prefix / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text('offline evidence')
            for _, _, _, source in build.REPORTS:
                target = root / source
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((build.ROOT / source).read_bytes())
            public = root / build.VOICE / 'experiments/rk3566/public/raw.json'
            public.parent.mkdir(parents=True)
            public.write_text('{"public": true}')
            output = Path(temporary) / 'site'
            with patch.object(build, 'ROOT', root):
                build.build(output)
            for prefix in build.UNPUBLISHED_DIRECTORIES:
                self.assertFalse((output / 'evidence' / prefix).exists(), prefix)
            self.assertEqual((output / 'evidence' / public.relative_to(root)).read_bytes(),
                             public.read_bytes())
            catalog = [('evidence/' + source.as_posix() if destination != 'voice-screening/report.html'
                        else 'reports/' + destination, title)
                       for destination, title, _, source in build.REPORTS]
            self.assertEqual(len(catalog), 3)
            for href, _ in catalog:
                target = output / href
                self.assertTrue(target.is_file(), href)
                source = (root / href.removeprefix('evidence/') if href.startswith('evidence/')
                          else root / build.REPORTS[2][3])
                self.assertEqual(target.read_text(), add_navigation(
                    source.read_text(), target, output, catalog))
                self.assertIn(href, (output / 'reports.html').read_text())


if __name__ == '__main__':
    unittest.main()
