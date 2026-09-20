use hct_core::dispatch;
use serde_json::{json, Value};

fn database() -> String {
    std::env::temp_dir()
        .join(format!("hct-{}.sqlite3", uuid::Uuid::now_v7()))
        .to_string_lossy()
        .into()
}
fn apply(db: &str, revision: u64, command: Value) -> Value {
    dispatch(db, json!({"expected_revision":revision,"command":command})).unwrap()
}

#[test]
fn archive_restore_and_import_copies_preserve_originals() {
    let db = database();
    let s = apply(
        &db,
        0,
        json!({"type":"create_project","title":"Origin","description":""}),
    );
    let p = s["projects"][0]["id"].clone();
    let s = apply(
        &db,
        1,
        json!({"type":"create_task","project_id":p,"title":"Task","description":""}),
    );
    let original = s.clone();
    apply(
        &db,
        2,
        json!({"type":"set_project_archived","project_id":p,"archived":true}),
    );
    assert!(dispatch(&db,json!({"expected_revision":3,"command":{"type":"create_task","project_id":p,"title":"Blocked","description":""}})).is_err());
    apply(
        &db,
        3,
        json!({"type":"set_project_archived","project_id":p,"archived":false}),
    );
    let preview = dispatch(&db, json!({"query":"import_preview","snapshot":original})).unwrap();
    assert_eq!(preview["tasks"], 1);
    let copied = apply(
        &db,
        4,
        json!({"type":"import_workspace","snapshot":original}),
    );
    assert_eq!(copied["projects"].as_array().unwrap().len(), 2);
    assert_ne!(copied["tasks"][1]["id"], copied["tasks"][0]["id"]);
    assert_eq!(copied["tasks"][1]["status"], "todo");
    let mut invalid = original.clone();
    invalid["tasks"][0]["dependencies"] = json!(["missing"]);
    assert!(dispatch(&db, json!({"query":"import_preview","snapshot":invalid})).is_err());
    assert_eq!(
        dispatch(&db, json!({"query":"snapshot"})).unwrap()["revision"],
        5
    );
    std::fs::remove_file(db).unwrap();
}

#[test]
fn asset_references_persist_without_accessing_or_deleting_source_files() {
    let db = database();
    let old = rusqlite::Connection::open(&db).unwrap();
    old.execute_batch(include_str!("../migrations/001_initial.sql"))
        .unwrap();
    drop(old);
    assert_eq!(
        dispatch(&db, json!({"query":"snapshot"})).unwrap()["schema_version"],
        4
    );
    let s = apply(
        &db,
        0,
        json!({"type":"create_project","title":"Assets","description":""}),
    );
    let s = apply(
        &db,
        1,
        json!({"type":"create_task","project_id":s["projects"][0]["id"],"title":"Task","description":""}),
    );
    let task = s["tasks"][0]["id"].clone();
    let command = json!({"type":"add_asset","task_id":task,"title":"External note","kind":"local_file","target":"/not-mounted/example.md","description":"Pointer only"});
    let s = apply(&db, 2, command.clone());
    assert_eq!(s["assets"][0]["target"], "/not-mounted/example.md");
    assert_eq!(
        dispatch(&db, json!({"query":"snapshot"})).unwrap()["assets"],
        s["assets"]
    );
    assert!(dispatch(&db, json!({"expected_revision":3,"command":command})).is_err());
    let mut bad = command.clone();
    bad["target"] = json!("relative.md");
    assert!(dispatch(&db, json!({"expected_revision":3,"command":bad})).is_err());
    bad["kind"] = json!("url");
    bad["target"] = json!("javascript:alert(1)");
    assert!(dispatch(&db, json!({"expected_revision":3,"command":bad})).is_err());
    let s = apply(
        &db,
        3,
        json!({"type":"remove_asset","task_id":task,"asset_id":s["assets"][0]["id"]}),
    );
    assert_eq!(s["assets"].as_array().unwrap().len(), 0);
    std::fs::remove_file(db).unwrap();
}

#[test]
fn projects_and_tasks_survive_reopening_and_conflicts_do_not_write() {
    let db = database();
    let initial = dispatch(&db, json!({"query":"snapshot"})).unwrap();
    assert_eq!(initial["revision"], 0);
    let state = apply(
        &db,
        0,
        json!({"type":"create_project","title":"研究计划","description":"目标"}),
    );
    let project = state["projects"][0]["id"].clone();
    let state = apply(
        &db,
        1,
        json!({"type":"create_task","project_id":project,"title":"第一步","description":"内容"}),
    );
    assert_eq!(state["tasks"][0]["status"], "todo");
    assert!(dispatch(&db, json!({"expected_revision":1,"command":{"type":"create_project","title":"stale","description":""}})).is_err());
    let reopened = dispatch(&db, json!({"query":"snapshot"})).unwrap();
    assert_eq!(reopened, state);
    assert_eq!(state["events"].as_array().unwrap().len(), 2);
    std::fs::remove_file(db).unwrap();
}

#[test]
fn dependencies_reject_cycles_and_block_start_until_predecessor_accepted() {
    let db = database();
    let s = apply(
        &db,
        0,
        json!({"type":"create_project","title":"产品","description":""}),
    );
    let p = s["projects"][0]["id"].clone();
    let s = apply(
        &db,
        1,
        json!({"type":"create_task","project_id":p,"title":"A","description":""}),
    );
    let a = s["tasks"][0]["id"].clone();
    let s = apply(
        &db,
        2,
        json!({"type":"create_task","project_id":p,"title":"B","description":""}),
    );
    let b = s["tasks"][1]["id"].clone();
    apply(
        &db,
        3,
        json!({"type":"set_dependencies","task_id":b,"dependencies":[a]}),
    );
    assert!(dispatch(&db,json!({"expected_revision":4,"command":{"type":"set_dependencies","task_id":a,"dependencies":[b]}})).is_err());
    assert!(dispatch(
        &db,
        json!({"expected_revision":4,"command":{"type":"set_status","task_id":b,"status":"doing"}})
    )
    .is_err());
    apply(
        &db,
        4,
        json!({"type":"set_status","task_id":a,"status":"doing"}),
    );
    apply(
        &db,
        5,
        json!({"type":"set_status","task_id":a,"status":"review"}),
    );
    let s = apply(
        &db,
        6,
        json!({"type":"set_criteria","task_id":a,"criteria":["Complete"]}),
    );
    let s = apply(
        &db,
        7,
        json!({"type":"register_artifact","task_id":a,"task_version":s["tasks"][0]["content_version"],"run_id":"test","title":"Result","kind":"document","sha256":"0".repeat(64),"storage_ref":"artifact:test","verification":"not_run"}),
    );
    let s = apply(
        &db,
        8,
        json!({"type":"record_decision","task_id":a,"artifact_id":s["artifacts"][0]["id"],"disposition":"adopt","checked_criteria":[s["tasks"][0]["criteria"][0]["id"]],"reason":"Fixture reviewed"}),
    );
    apply(
        &db,
        9,
        json!({"type":"accept_task","task_id":a,"decision_id":s["decisions"][0]["id"]}),
    );
    let s = apply(
        &db,
        10,
        json!({"type":"set_status","task_id":b,"status":"doing"}),
    );
    assert_eq!(s["tasks"][1]["status"], "doing");
    std::fs::remove_file(db).unwrap();
}

#[test]
fn invalid_input_and_unearned_acceptance_are_rejected() {
    let db = database();
    assert!(dispatch(&db,json!({"expected_revision":0,"command":{"type":"create_project","title":" ","description":""}})).is_err());
    let s = apply(
        &db,
        0,
        json!({"type":"create_project","title":"P","description":""}),
    );
    let s = apply(
        &db,
        1,
        json!({"type":"create_task","project_id":s["projects"][0]["id"],"title":"T","description":""}),
    );
    assert!(dispatch(&db,json!({"expected_revision":2,"command":{"type":"set_status","task_id":s["tasks"][0]["id"],"status":"accepted"}})).is_err());
    assert!(dispatch(&db,json!({"expected_revision":2,"command":{"type":"create_task","project_id":"missing","title":"T","description":""}})).is_err());
    std::fs::remove_file(db).unwrap();
}
