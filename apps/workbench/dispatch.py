"""Read-only compatibility view of locally retained Harness execution records."""

import sqlite3


class Dispatcher:
    def __init__(self, path):
        self.path = path

    def list(self):
        if not self.path.exists():
            return []
        with sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dispatches'").fetchone():
                return []
            return [dict(row) for row in db.execute("SELECT * FROM dispatches ORDER BY rowid DESC")]
