import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from .archive import extract_verified


class ArchiveTests(unittest.TestCase):
    def test_restore_and_reject_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "a.tar.gz"
            out = root / "restored"
            with tarfile.open(archive, "w:gz") as tar:
                m = tarfile.TarInfo("study/result.json")
                m.size = 2
                tar.addfile(m, io.BytesIO(b"{}"))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(extract_verified(archive, out, digest), 1)
            self.assertEqual((out / "study/result.json").read_bytes(), b"{}")
            with self.assertRaises(FileExistsError):
                extract_verified(archive, out, digest)
            with self.assertRaises(ValueError):
                extract_verified(archive, root / "bad", "0" * 64)

    def test_reject_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "a.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                m = tarfile.TarInfo("../escape")
                m.size = 2
                tar.addfile(m, io.BytesIO(b"{}"))
            with self.assertRaises(ValueError):
                extract_verified(
                    archive,
                    root / "out",
                    hashlib.sha256(archive.read_bytes()).hexdigest(),
                )
            self.assertFalse((root / "escape").exists())
