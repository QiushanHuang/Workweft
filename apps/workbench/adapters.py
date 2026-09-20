"""Read-only integration sources. The domain core has no adapter imports."""
import json
import sqlite3
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path


def run_id(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value or uuid.UUID(value).version != 4:
        raise ValueError('请输入有效的云端运行 UUID v4')
    return value


def harness_status(identifier):
    """Fixed read-only CLI operation; no browser-supplied shell fragments."""
    run_id(identifier)
    raise RuntimeError('Remote executor retired; retained observations are local history')


def harness_call(operation, payload):
    raise RuntimeError('Remote executor retired')


def ssh_json(command, payload):
    raise RuntimeError('Remote executor retired')


class RunStore:
    """Adapter-owned observations; never writes human task acceptance state."""
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, state TEXT NOT NULL, checked_at TEXT, error TEXT)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM runs ORDER BY rowid DESC')]

    def bind(self, task_id, identifier):
        identifier = run_id(identifier)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT task_id FROM runs WHERE id=?', (identifier,)).fetchone()
            if old and old['task_id'] != task_id:
                raise ValueError('此运行已关联另一个任务')
            db.execute('INSERT OR IGNORE INTO runs(id,task_id,state) VALUES(?,?,?)',
                       (identifier, task_id, 'not_checked'))

    def refresh(self, identifier, transport=harness_status):
        identifier = run_id(identifier)
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM runs WHERE id=?', (identifier,)).fetchone():
                raise ValueError('请先关联运行')
        try:
            response = transport(identifier)
            state = response['state']
            if not isinstance(state, str) or len(state) > 100:
                raise ValueError('invalid state')
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
            with self.connect() as db:
                db.execute('UPDATE runs SET error=? WHERE id=?', ('查询失败；保留上次状态，请检查 SSH 连接', identifier))
        else:
            with self.connect() as db:
                db.execute("UPDATE runs SET state=?, checked_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), error=NULL WHERE id=?", (state, identifier))


def harness_history(repository: Path) -> dict:
    path = repository / "docs/evidence/wp0b/real-task/task11-real-run-receipt.json"
    if not path.exists():
        return {"runs": [], "live": False}
    receipt = json.loads(path.read_text())
    execution = receipt["execution"]
    result = receipt["result"]
    return {"live": False, "runs": [{
        "id": receipt["logical_run_id"],
        "model_requested": execution["requested_model"],
        "state": receipt["collection"]["remote_state"],
        "recorded_at": receipt["created_at"],
        "duration_ms": execution["duration_ms"],
        "changed_paths": result["changed_paths"],
        "verification": receipt["independent_controller_verification"]["disposition"],
        "source": str(path.relative_to(repository)),
        "limitations": receipt["limitations"],
    }]}
