import importlib.util
import unittest


class NextUpTests(unittest.TestCase):
    def test_ready_blocked_and_archived(self):
        self.assertIsNotNone(importlib.util.find_spec("next_up"))
        from next_up import recommend

        snapshot = {
            "projects": [
                {"id": "p", "archived": False},
                {"id": "old", "archived": True},
            ],
            "tasks": [
                {
                    "id": "a",
                    "project_id": "p",
                    "title": "A",
                    "status": "todo",
                    "dependencies": [],
                },
                {
                    "id": "b",
                    "project_id": "p",
                    "title": "B",
                    "status": "todo",
                    "dependencies": ["a"],
                },
                {
                    "id": "c",
                    "project_id": "old",
                    "title": "C",
                    "status": "todo",
                    "dependencies": [],
                },
            ],
        }
        rows = recommend(snapshot)
        self.assertEqual([row["task_id"] for row in rows], ["a", "b"])
        self.assertEqual(rows[0]["category"], "ready")
        self.assertTrue(rows[0]["reason"])
        self.assertEqual(rows[1]["category"], "blocked")
        self.assertEqual(rows[1]["blocking_ids"], ["a"])

    def test_order_and_unknown_dependency(self):
        self.assertIsNotNone(importlib.util.find_spec("next_up"))
        from next_up import recommend

        tasks = [
            {"id": k, "project_id": "p", "title": k, "status": v, "dependencies": []}
            for k, v in [
                ("t", "todo"),
                ("r", "review"),
                ("d", "doing"),
                ("a", "accepted"),
            ]
        ]
        tasks.append(
            {
                "id": "b",
                "project_id": "p",
                "title": "B",
                "status": "todo",
                "dependencies": ["missing"],
            }
        )
        rows = recommend({"projects": [{"id": "p"}], "tasks": tasks})
        self.assertEqual([row["task_id"] for row in rows], ["r", "d", "t", "b"])
        self.assertEqual(rows[-1]["blocking_ids"], ["missing"])
        self.assertEqual(tasks[0]["status"], "todo")
