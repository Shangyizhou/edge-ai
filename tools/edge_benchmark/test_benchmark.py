"""通过公开运行入口验证超时事实保留、子进程回收和报告转义。"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "edge_benchmark", Path(__file__).with_name("benchmark.py")
)
BENCHMARK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCHMARK)


class BenchmarkContractTest(unittest.TestCase):
    """测量器应如实保留超时前结果，且不把结果正文当作 HTML。"""

    def test_timeout_preserves_completed_sample_and_stops_descendant(self):
        """子进程悬挂时只终止该实验，保留已生成内容和非成功状态。"""
        program = (
            "import json,pathlib,subprocess,sys,time; "
            "p=pathlib.Path(sys.argv[1]); "
            "child=subprocess.Popen([sys.executable,'-c',"
            "'import time; time.sleep(30)']); "
            "(p/'child.pid').write_text(str(child.pid)); "
            "(p/'events.jsonl').write_text(json.dumps({"
            "'event':'sample','index':0,'seconds':0.1,"
            "'reply':'<img src=x onerror=alert(1)>'})+'\\n'); "
            "time.sleep(30)"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            case = {
                "id": "hung-native",
                "kind": "command",
                "timeout": 0.6,
                "command": [sys.executable, "-c", program, "{output}"],
            }
            BENCHMARK.run_suite(
                {
                    "python": sys.executable,
                    "cases": [case],
                    "budget_seconds": 5,
                },
                root,
            )
            result = json.loads((root / "hung-native/result.json").read_text())
            self.assertEqual(result["status"], "timeout")
            self.assertEqual(len(result["events"]), 1)
            pid = (root / "hung-native/child.pid").read_text()
            stat = Path("/proc") / pid / "stat"
            if stat.exists():
                self.assertEqual(
                    stat.read_text().rsplit(")", 1)[1].split()[0], "Z"
                )
            report = (root / "report.html").read_text()
            self.assertIn("timeout", report)
            self.assertIn("&lt;img", report)
            self.assertNotIn("<img src=x", report)


if __name__ == "__main__":
    unittest.main()
