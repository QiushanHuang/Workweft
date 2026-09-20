CREATE TABLE snapshot (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
INSERT INTO snapshot VALUES (1, '{"revision":0,"projects":[],"tasks":[]}');
CREATE TABLE events (
    revision INTEGER PRIMARY KEY,
    command TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
PRAGMA user_version=1;
