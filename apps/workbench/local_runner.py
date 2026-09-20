"""Local Codex execution. Workers outlive UI connections; canonical source is never edited."""

from contextlib import contextmanager
import hashlib
import difflib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import threading
import uuid

SOURCE = Path(__file__).resolve().parents[2]
TERMINAL = {
    "reported_success",
    "failed",
    "cancelled",
    "interrupted",
    "verification_failed",
}


def reduce_event(state, event):
    state = dict(state)
    if event.get("type") == "thread.started":
        state["session_id"] = event.get("thread_id")
    if event.get("type") == "turn.completed":
        state["model_completed"] = True
        state["usage"] = event.get("usage")
    if event.get("type") in ("turn.failed", "error"):
        state["model_error"] = True
    return state


def relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("无效相对路径")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or str(p) != value:
        raise ValueError("只允许工作目录内的规范相对路径")
    return value


def collect_changes(folder):
    """Compare byte snapshots without executing worker-controlled Git configuration."""
    workspace = folder / "workspace"
    inputs = folder / "inputs"
    names = {
        str(p.relative_to(base))
        for base in (workspace, inputs)
        for p in base.rglob("*")
        if (p.is_file() or p.is_symlink())
        and ".git" not in p.relative_to(base).parts
        and "__pycache__" not in p.relative_to(base).parts
    }
    changed = []
    patches = []
    unsafe = False
    for name in sorted(names):
        old = inputs / name
        new = workspace / name
        if new.is_symlink() or not new.resolve().is_relative_to(workspace.resolve()):
            changed.append(name)
            unsafe = True
            continue
        before = old.read_bytes() if old.exists() else b""
        after = new.read_bytes() if new.exists() else b""
        if before == after:
            continue
        changed.append(name)
        if max(len(before), len(after)) > 1_000_000:
            unsafe = True
            continue
        patches.extend(
            difflib.unified_diff(
                before.decode("utf-8", errors="replace").splitlines(keepends=True),
                after.decode("utf-8", errors="replace").splitlines(keepends=True),
                fromfile="a/" + name if old.exists() else "/dev/null",
                tofile="b/" + name if new.exists() else "/dev/null",
            )
        )
    return changed, "".join(patches), unsafe


class LocalRunner:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        settings = self.root.parent / "sources.json"
        self.source = SOURCE
        if settings.exists():
            configured = Path(json.loads(settings.read_text())["workbench_root"])
            if (
                not configured.is_absolute()
                or not (configured / "apps/workbench").is_dir()
            ):
                raise ValueError("配置的工作台源码目录不存在")
            self.source = configured.resolve()
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, identity TEXT UNIQUE NOT NULL, body TEXT NOT NULL)"
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "jobs.sqlite3", timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self):
        with self.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute("SELECT body FROM jobs ORDER BY rowid DESC")
            ]

    def get(self, identifier):
        with self.connect() as db:
            row = db.execute(
                "SELECT body FROM jobs WHERE id=?", (identifier,)
            ).fetchone()
        if not row:
            raise ValueError("本地运行不存在")
        return json.loads(row[0])

    def update(self, identifier, **values):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = json.loads(
                db.execute(
                    "SELECT body FROM jobs WHERE id=?", (identifier,)
                ).fetchone()[0]
            )
            row.update(values)
            row["updated_at"] = time.time()
            db.execute(
                "UPDATE jobs SET body=? WHERE id=?",
                (json.dumps(row, ensure_ascii=False), identifier),
            )
        return row

    def submit(self, task, revision, launch=True, mode="document", execution=None):
        if mode not in ("document", "code"):
            raise ValueError("未知本地执行模式")
        execution = execution or {}
        if not isinstance(execution, dict) or set(execution) - {
            "allowed_paths",
            "test_files",
        }:
            raise ValueError("执行参数格式无效")
        if not isinstance(execution.get("allowed_paths", []), list) or not isinstance(
            execution.get("test_files", []), list
        ):
            raise ValueError("路径与测试必须是列表")
        allowed = [relative(p) for p in execution.get("allowed_paths", [])]
        tests = execution.get("test_files", [])
        if len(allowed) > 32 or len(tests) > 8:
            raise ValueError("单次任务最多 32 个修改路径和 8 个测试文件")
        if mode == "code" and (not allowed or not tests):
            raise ValueError("代码任务需要明确修改路径和测试文件")
        for p in allowed:
            if (
                not p.startswith("apps/workbench/")
                or not p.endswith(".py")
                or p.endswith(
                    (
                        "local_runner.py",
                        "server.py",
                        "adapters.py",
                        "dispatch.py",
                        "execution_service.py",
                    )
                )
            ):
                raise ValueError(
                    "首版本地代码任务仅允许工作台 Python 模块；不能修改运行控制器"
                )
        if any(
            not isinstance(t, str)
            or not t.startswith("test_")
            or not t.endswith(".py")
            or "/" in t
            or "*" in t
            for t in tests
        ):
            raise ValueError("测试需为明确的 test_*.py 文件名")
        inputs = {}
        if mode == "code":
            for p in (self.source / "apps/workbench").rglob("*.py"):
                if (
                    p.is_symlink()
                    or "__pycache__" in p.parts
                    or any(
                        part.startswith(".") or part == "node_modules"
                        for part in p.relative_to(self.source / "apps/workbench").parts
                    )
                ):
                    continue
                data = p.read_bytes()
                if len(data) > 1_000_000:
                    raise ValueError("单个源码输入过大")
                inputs[str(p.relative_to(self.source))] = data
            for filename in tests:
                path = "apps/workbench/" + filename
                if path not in inputs or path in allowed:
                    raise ValueError("验收测试必须预先存在且不可被本次任务修改")
        bindings = {
            path: hashlib.sha256(data).hexdigest() for path, data in inputs.items()
        }
        spec = {
            "task_id": task["id"],
            "title": task["title"],
            "description": task["description"],
            "task_version": task.get("content_version", 0),
            "criteria": task.get("criteria", []),
            "dependency_bindings": task.get("dependency_bindings", {}),
            "mode": mode,
            "allowed_paths": allowed,
            "test_files": tests,
            "input_bindings": bindings,
            "source_root": str(self.source) if mode == "code" else None,
        }
        identity = json.dumps(spec, sort_keys=True, ensure_ascii=False)
        identifier = str(uuid.uuid4())
        job = dict(
            spec,
            id=identifier,
            revision=revision,
            backend="codex-local",
            profile="codex_" + mode,
            phase="queued",
            result=None,
            error=None,
            created_at=time.time(),
            updated_at=time.time(),
            cancel_requested=False,
        )
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT body FROM jobs WHERE identity=?", (identity,)
            ).fetchone()
            if existing:
                return json.loads(existing[0])
            if any(
                json.loads(row[0])["phase"] not in TERMINAL
                for row in db.execute("SELECT body FROM jobs")
            ):
                raise ValueError("已有本地运行，请先完成或取消")
            folder = self.root / identifier
            workspace = folder / "workspace"
            workspace.mkdir(parents=True, mode=0o700)
            (folder / "inputs").mkdir(mode=0o700)
            for name, data in inputs.items():
                target = workspace / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                frozen = folder / "inputs" / name
                frozen.parent.mkdir(parents=True, exist_ok=True)
                frozen.write_bytes(data)
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?)",
                (identifier, identity, json.dumps(job, ensure_ascii=False)),
            )
        if launch:
            with (folder / "worker.log").open("ab") as log:
                worker = subprocess.Popen(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        str(self.root),
                        identifier,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
                threading.Thread(target=worker.wait, daemon=True).start()
        return job

    def cancel(self, identifier):
        job = self.get(identifier)
        if job["phase"] in TERMINAL:
            return job
        return self.update(identifier, cancel_requested=True)

    def refresh(self, identifier):
        job = self.get(identifier)
        if job["phase"] not in TERMINAL and time.time() - job["updated_at"] > 180:
            return self.update(
                identifier,
                phase="interrupted",
                error="Worker 心跳丢失；保留结果，不自动重派。",
            )
        return job

    def work(self, identifier):
        job = self.get(identifier)
        folder = self.root / identifier
        workspace = folder / "workspace"
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            latest = json.loads(
                db.execute(
                    "SELECT body FROM jobs WHERE id=?", (identifier,)
                ).fetchone()[0]
            )
            if latest["phase"] != "queued":
                return
            latest.update(
                phase="preparing", updated_at=time.time(), worker_pid=os.getpid()
            )
            db.execute(
                "UPDATE jobs SET body=? WHERE id=?", (json.dumps(latest), identifier)
            )
        child = None
        try:
            if latest["cancel_requested"]:
                self.update(identifier, phase="cancelled")
                return

            def git(*args):
                return subprocess.run(
                    ["git", "-C", str(workspace), *args],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=20,
                ).stdout

            git("init", "-q")
            git("add", ".")
            git(
                "-c",
                "user.name=HCT Snapshot",
                "-c",
                "user.email=snapshot@local",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgSign=false",
                "commit",
                "--allow-empty",
                "-qm",
                "Frozen task input",
            )
            codex = shutil.which("codex")
            if not codex:
                for candidate in (
                    Path.home() / ".npm-global/bin/codex",
                    Path("/opt/homebrew/bin/codex"),
                    Path("/usr/local/bin/codex"),
                ):
                    if candidate.is_file() and os.access(candidate, os.X_OK):
                        codex = str(candidate)
                        break
            if not codex:
                raise RuntimeError("未找到 Codex CLI")
            env = {
                key: value
                for key, value in os.environ.items()
                if key
                in (
                    "PATH",
                    "HOME",
                    "TMPDIR",
                    "LANG",
                    "LC_ALL",
                    "CODEX_HOME",
                    "HTTP_PROXY",
                    "HTTPS_PROXY",
                    "ALL_PROXY",
                    "NO_PROXY",
                    "SSL_CERT_FILE",
                )
            }
            env["PATH"] = os.pathsep.join(
                dict.fromkeys(
                    [
                        str(Path(codex).parent),
                        "/opt/homebrew/bin",
                        "/usr/local/bin",
                        env.get("PATH", "/usr/bin:/bin"),
                    ]
                )
            )
            prompt = (
                "Work only in the supplied workspace. Do not access other directories, credentials, SSH, network services, or start other agents. "
                "Do not commit or change tests unless explicitly listed as allowed. Produce the actual requested output.\n"
                f"Title: {job['title']}\nDescription: {job['description']}\n"
                f"Acceptance criteria: {json.dumps(job.get('criteria', []), ensure_ascii=False)}\n"
            )
            if job["mode"] == "code":
                prompt += f"Only change/create these paths: {json.dumps(job['allowed_paths'])}. Tests: {json.dumps(job['test_files'])}. Finish with a concise change summary."
            else:
                prompt += "Write the complete Markdown deliverable to result.md and summarize it."
            (folder / "prompt.txt").write_text(prompt)
            with (
                (folder / "events.jsonl").open("wb") as events,
                (folder / "stderr.log").open("wb") as errors,
            ):
                child = subprocess.Popen(
                    [
                        codex,
                        "exec",
                        "--ignore-user-config",
                        "--sandbox",
                        "workspace-write",
                        "--json",
                        "-C",
                        str(workspace),
                        "-o",
                        str(folder / "final.txt"),
                        "-",
                    ],
                    stdin=subprocess.PIPE,
                    cwd=workspace,
                    stdout=events,
                    stderr=errors,
                    env=env,
                    start_new_session=True,
                )
                child.stdin.write(prompt.encode())
                child.stdin.close()
                started = time.monotonic()
                self.update(identifier, phase="running", pid=child.pid)
                while child.poll() is None:
                    current = self.get(identifier)
                    oversized = (
                        folder / "events.jsonl"
                    ).stat().st_size > 20_000_000 or (
                        folder / "stderr.log"
                    ).stat().st_size > 5_000_000
                    if (
                        current["cancel_requested"]
                        or time.monotonic() - started > 900
                        or oversized
                    ):
                        os.killpg(child.pid, signal.SIGTERM)
                        try:
                            child.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(child.pid, signal.SIGKILL)
                            child.wait()
                        self.update(
                            identifier,
                            phase="cancelled"
                            if current["cancel_requested"]
                            else "interrupted",
                            error="执行已停止，工作副本和日志保留",
                        )
                        return
                    self.update(identifier, phase="running")
                    time.sleep(1)
            observation = {}
            for line in (
                (folder / "events.jsonl").read_text(errors="replace").splitlines()
            ):
                try:
                    observation = reduce_event(observation, json.loads(line))
                except ValueError:
                    continue
            self.update(identifier, **observation, exit_code=child.returncode)
            if (
                child.returncode
                or not observation.get("model_completed")
                or observation.get("model_error")
            ):
                self.update(
                    identifier, phase="failed", error="Codex 未成功完成；原始日志已保留"
                )
                return
            changed, patch, unsafe = collect_changes(folder)
            allowed = set(
                job["allowed_paths"] if job["mode"] == "code" else ["result.md"]
            )
            permitted = not unsafe and set(changed).issubset(allowed) and bool(changed)
            result = {
                "kind": "code" if job["mode"] == "code" else "document",
                "changed_paths": changed,
                "patch": patch,
                "text": (folder / "final.txt").read_text()
                if (folder / "final.txt").exists()
                else "",
                "truncated": False,
                "verification_passed": False,
                "verification_log": "尚未验证",
                "workspace": str(workspace),
            }
            if job["mode"] == "document":
                if permitted and (workspace / "result.md").is_file():
                    document = (workspace / "result.md").read_text()
                    result["text"] = document[:262144]
                    result["truncated"] = len(document) > 262144
                result["verification_log"] = "文档已回收；未验证事实内容"
                self.update(
                    identifier,
                    phase="reported_success" if permitted else "verification_failed",
                    result=json.dumps(result, ensure_ascii=False),
                )
                return
            verified = permitted
            logs = []
            if permitted:
                self.update(identifier, phase="verifying")
                test_home = folder / "test-home"
                test_home.mkdir()
                profile = (
                    "(version 1)(allow default)(deny network*)(deny file-write* (require-not (subpath "
                    + json.dumps(str(folder))
                    + ")))"
                )
                for protected in (
                    Path.home() / ".codex",
                    Path.home() / ".ssh",
                    Path.home() / ".local/share/hct-backup-keys",
                ):
                    profile += (
                        "(deny file-read* (subpath " + json.dumps(str(protected)) + "))"
                    )
                profile += (
                    "(deny file-write* (subpath "
                    + json.dumps(str(folder / "inputs"))
                    + "))"
                )
                for reserved in (
                    "prompt.txt",
                    "events.jsonl",
                    "stderr.log",
                    "final.txt",
                    "worker.log",
                ):
                    profile += (
                        "(deny file-write* (literal "
                        + json.dumps(str(folder / reserved))
                        + "))"
                    )
                test_env = dict(
                    env,
                    HOME=str(test_home),
                    TMPDIR=str(test_home),
                    PYTHONDONTWRITEBYTECODE="1",
                )
                for filename in job["test_files"]:
                    self.update(identifier, phase="verifying")
                    run = subprocess.run(
                        [
                            "/usr/bin/sandbox-exec",
                            "-p",
                            profile,
                            sys.executable,
                            "-B",
                            "-c",
                            "import sys,unittest; s=unittest.defaultTestLoader.discover('apps/workbench',pattern=sys.argv[1]); assert s.countTestCases()>0, 'No tests discovered'; r=unittest.TextTestRunner(verbosity=2).run(s); sys.exit(0 if r.wasSuccessful() else 1)",
                            filename,
                        ],
                        cwd=workspace,
                        env=test_env,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    logs.append(run.stdout + run.stderr)
                    verified = verified and run.returncode == 0
                    if self.get(identifier)["cancel_requested"]:
                        self.update(
                            identifier,
                            phase="cancelled",
                            error="验证期间收到取消；未记录为成功",
                        )
                        return
                after_paths, after_patch, after_unsafe = collect_changes(folder)
                verified = (
                    verified
                    and not after_unsafe
                    and after_paths == changed
                    and after_patch == patch
                )
            result["verification_passed"] = verified
            result["verification_log"] = (
                "\n".join(logs)
                if permitted
                else (
                    "未产生文件修改，未宣称任务完成"
                    if not changed
                    else "修改路径超出允许范围，未运行测试"
                )
            )
            self.update(
                identifier,
                phase="reported_success" if verified else "verification_failed",
                result=json.dumps(result, ensure_ascii=False),
            )
        except Exception as exc:
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=10)
            self.update(
                identifier,
                phase="failed",
                error=f"本地执行异常：{type(exc).__name__}；请检查私有运行日志",
            )
            raise


if __name__ == "__main__":
    LocalRunner(Path(sys.argv[1])).work(sys.argv[2])
