import importlib.util
from pathlib import Path
import tempfile
import unittest
import os
import sys
import time
import json
import subprocess
from unittest.mock import patch


class LocalRunnerTests(unittest.TestCase):
    def test_owned_worker_survives_controller_recreation_and_cancels(self):
        from local_runner import LocalRunner

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = root / "codex"
            executable.write_text(
                "#!"
                + sys.executable
                + '\nimport json,time,sys\nfrom pathlib import Path\nsys.stdin.read()\nPath("started").write_text("yes")\nprint(json.dumps({"type":"thread.started","thread_id":"fake-session"}),flush=True)\ntime.sleep(20)\n'
            )
            executable.chmod(0o700)
            with patch.dict(
                os.environ, {"PATH": str(root) + os.pathsep + os.environ["PATH"]}
            ):
                runner = LocalRunner(root / "runs")
                task = {"id": "t", "title": "Lifecycle test", "description": "test"}
                coordinator = "import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from local_runner import LocalRunner; print(json.dumps(LocalRunner(Path(sys.argv[2])).submit(json.loads(sys.argv[3]),1)))"
                launched = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        coordinator,
                        str(Path(__file__).parent),
                        str(root / "runs"),
                        json.dumps(task),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=10,
                )
                job = json.loads(launched.stdout)
                try:
                    until = time.monotonic() + 10
                    while (
                        not (root / "runs" / job["id"] / "workspace/started").exists()
                        and time.monotonic() < until
                    ):
                        time.sleep(0.1)
                    self.assertTrue(
                        (root / "runs" / job["id"] / "workspace/started").exists()
                    )
                    recreated = LocalRunner(root / "runs")
                    self.assertEqual(recreated.submit(task, 2)["id"], job["id"])
                    recreated.cancel(job["id"])
                    until = time.monotonic() + 10
                    while (
                        recreated.get(job["id"])["phase"] != "cancelled"
                        and time.monotonic() < until
                    ):
                        time.sleep(0.1)
                    self.assertEqual(recreated.get(job["id"])["phase"], "cancelled")
                finally:
                    runner.cancel(job["id"])
                    until = time.monotonic() + 5
                    while (
                        runner.get(job["id"])["phase"] not in ("cancelled", "failed")
                        and time.monotonic() < until
                    ):
                        time.sleep(0.1)

    def test_collection_rejects_symlink_and_uses_frozen_input(self):
        import local_runner

        self.assertTrue(hasattr(local_runner, "collect_changes"))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "workspace").mkdir()
            (root / "inputs").mkdir()
            (root / "inputs/a.py").write_text("old\n")
            (root / "workspace/a.py").write_text("new\n")
            changed, patch, unsafe = local_runner.collect_changes(root)
            self.assertEqual(changed, ["a.py"])
            self.assertIn("+new", patch)
            self.assertFalse(unsafe)
            (root / "outside").write_text("DO_NOT_READ")
            (root / "workspace/leak.py").symlink_to(root / "outside")
            changed, patch, unsafe = local_runner.collect_changes(root)
            self.assertTrue(unsafe)
            self.assertNotIn("DO_NOT_READ", patch)

    def test_code_requires_existing_immutable_tests(self):
        from local_runner import LocalRunner

        with tempfile.TemporaryDirectory() as folder:
            runner = LocalRunner(Path(folder))
            with self.assertRaises(ValueError):
                runner.submit(
                    {"id": "t", "title": "Title", "description": "Body"},
                    1,
                    launch=False,
                    mode="code",
                    execution={
                        "allowed_paths": ["apps/workbench/a.py"],
                        "test_files": ["test_missing_contract.py"],
                    },
                )

    def test_durable_reservation_and_unknown_after_restart(self):
        self.assertIsNotNone(importlib.util.find_spec("local_runner"))
        from local_runner import LocalRunner

        with tempfile.TemporaryDirectory() as folder:
            runner = LocalRunner(Path(folder))
            task = {"id": "t", "title": "Title", "description": "Body"}
            first = runner.submit(task, 1, launch=False)
            again = runner.submit(task, 2, launch=False)
            self.assertEqual(first["id"], again["id"])
            restarted = LocalRunner(Path(folder))
            self.assertEqual(restarted.list()[0]["phase"], "queued")
            self.assertEqual(restarted.list()[0]["backend"], "codex-local")

    def test_event_completion_is_not_verification(self):
        self.assertIsNotNone(importlib.util.find_spec("local_runner"))
        from local_runner import reduce_event

        result = reduce_event(
            {}, {"type": "turn.completed", "usage": {"input_tokens": 10}}
        )
        self.assertEqual(result["model_completed"], True)
        self.assertNotIn("verification_passed", result)
        result = reduce_event(
            result, {"type": "thread.started", "thread_id": "thread-one"}
        )
        self.assertEqual(result["session_id"], "thread-one")
