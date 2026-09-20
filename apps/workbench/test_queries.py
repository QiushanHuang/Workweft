import importlib.util
import unittest


class QueryTests(unittest.TestCase):
    def test_search_links_historical_decision_to_task_without_reading_files(self):
        self.assertIsNotNone(importlib.util.find_spec("queries"))
        from queries import search

        snapshot = {
            "revision": 7,
            "projects": [{"id": "p", "title": "项目", "archived": False}],
            "tasks": [
                {
                    "id": "t",
                    "project_id": "p",
                    "title": "任务",
                    "description": "内容",
                    "content_version": 2,
                    "criteria": [],
                }
            ],
            "assets": [
                {
                    "id": "a",
                    "task_id": "t",
                    "title": "本地引用",
                    "description": "",
                    "target": "/not-existing/report.md",
                }
            ],
            "artifacts": [],
            "decisions": [
                {
                    "id": "d",
                    "task_id": "t",
                    "task_version": 1,
                    "artifact_id": "x",
                    "disposition": "adopt",
                    "reason": "边界已核对",
                }
            ],
        }
        result = search(snapshot, "边界")
        self.assertEqual(result["revision"], 7)
        self.assertEqual(result["items"][0]["task_id"], "t")
        self.assertTrue(result["items"][0]["stale"])
        self.assertEqual(search(snapshot, "report.md")["items"][0]["kind"], "asset")
        self.assertEqual(search(snapshot, "")["items"], [])
