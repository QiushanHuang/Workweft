"""Loopback workbench host; all domain writes go through the Rust core."""

import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

from adapters import RunStore, harness_history
from execution_service import ExecutionService
from asset_export import export_references
from interchange import import_snapshot, to_minddesk
from import_summary import summarize_import
from artifacts import ArtifactStore
from queries import search
from next_up import recommend

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).with_name("static")


def core(database, request):
    binary = ROOT / "target/debug/hct-core"
    result = subprocess.run(
        [str(binary), str(database)],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=15,
    )
    return result.returncode, json.loads(result.stdout)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Do not persist potentially sensitive search terms in routine access logs.
        safe = tuple(
            str(value).split("?", 1)[0] + "?[query omitted]"
            if "?" in str(value)
            else value
            for value in args
        )
        super().log_message(format, *safe)

    def send(self, code, payload, content_type="application/json; charset=utf-8"):
        raw = (
            json.dumps(payload, ensure_ascii=False).encode()
            if isinstance(payload, (dict, list))
            else payload
        )
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(raw)

    def allowed_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self.allowed_host():
            return self.send(403, {"error": "请使用本机 127.0.0.1 地址"})
        path = urlsplit(self.path).path
        try:
            if path == "/favicon.ico":
                return self.send(204, b"", "image/x-icon")
            if path == "/api/session":
                return self.send(200, {"token": self.server.token})
            if path == "/api/runs":
                return self.send(
                    200,
                    dict(
                        harness_history(ROOT),
                        linked=self.server.runs.list(),
                        dispatches=self.server.dispatcher.list(),
                    ),
                )
            if path.startswith("/api/artifacts/"):
                identifier = path.removeprefix("/api/artifacts/")
                code, snapshot = core(self.server.database, {"query": "snapshot"})
                artifact = next(
                    (a for a in snapshot.get("artifacts", []) if a["id"] == identifier),
                    None,
                )
                if code or artifact is None:
                    return self.send(404, {"error": "产物不存在"})
                return self.send(200, self.server.artifacts.read(artifact["sha256"]))
            if path == "/api/search":
                code, snapshot = core(self.server.database, {"query": "snapshot"})
                if code:
                    return self.send(500, snapshot)
                try:
                    result = search(
                        snapshot, parse_qs(urlsplit(self.path).query).get("q", [""])[0]
                    )
                except ValueError as exc:
                    return self.send(400, {"error": str(exc)})
                return self.send(200, result)
            if path in (
                "/api/snapshot",
                "/api/export",
                "/api/export.json",
                "/api/assets/export",
                "/api/minddesk/export",
                "/api/next-up",
            ):
                code, snapshot = core(self.server.database, {"query": "snapshot"})
                if code:
                    return self.send(500, snapshot)
                if path == "/api/snapshot":
                    return self.send(200, snapshot)
                if path == "/api/next-up":
                    return self.send(
                        200,
                        {
                            "revision": snapshot["revision"],
                            "items": recommend(snapshot),
                        },
                    )
                if path == "/api/export.json":
                    return self.send(
                        200, {"schema": "HCTWorkspaceExportV1", "snapshot": snapshot}
                    )
                if path == "/api/minddesk/export":
                    return self.send(200, to_minddesk(snapshot))
                if path == "/api/assets/export":
                    return self.send(
                        200,
                        export_references(snapshot.get("assets", [])).encode(),
                        "text/markdown; charset=utf-8",
                    )
                lines = [
                    "# Workweft",
                    f"\nRevision: {snapshot['revision']}\n",
                ]
                for project in snapshot["projects"]:
                    lines.extend([f"## {project['title']}", project["description"], ""])
                    for task in snapshot["tasks"]:
                        if task["project_id"] == project["id"]:
                            lines.extend(
                                [
                                    f"- [{task['status']}] {task['title']} ({task['id']})",
                                    f"  {task['description']}",
                                    f"  Depends on: {', '.join(task['dependencies']) or 'none'}",
                                ]
                            )
                            for asset in snapshot.get("assets", []):
                                if asset["task_id"] == task["id"]:
                                    lines.extend(
                                        [
                                            f"  - Asset: {asset['title']} ({asset['kind']})",
                                            f"    Target: {asset['target']}",
                                            f"    {asset['description']}",
                                        ]
                                    )
                            lines.append(
                                f"  Content version: {task.get('content_version', 0)}"
                            )
                            for criterion in task.get("criteria", []):
                                lines.append(f"  - Criterion: {criterion['text']}")
                            for artifact in snapshot.get("artifacts", []):
                                if artifact["task_id"] == task["id"]:
                                    lines.append(
                                        f"  - Artifact: {artifact['title']} ({artifact['id']}); "
                                        f"task v{artifact['task_version']}; run {artifact['run_id']}; "
                                        f"verification: {artifact['verification']}"
                                    )
                            for decision in snapshot.get("decisions", []):
                                if decision["task_id"] == task["id"]:
                                    lines.append(
                                        f"  - Decision: {decision['disposition']} ({decision['id']}); "
                                        f"task v{decision['task_version']}; artifact {decision['artifact_id']}"
                                    )
                                    lines.append(f"    Reason: {decision['reason']}")
                                    for criterion in decision.get(
                                        "criteria_snapshot", []
                                    ):
                                        mark = (
                                            "x"
                                            if criterion["id"]
                                            in decision["checked_criteria"]
                                            else " "
                                        )
                                        lines.append(
                                            f"    - [{mark}] {criterion['text']}"
                                        )
                return self.send(
                    200, "\n".join(lines).encode(), "text/markdown; charset=utf-8"
                )
            files = {
                "/": ("index.html", "text/html"),
                "/app.js": ("app.js", "text/javascript"),
                "/review-panel.js": ("review-panel.js", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
                "/logo.png": ("logo.png", "image/png"),
            }
            if path not in files:
                return self.send(404, {"error": "Not found"})
            name, kind = files[path]
            self.send(200, (STATIC / name).read_bytes(), kind + "; charset=utf-8")
        except (OSError, ValueError, subprocess.SubprocessError):
            self.send(500, {"error": "无法读取本地数据，请检查服务终端"})

    def do_POST(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if (
            not self.allowed_host()
            or self.headers.get("Origin") not in (None, origin)
            or not secrets.compare_digest(
                self.headers.get("X-HCT-Token", ""), self.server.token
            )
        ):
            return self.send(403, {"error": "请求未获本地会话授权，请刷新页面"})
        if self.path not in (
            "/api/command",
            "/api/artifacts/capture",
            "/api/import/preview",
            "/api/import/apply",
            "/api/runs/bind",
            "/api/runs/refresh",
            "/api/runs/dispatch",
            "/api/runs/reconcile",
            "/api/runs/cancel",
        ):
            return self.send(404, {"error": "Not found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1_048_576:
                return self.send(413, {"error": "请求长度无效"})
            request = json.loads(self.rfile.read(size))
            if self.path == "/api/artifacts/capture":
                if not isinstance(request, dict) or set(request) != {
                    "run_id",
                    "expected_revision",
                }:
                    return self.send(400, {"error": "请求格式无效"})
                job = next(
                    (
                        job
                        for job in self.server.dispatcher.list()
                        if job["id"] == request["run_id"]
                    ),
                    None,
                )
                if job is None:
                    return self.send(404, {"error": "运行不存在"})
                metadata = self.server.artifacts.freeze(job)
                code, result = core(
                    self.server.database,
                    {
                        "expected_revision": request["expected_revision"],
                        "command": dict(metadata, type="register_artifact"),
                    },
                )
                return self.send(409 if code else 200, result)
            if self.path == "/api/import/preview":
                snapshot = import_snapshot(request)
                code, preview = core(
                    self.server.database,
                    {"query": "import_preview", "snapshot": snapshot},
                )
                if code:
                    return self.send(400, preview)
                preview["summary"] = summarize_import(
                    {key: preview[key] for key in ("projects", "tasks", "assets")}
                )
                identifier = secrets.token_urlsafe(24)
                with self.server.import_lock:
                    self.server.imports = {
                        key: value
                        for key, value in self.server.imports.items()
                        if value[2] > time.monotonic()
                    }
                    if len(self.server.imports) >= 20:
                        return self.send(429, {"error": "导入预览过多，请稍后重试"})
                    self.server.imports[identifier] = (
                        snapshot,
                        preview["revision"],
                        time.monotonic() + 600,
                    )
                return self.send(
                    200,
                    dict(
                        preview,
                        preview_id=identifier,
                        warning="仅添加新副本；重新分配 ID，任务重置待办，不恢复运行、人工验收或归档状态。MindDesk 命令/脚本不会执行；未映射的样式、片段和分组不会导入。",
                    ),
                )
            if self.path == "/api/import/apply":
                if not isinstance(request, dict) or set(request) != {"preview_id"}:
                    return self.send(400, {"error": "请求格式无效"})
                with self.server.import_lock:
                    entry = self.server.imports.pop(request["preview_id"], None)
                if not entry or entry[2] < time.monotonic():
                    return self.send(409, {"error": "预览已过期或已使用，请重新预览"})
                code, result = core(
                    self.server.database,
                    {
                        "expected_revision": entry[1],
                        "command": {"type": "import_workspace", "snapshot": entry[0]},
                    },
                )
                return self.send(409 if code else 200, result)
            if self.path.startswith("/api/runs/"):
                if not isinstance(request, dict):
                    return self.send(400, {"error": "请求格式无效"})
                if self.path.endswith("/dispatch"):
                    if not {"task_id", "expected_revision"}.issubset(request) or set(
                        request
                    ) - {"task_id", "expected_revision", "profile", "execution"}:
                        return self.send(400, {"error": "请求格式无效"})
                    code, snapshot = core(self.server.database, {"query": "snapshot"})
                    if code or snapshot["revision"] != request["expected_revision"]:
                        return self.send(409, {"error": "任务已更新，请刷新后提交"})
                    task = next(
                        (
                            item
                            for item in snapshot["tasks"]
                            if item["id"] == request["task_id"]
                        ),
                        None,
                    )
                    if not task or task["status"] == "accepted":
                        return self.send(
                            400, {"error": "任务不存在或已经验收，请先重新打开任务"}
                        )
                    if not task.get("criteria"):
                        return self.send(
                            409, {"error": "请先在任务详情填写验收条件，再启动新任务"}
                        )
                    if any(
                        p["id"] == task["project_id"] and p.get("archived")
                        for p in snapshot["projects"]
                    ):
                        return self.send(409, {"error": "项目已归档，请先恢复"})
                    accepted = {
                        item["id"]
                        for item in snapshot["tasks"]
                        if item["status"] == "accepted"
                    }
                    if not set(task["dependencies"]).issubset(accepted):
                        return self.send(409, {"error": "请先完成前置任务"})
                    task = dict(
                        task,
                        dependency_bindings={
                            item["id"]: {
                                "content_version": item["content_version"],
                                "acceptance_decision": item.get("acceptance_decision"),
                            }
                            for item in snapshot["tasks"]
                            if item["id"] in task["dependencies"]
                        },
                    )
                    return self.send(
                        202,
                        self.server.dispatcher.submit(
                            task,
                            snapshot["revision"],
                            profile=request.get("profile", "codex_document"),
                            execution=request.get("execution"),
                        ),
                    )
                if self.path.endswith(("/reconcile", "/cancel")):
                    if set(request) != {"run_id"}:
                        return self.send(400, {"error": "请求格式无效"})
                    operation = (
                        self.server.dispatcher.cancel
                        if self.path.endswith("/cancel")
                        else self.server.dispatcher.refresh
                    )
                    return self.send(200, operation(request["run_id"]))
                if self.path.endswith("/bind"):
                    if set(request) != {"task_id", "run_id"}:
                        return self.send(400, {"error": "请求格式无效"})
                    code, snapshot = core(self.server.database, {"query": "snapshot"})
                    if code or request["task_id"] not in [
                        task["id"] for task in snapshot["tasks"]
                    ]:
                        return self.send(400, {"error": "任务不存在"})
                    self.server.runs.bind(request["task_id"], request["run_id"])
                else:
                    if set(request) != {"run_id"}:
                        return self.send(400, {"error": "请求格式无效"})
                    return self.send(409, {"error": "旧执行器已停用；历史记录仍可查看"})
                return self.send(200, {"linked": self.server.runs.list()})
            if not isinstance(request, dict) or set(request) != {
                "expected_revision",
                "command",
            }:
                return self.send(400, {"error": "请求格式无效"})
            command = request["command"]
            if not isinstance(command, dict):
                return self.send(400, {"error": "命令格式无效"})
            if command.get("type") == "register_artifact":
                return self.send(
                    403, {"error": "产物只能从保存的运行结果归档，不能手填验证状态"}
                )
            if (
                command.get("type") in ("accept_task", "record_decision")
                and command.get("disposition") != "reject"
            ):
                code, current = core(self.server.database, {"query": "snapshot"})
                artifact_id = command.get("artifact_id")
                if command["type"] == "accept_task":
                    decision = next(
                        (
                            d
                            for d in current.get("decisions", [])
                            if d["id"] == command.get("decision_id")
                        ),
                        None,
                    )
                    artifact_id = decision["artifact_id"] if decision else None
                artifact = next(
                    (a for a in current.get("artifacts", []) if a["id"] == artifact_id),
                    None,
                )
                if code or artifact is None:
                    return self.send(409, {"error": "请先选择已归档的产物版本"})
                try:
                    self.server.artifacts.read(artifact["sha256"])
                except (OSError, ValueError):
                    return self.send(
                        409, {"error": "产物内容不可用或已改变，不能采用/验收"}
                    )
            code, result = core(self.server.database, request)
            self.send(409 if code else 200, result)
        except (ValueError, UnicodeError, KeyError, TypeError):
            self.send(
                400, {"error": "请求参数无效；请检查 JSON、运行 UUID 或已有任务关联"}
            )
        except (OSError, RuntimeError, subprocess.SubprocessError):
            self.send(500, {"error": "操作未确认，请刷新以核对最新状态"})


def main():
    default_data = (
        Path.home()
        / "Library/Application Support/local.harness.control/workbench.sqlite3"
        if os.uname().sysname == "Darwin"
        else ROOT / ".harness-control/workbench.sqlite3"
    )
    database = Path(os.environ.get("HCT_DATABASE", str(default_data))).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    if not (ROOT / "target/debug/hct-core").exists():
        raise SystemExit("请先运行 cargo build -p hct-core")
    server = ThreadingHTTPServer(
        ("127.0.0.1", int(os.environ.get("HCT_PORT", "4178"))), Handler
    )
    server.database = database
    server.runs = RunStore(database.with_name(database.stem + "-runs.sqlite3"))
    server.dispatcher = ExecutionService(database)
    server.artifacts = ArtifactStore(database.parent / "artifacts")
    server.dispatcher.resume_observation()
    server.token = secrets.token_urlsafe(32)
    server.imports = {}
    server.import_lock = threading.Lock()
    print(f"Workweft: http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
