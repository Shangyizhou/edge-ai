import json
import tempfile
import unittest
from pathlib import Path

from tools.edge_workflow.audit_data import audit


class AuditTests(unittest.TestCase):
    def test_shared_origin_is_not_independent(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            for split in ["train", "final"]:
                (p / (split + ".jsonl")).write_text(
                    json.dumps(
                        {
                            "source_group": "same-origin",
                            "messages": [{"role": "user", "content": split}],
                        }
                    )
                    + "\n"
                )
            (p / "index.json").write_text(
                json.dumps(
                    {
                        "files": {
                            s: str(p / (s + ".jsonl"))
                            for s in ["train", "final"]
                        }
                    }
                )
            )
            result = audit(p / "index.json")
            self.assertEqual(result["status"], "failed")
            self.assertIn("cross-split source family", result["issues"])

    def test_audit_does_not_disclose_final_text(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            (p / "final.jsonl").write_text(
                json.dumps(
                    {
                        "source_group": "final-only",
                        "messages": [
                            {
                                "role": "user",
                                "content": "private holdout question",
                            }
                        ],
                    }
                )
                + "\n"
            )
            (p / "index.json").write_text(
                json.dumps({"files": {"final": str(p / "final.jsonl")}})
            )
            self.assertNotIn(
                "private holdout question", json.dumps(audit(p / "index.json"))
            )
