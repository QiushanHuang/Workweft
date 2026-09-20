from pathlib import Path
import tempfile
import unittest
import sqlite3
from unittest.mock import patch
from execution_service import ExecutionService


class ExecutionServiceTests(unittest.TestCase):
    def test_school_history_never_reconnects_or_becomes_local_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            history = Path(folder) / "app-runs.sqlite3"
            with sqlite3.connect(history) as db:
                db.execute("CREATE TABLE dispatches (id TEXT, task_id TEXT, revision INTEGER, title TEXT, phase TEXT)")
                db.execute("INSERT INTO dispatches VALUES ('old', 'task', 1, 'History', 'outcome_unknown')")
            original = history.read_bytes()
            service = ExecutionService(Path(folder) / "app.sqlite3")

            def forbidden(*args):
                raise AssertionError("must not contact retired school server")

            service.legacy.transport = forbidden
            service.resume_observation()
            self.assertFalse(service.refresh("old")["backend_available"])
            with (
                self.assertRaises(ValueError),
                patch.object(
                    service.local,
                    "submit",
                    side_effect=AssertionError("must refuse before launch"),
                ),
            ):
                service.submit(
                    {
                        "id": "task",
                        "title": "Retry",
                        "description": "Same logical task",
                    },
                    2,
                )
            self.assertEqual(service.local.list(), [])
            self.assertEqual(history.read_bytes(), original)

    def test_new_install_does_not_create_cloud_history(self):
        with tempfile.TemporaryDirectory() as folder:
            service = ExecutionService(Path(folder) / "app.sqlite3")
            self.assertEqual(service.legacy.list(), [])
            self.assertFalse((Path(folder) / "app-runs.sqlite3").exists())
