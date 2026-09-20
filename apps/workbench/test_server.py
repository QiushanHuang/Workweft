import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

SERVER = Path(__file__).with_name("server.py")


class WorkbenchTest(unittest.TestCase):
    def test_persistent_api_and_export(self):
        self.assertTrue(SERVER.exists(), "workbench server is not implemented")
        with tempfile.TemporaryDirectory() as temp:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = dict(
                os.environ,
                HCT_PORT=str(port),
                HCT_DATABASE=str(Path(temp) / "app.sqlite3"),
            )
            process = subprocess.Popen(
                [sys.executable, str(SERVER)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(
                            base + "/api/snapshot", timeout=1
                        ) as response:
                            snapshot = json.load(response)
                        break
                    except OSError:
                        if process.poll() is not None:
                            self.fail(process.stderr.read().decode())
                        time.sleep(0.05)
                else:
                    self.fail("server did not start")
                self.assertEqual(snapshot["revision"], 0)
                with urllib.request.urlopen(base + "/api/session") as response:
                    token = json.load(response)["token"]
                body = json.dumps(
                    {
                        "expected_revision": 0,
                        "command": {
                            "type": "create_project",
                            "title": "端到端项目",
                            "description": "目标",
                        },
                    }
                ).encode()
                req = urllib.request.Request(
                    base + "/api/command",
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-HCT-Token": token,
                        "Origin": base,
                    },
                )
                with urllib.request.urlopen(req) as response:
                    self.assertEqual(
                        json.load(response)["projects"][0]["title"], "端到端项目"
                    )
                with self.assertRaises(urllib.error.HTTPError) as conflict:
                    urllib.request.urlopen(req)
                self.assertEqual(conflict.exception.code, 409)
                conflict.exception.close()
                with urllib.request.urlopen(base + "/api/export") as response:
                    self.assertIn("端到端项目", response.read().decode())
                bad = urllib.request.Request(
                    base + "/api/command",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(bad)
                self.assertEqual(rejected.exception.code, 403)
                rejected.exception.close()
                with urllib.request.urlopen(base + "/") as response:
                    self.assertIn("Harness", response.read().decode())
                with urllib.request.urlopen(base + "/logo.png") as response:
                    self.assertTrue(response.read().startswith(b"\x89PNG"))

                def post(path, payload):
                    request = urllib.request.Request(
                        base + path,
                        data=json.dumps(payload).encode(),
                        headers={
                            "Content-Type": "application/json",
                            "X-HCT-Token": token,
                        },
                    )
                    with urllib.request.urlopen(request) as response:
                        return json.load(response)

                with urllib.request.urlopen(base + "/api/snapshot") as response:
                    current = json.load(response)
                current = post(
                    "/api/command",
                    {
                        "expected_revision": 1,
                        "command": {
                            "type": "create_task",
                            "project_id": current["projects"][0]["id"],
                            "title": "云端关联",
                            "description": "",
                        },
                    },
                )
                task_id = current["tasks"][0]["id"]
                run_id = "e224a4bc-f252-4aba-830d-ad2b9f637570"
                linked = post("/api/runs/bind", {"task_id": task_id, "run_id": run_id})
                self.assertEqual(linked["linked"][0]["task_id"], task_id)
                with urllib.request.urlopen(base + "/api/runs") as response:
                    self.assertEqual(
                        json.load(response)["linked"][0]["state"], "not_checked"
                    )
                with self.assertRaises(urllib.error.HTTPError) as missing:
                    post("/api/runs/bind", {"task_id": "absent", "run_id": run_id})
                self.assertEqual(missing.exception.code, 400)
                missing.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as stale:
                    post(
                        "/api/runs/dispatch",
                        {"task_id": task_id, "expected_revision": 0},
                    )
                self.assertEqual(stale.exception.code, 409)
                stale.exception.close()
                post(
                    "/api/command",
                    {
                        "expected_revision": 2,
                        "command": {
                            "type": "add_asset",
                            "task_id": task_id,
                            "title": "Pointer",
                            "kind": "external_ref",
                            "target": "minddesk:unresolved-example",
                            "description": "No protocol assumption",
                        },
                    },
                )
                with urllib.request.urlopen(base + "/api/export.json") as response:
                    exported = json.load(response)
                self.assertEqual(
                    exported["snapshot"]["assets"][0]["target"],
                    "minddesk:unresolved-example",
                )
                with urllib.request.urlopen(base + "/api/assets/export") as response:
                    asset_markdown = response.read().decode()
                self.assertIn("```json", asset_markdown)
                self.assertIn("minddesk:unresolved-example", asset_markdown)
                preview = post("/api/import/preview", exported)
                self.assertEqual(preview["tasks"], 1)
                imported = post(
                    "/api/import/apply", {"preview_id": preview["preview_id"]}
                )
                self.assertEqual(len(imported["tasks"]), 2)
                with self.assertRaises(urllib.error.HTTPError) as replay:
                    post("/api/import/apply", {"preview_id": preview["preview_id"]})
                self.assertEqual(replay.exception.code, 409)
                replay.exception.close()
                reviewed = post(
                    "/api/command",
                    {
                        "expected_revision": imported["revision"],
                        "command": {
                            "type": "set_criteria",
                            "task_id": task_id,
                            "criteria": ["内容可读"],
                        },
                    },
                )
                from local_runner import LocalRunner

                runner = LocalRunner(Path(temp) / "codex-runs")
                task = next(t for t in reviewed["tasks"] if t["id"] == task_id)
                job = runner.submit(task, reviewed["revision"], launch=False)
                runner.update(
                    job["id"],
                    phase="reported_success",
                    result=json.dumps(
                        {
                            "kind": "document",
                            "text": "# Fixture result",
                            "truncated": False,
                        }
                    ),
                )
                captured = post(
                    "/api/artifacts/capture",
                    {"run_id": job["id"], "expected_revision": reviewed["revision"]},
                )
                self.assertEqual(captured["tasks"][0]["status"], "review")
                captured = post(
                    "/api/artifacts/capture",
                    {"run_id": job["id"], "expected_revision": captured["revision"]},
                )
                self.assertEqual(len(captured["artifacts"]), 1)
                artifact = captured["artifacts"][0]
                decided = post(
                    "/api/command",
                    {
                        "expected_revision": captured["revision"],
                        "command": {
                            "type": "record_decision",
                            "task_id": task_id,
                            "artifact_id": artifact["id"],
                            "disposition": "adopt",
                            "checked_criteria": [task["criteria"][0]["id"]],
                            "reason": "HTTP regression fixture",
                        },
                    },
                )
                artifact_path = (
                    Path(temp) / "artifacts" / (artifact["sha256"] + ".json")
                )
                original = artifact_path.read_bytes()
                artifact_path.write_text("tampered fixture")
                accept = {
                    "expected_revision": decided["revision"],
                    "command": {
                        "type": "accept_task",
                        "task_id": task_id,
                        "decision_id": decided["decisions"][0]["id"],
                    },
                }
                with self.assertRaises(urllib.error.HTTPError) as corrupt:
                    post("/api/command", accept)
                self.assertEqual(corrupt.exception.code, 409)
                corrupt.exception.close()
                artifact_path.write_bytes(original)
                accepted = post("/api/command", accept)
                self.assertEqual(accepted["tasks"][0]["status"], "accepted")
                with urllib.request.urlopen(base + "/api/export") as response:
                    exported = response.read().decode()
                    self.assertIn("minddesk:unresolved-example", exported)
                    self.assertIn("HTTP regression fixture", exported)
                    self.assertIn("Criterion:", exported)
                    self.assertIn(artifact["run_id"], exported)
            finally:
                process.terminate()
                process.wait(timeout=5)
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
