import importlib.util
from pathlib import Path
import tempfile
import unittest


class ArtifactTests(unittest.TestCase):
    def test_freeze_is_idempotent_and_tamper_is_detected(self):
        self.assertIsNotNone(importlib.util.find_spec("artifacts"))
        from artifacts import ArtifactStore

        with tempfile.TemporaryDirectory() as folder:
            store = ArtifactStore(Path(folder))
            job = {
                "id": "run",
                "task_id": "t",
                "task_version": 2,
                "backend": "codex-local",
                "phase": "reported_success",
                "result": '{"kind":"document","text":"# Result","verification_passed":false}',
            }
            metadata = store.freeze(job)
            self.assertEqual(metadata, store.freeze(job))
            self.assertEqual(metadata["verification"], "not_run")
            self.assertEqual(
                store.read(metadata["sha256"])["result"]["text"], "# Result"
            )
            (Path(folder) / (metadata["sha256"] + ".json")).write_text("changed")
            with self.assertRaises(ValueError):
                store.read(metadata["sha256"])
