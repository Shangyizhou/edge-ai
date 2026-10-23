"""Publication allowlist and offline link checks."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.research_site import build


class PublicationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.source = (
            self.root / "studies/voice-interaction/reports/example/report.html"
        )
        self.source.parent.mkdir(parents=True)
        self.source.write_text("<html><h1>Public</h1></html>")
        self.manifest = {
            "schema": "edge-ai-publication/v1",
            "files": [
                {
                    "source": str(self.source.relative_to(self.root)),
                    "destination": "reports/example/report.html",
                    "sha256": hashlib.sha256(
                        self.source.read_bytes()
                    ).hexdigest(),
                }
            ],
            "catalog": [
                {
                    "href": "reports/example/report.html",
                    "title": "Example",
                    "description": "Only curated output",
                }
            ],
        }
        self.out = Path(self.tmp.name) / "site"

    def save(self):
        path = self.root / build.MANIFEST
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.manifest))

    def test_only_explicit_files(self):
        (self.source.parent / "private.json").write_text("secret")
        self.save()
        build.build(self.out, self.root)
        self.assertEqual(len(list(self.out.rglob("*.html"))), 3)
        self.assertFalse(list(self.out.rglob("private.json")))
        self.assertEqual(
            (self.out / "reports/example/report.html").read_bytes(),
            self.source.read_bytes(),
        )

    def test_changed_source_rejected(self):
        self.save()
        self.source.write_text("changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            build.build(self.out, self.root)

    def test_traversal_rejected(self):
        for value in (
            "../escape.html",
            "%2e%2e/escape.html",
            "/escape.html",
            "https://host/file",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build.confined(self.root, value)

    def test_duplicate_normalized_destination_rejected(self):
        row = dict(self.manifest["files"][0])
        row["destination"] = "reports/example/%72eport.html"
        self.manifest["files"].append(row)
        self.save()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build.build(self.out, self.root)

    def test_local_or_broken_links_rejected(self):
        self.out.mkdir()
        page = self.out / "report.html"
        for href in (
            "file:///private/data",
            "/Users/name/file",
            "missing.html",
            "../escape.html",
        ):
            page.write_text('<a href="' + href + '">link</a>')
            with self.subTest(href=href), self.assertRaises(ValueError):
                build.validate_html(page, self.out)

    def test_legacy_alias(self):
        self.manifest["aliases"] = {
            "old/report.html": "reports/example/report.html"
        }
        self.save()
        build.build(self.out, self.root)
        self.assertIn(
            "../reports/example/report.html",
            (self.out / "old/report.html").read_text(),
        )

    def test_no_overwrite(self):
        self.save()
        self.out.mkdir()
        with self.assertRaises(FileExistsError):
            build.build(self.out, self.root)


if __name__ == "__main__":
    unittest.main()
