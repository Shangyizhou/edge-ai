"""隔离数据库中的同步回归测试，不连接用户的 MLflow。"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from tools.edge_benchmark import test_experiment as fixtures
from tools.edge_benchmark.execution import run_plan
from tools.edge_benchmark.experiment import read_json
from tools.experiment_tracking.record_execution import synchronize

HAS_MLFLOW = importlib.util.find_spec("mlflow") is not None


@unittest.skipUnless(
    HAS_MLFLOW, "optional control-plane MLflow is not installed"
)
class SynchronizationTests(unittest.TestCase):
    """验证中断补传和去重，所有模型记录都属于 synthetic。"""

    def setUp(self) -> None:
        """使用合成执行及独立 SQLite，不读取真实样本。"""
        from mlflow import MlflowClient

        fixture = fixtures.ExperimentTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.plan()
        self.root = fixture.root
        self.run = self.root / "run"
        run_plan(
            self.root / "plan/plan.json",
            self.run,
            lambda *args: {
                "status": "completed",
                "result": {
                    "status": "completed",
                    "summary": {"samples": 1},
                    "cases": [{"id": "one", "status": "completed"}],
                },
            },
        )
        self.uri = "sqlite:///" + str(self.root / "isolated.db")
        self.client = MlflowClient(tracking_uri=self.uri)
        self.experiment_id = self.client.create_experiment(
            "edge-ai/qwen_tool_calls/synthetic",
            artifact_location=(self.root / "artifacts").as_uri(),
        )

    def test_sync_twice_keeps_one_run_metric_and_table(self) -> None:
        """补同步不得再次执行或追加重复表行。"""
        first = synchronize(self.run, self.uri)
        second = synchronize(self.run, self.uri)
        self.assertEqual(first["runs"], second["runs"])
        runs = self.client.search_runs([self.experiment_id])
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].data.tags["source_kind"], "synthetic_fixture")
        self.assertEqual(
            len(
                self.client.get_metric_history(runs[0].info.run_id, "samples")
            ),
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            table = self.client.download_artifacts(
                runs[0].info.run_id, "cases.json", directory
            )
            self.assertEqual(len(read_json(Path(table))["data"]), 1)

    def test_unavailable_store_preserves_measurements(self) -> None:
        """存储失败只影响同步状态，不改变测量或重新推理。"""
        before = (self.run / "execution.json").read_bytes()
        with self.assertRaises(Exception):
            synchronize(self.run, "not-a-supported-store://")
        self.assertEqual(read_json(self.run / "sync.json")["status"], "error")
        self.assertEqual((self.run / "execution.json").read_bytes(), before)
        self.assertEqual(synchronize(self.run, self.uri)["status"], "synced")


if __name__ == "__main__":
    unittest.main()
