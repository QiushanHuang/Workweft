use crate::domain::{Command, State};
use rusqlite::{params, Connection, TransactionBehavior};
use serde_json::{json, Value};
use std::time::Duration;

pub fn dispatch(path: &str, request: Value) -> Result<Value, String> {
    execute(path, request).map_err(|e| e.to_string())
}

fn execute(path: &str, request: Value) -> Result<Value, Box<dyn std::error::Error>> {
    let mut db = Connection::open(path)?;
    db.busy_timeout(Duration::from_secs(5))?;
    let tx = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let version: u64 = tx.pragma_query_value(None, "user_version", |r| r.get(0))?;
    if version > 4 {
        return Err("数据库来自更新版本，请升级应用".into());
    }
    if version == 0 {
        tx.execute_batch(include_str!("../migrations/001_initial.sql"))?;
    }
    if version < 2 {
        tx.execute_batch(include_str!("../migrations/002_asset_references.sql"))?;
    }
    if version < 3 {
        tx.execute_batch("PRAGMA user_version=3;")?;
    }
    if version < 4 {
        tx.execute_batch("PRAGMA user_version=4;")?;
    }
    let body: String = tx.query_row("SELECT body FROM snapshot WHERE id=1", [], |r| r.get(0))?;
    let mut state: State = serde_json::from_str(&body)?;
    if request.get("query") == Some(&json!("import_preview")) {
        let source: State =
            serde_json::from_value(request.get("snapshot").cloned().ok_or("缺少导入数据")?)?;
        state.import_copy(&source)?;
        return Ok(
            json!({"projects":source.projects.len(),"tasks":source.tasks.len(),"assets":source.assets.len(),"revision":state.revision,"policy":"copy_new_ids_reset_todo","titles":source.projects.iter().map(|p| &p.title).collect::<Vec<_>>()}),
        );
    }
    if request.get("query") != Some(&json!("snapshot")) {
        if request.get("expected_revision").and_then(Value::as_u64) != Some(state.revision) {
            return Err("版本冲突：数据已被其他操作更新，请刷新后重试".into());
        }
        let command: Command =
            serde_json::from_value(request.get("command").cloned().ok_or("缺少 command")?)?;
        state = state.apply(&command)?;
        let payload = serde_json::to_string(&command)?;
        tx.execute(
            "INSERT INTO events(revision,command) VALUES(?1,?2)",
            params![state.revision, payload],
        )?;
        tx.execute(
            "UPDATE snapshot SET body=?1 WHERE id=1",
            [serde_json::to_string(&state)?],
        )?;
    }
    let mut response = serde_json::to_value(state)?;
    let events: Vec<Value> = {
        let mut statement = tx.prepare(
            "SELECT revision,command,created_at FROM events ORDER BY revision DESC LIMIT 100",
        )?;
        let rows = statement.query_map([], |r| {
            Ok((
                r.get::<_, u64>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
            ))
        })?;
        let mut result = Vec::new();
        for row in rows {
            let (revision, command, created_at) = row?;
            result.push(json!({"revision":revision,"command":serde_json::from_str::<Value>(&command)?,"created_at":created_at}));
        }
        result
    };
    response["events"] = json!(events);
    response["schema_version"] = json!(4);
    tx.commit()?;
    Ok(response)
}
