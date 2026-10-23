"""Storage identity and backup restoration contracts."""

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from . import backup, registry


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def test_resolve_local_and_external(self):
        self.assertEqual(
            registry.resolve("repo://data/input.json", root=self.root),
            self.root / "data/input.json",
        )
        self.assertEqual(
            registry.resolve(
                "edge-ai://data/input.json", asset_root=self.root
            ),
            self.root / "data/input.json",
        )
        self.assertIsNone(registry.resolve("ssh://board/file"))

    def test_reserved_final_skipped_and_development_verified(self):
        payload = self.root / "input.json"
        payload.write_text("{}")
        manifest = {
            "id": "test",
            "version": "v1",
            "splits": {
                "development": {
                    "purpose": "development",
                    "artifact": {
                        "uri": "edge-ai://input.json",
                        "sha256": registry.sha(payload),
                    },
                },
                "final": {
                    "purpose": "final_reserved",
                    "artifact": {
                        "uri": "edge-ai://missing.json",
                        "sha256": "0" * 64,
                    },
                },
            },
        }
        (self.root / "manifest.json").write_text(json.dumps(manifest))
        catalog = self.root / "catalog.json"
        catalog.write_text(
            json.dumps(
                {
                    "schema": "edge-ai-dataset-catalog/v1",
                    "datasets": [
                        {
                            "id": "test",
                            "version": "v1",
                            "manifest": "manifest.json",
                        }
                    ],
                }
            )
        )
        rows = registry.verify(catalog, asset_root=self.root)
        self.assertEqual(
            [r["status"] for r in rows], ["verified", "not_checked_final"]
        )
        payload.write_text("changed")
        self.assertEqual(
            registry.verify(catalog, asset_root=self.root)[0]["status"],
            "mismatch",
        )

    def test_traversal_and_symlink(self):
        with self.assertRaises(ValueError):
            registry.resolve("repo://data/%2e%2e/../escape", root=self.root)
        (self.root / "escape").symlink_to("/tmp")
        with self.assertRaises(ValueError):
            registry.resolve("repo://escape/a", root=self.root)

    def test_sample_identity(self):
        a = [{"id": "a", "user": "hello", "expected": {}, "latency": 2}]
        b = [{"expected": {}, "user": "hello", "id": "a"}]
        self.assertEqual(
            registry.samples_digest(a), registry.samples_digest(b)
        )
        b[0]["user"] = "changed"
        self.assertNotEqual(
            registry.samples_digest(a), registry.samples_digest(b)
        )

    def archive(self, name="data/file.json", duplicate_index=False):
        payload = b'{"example":true}'
        row = {
            "member": name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        }
        index = json.dumps([row, row] if duplicate_index else [row]).encode()
        path = self.root / "backup.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            for member, data in [
                (name, payload),
                ("backup-index.json", index),
            ]:
                info = tarfile.TarInfo(member)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return path

    def test_restore_roundtrip(self):
        path = self.archive()
        out = self.root / "restored"
        result = backup.restore(path, out, registry.sha(path))
        self.assertEqual(result["files"], 1)
        self.assertEqual(
            json.loads((out / "data/file.json").read_text()), {"example": True}
        )
        with self.assertRaises(FileExistsError):
            backup.restore(path, out, registry.sha(path))

    def test_restore_tampered_identity(self):
        path = self.archive()
        with self.assertRaisesRegex(ValueError, "identity"):
            backup.restore(path, self.root / "restored", "0" * 64)

    def test_restore_traversal(self):
        path = self.archive("../escape")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            backup.restore(path, self.root / "restored", registry.sha(path))
        self.assertFalse((self.root / "escape").exists())

    def test_restore_duplicate_index(self):
        path = self.archive(duplicate_index=True)
        with self.assertRaises(ValueError):
            backup.restore(path, self.root / "restored", registry.sha(path))


if __name__ == "__main__":
    unittest.main()
