use hct_core::dispatch;
use serde_json::{json, Value};
fn snapshot(db: &str) -> Value {
    dispatch(db, json!({"query":"snapshot"})).unwrap()
}
fn send(db: &str, c: Value) -> Result<Value, String> {
    dispatch(
        db,
        json!({"expected_revision":snapshot(db)["revision"],"command":c}),
    )
}

#[test]
fn review_binds_criteria_artifact_and_current_task_version() {
    let db = std::env::temp_dir()
        .join(format!("hct-review-{}.sqlite3", uuid::Uuid::now_v7()))
        .to_string_lossy()
        .to_string();
    let s = send(
        &db,
        json!({"type":"create_project","title":"P","description":""}),
    )
    .unwrap();
    let s=send(&db,json!({"type":"create_task","project_id":s["projects"][0]["id"],"title":"T","description":""})).unwrap();
    let task = s["tasks"][0]["id"].clone();
    let s = send(
        &db,
        json!({"type":"set_criteria","task_id":task,"criteria":["说明完整","边界准确"]}),
    )
    .unwrap();
    let version = s["tasks"][0]["content_version"].clone();
    let checks = json!([
        s["tasks"][0]["criteria"][0]["id"],
        s["tasks"][0]["criteria"][1]["id"]
    ]);
    let s=send(&db,json!({"type":"register_artifact","task_id":task,"task_version":version,"run_id":"run-one","title":"Report","kind":"document","sha256":"a".repeat(64),"storage_ref":"artifact:one","verification":"not_run"})).unwrap();
    let artifact = s["artifacts"][0]["id"].clone();
    send(
        &db,
        json!({"type":"set_status","task_id":task,"status":"doing"}),
    )
    .unwrap();
    send(
        &db,
        json!({"type":"set_status","task_id":task,"status":"review"}),
    )
    .unwrap();
    assert!(send(
        &db,
        json!({"type":"set_status","task_id":task,"status":"accepted"})
    )
    .is_err());
    let s=send(&db,json!({"type":"record_decision","task_id":task,"artifact_id":artifact,"disposition":"adopt","checked_criteria":[],"reason":"先采用候选"})).unwrap();
    let partial = s["decisions"][0]["id"].clone();
    assert!(send(
        &db,
        json!({"type":"accept_task","task_id":task,"decision_id":partial})
    )
    .is_err());
    let s=send(&db,json!({"type":"record_decision","task_id":task,"artifact_id":artifact,"disposition":"adopt","checked_criteria":checks,"reason":"已逐项检查内容"})).unwrap();
    let decision = s["decisions"][1]["id"].clone();
    let s = send(
        &db,
        json!({"type":"accept_task","task_id":task,"decision_id":decision}),
    )
    .unwrap();
    assert_eq!(s["tasks"][0]["status"], "accepted");
    send(
        &db,
        json!({"type":"set_status","task_id":task,"status":"todo"}),
    )
    .unwrap();
    send(
        &db,
        json!({"type":"edit_task","task_id":task,"title":"Changed","description":"new scope"}),
    )
    .unwrap();
    send(
        &db,
        json!({"type":"set_status","task_id":task,"status":"doing"}),
    )
    .unwrap();
    send(
        &db,
        json!({"type":"set_status","task_id":task,"status":"review"}),
    )
    .unwrap();
    assert!(send(
        &db,
        json!({"type":"accept_task","task_id":task,"decision_id":decision})
    )
    .is_err());
    assert_eq!(snapshot(&db)["decisions"].as_array().unwrap().len(), 2);
    std::fs::remove_file(db).unwrap();
}

#[test]
fn failed_code_and_superseded_adoption_cannot_be_accepted() {
    let db = std::env::temp_dir()
        .join(format!("hct-review-{}.sqlite3", uuid::Uuid::now_v7()))
        .to_string_lossy()
        .to_string();
    let s = send(
        &db,
        json!({"type":"create_project","title":"P","description":""}),
    )
    .unwrap();
    let s=send(&db,json!({"type":"create_task","project_id":s["projects"][0]["id"],"title":"T","description":"","criteria":["Tests pass"]})).unwrap();
    let task = s["tasks"][0]["id"].clone();
    let check = s["tasks"][0]["criteria"][0]["id"].clone();
    let s = send(
        &db,
        json!({"type":"edit_task","task_id":task,"title":"T","description":""}),
    )
    .unwrap();
    assert_eq!(s["tasks"][0]["content_version"], 1);
    let s=send(&db,json!({"type":"register_artifact","task_id":task,"task_version":1,"run_id":"failed","title":"Patch","kind":"code","sha256":"a".repeat(64),"storage_ref":"artifact:a","verification":"failed"})).unwrap();
    let artifact = s["artifacts"][0]["id"].clone();
    send(
        &db,
        json!({"type":"set_status","task_id":task,"status":"doing"}),
    )
    .unwrap();
    send(
        &db,
        json!({"type":"set_status","task_id":task,"status":"review"}),
    )
    .unwrap();
    let s=send(&db,json!({"type":"record_decision","task_id":task,"artifact_id":artifact,"disposition":"adopt","checked_criteria":[check],"reason":"Candidate only"})).unwrap();
    assert!(send(
        &db,
        json!({"type":"accept_task","task_id":task,"decision_id":s["decisions"][0]["id"]})
    )
    .is_err());
    let s=send(&db,json!({"type":"register_artifact","task_id":task,"task_version":1,"run_id":"passed","title":"Patch","kind":"code","sha256":"b".repeat(64),"storage_ref":"artifact:b","verification":"passed"})).unwrap();
    let artifact = s["artifacts"][1]["id"].clone();
    let s=send(&db,json!({"type":"record_decision","task_id":task,"artifact_id":artifact,"disposition":"adopt","checked_criteria":[check],"reason":"Reviewed"})).unwrap();
    let adopted = s["decisions"][1]["id"].clone();
    send(&db,json!({"type":"record_decision","task_id":task,"artifact_id":artifact,"disposition":"reject","checked_criteria":[],"reason":"Later finding"})).unwrap();
    assert!(send(
        &db,
        json!({"type":"accept_task","task_id":task,"decision_id":adopted})
    )
    .is_err());
    std::fs::remove_file(db).unwrap();
}

#[test]
fn dependency_version_binding_is_checked_at_acceptance() {
    let mut raw = json!({"revision":0,"projects":[{"id":"p","title":"P","description":""}],
      "tasks":[{"id":"parent","project_id":"p","title":"P","description":"","status":"accepted","dependencies":[],"content_version":2,"acceptance_decision":"parent-choice"},
      {"id":"child","project_id":"p","title":"C","description":"","status":"review","dependencies":["parent"],"content_version":1,"criteria":[{"id":"c","text":"checked"}]}],
      "artifacts":[{"id":"a","task_id":"child","task_version":1,"run_id":"r","title":"Doc","kind":"document","sha256":"a".repeat(64),"storage_ref":"artifact:a","verification":"not_run","ordinal":1,"created_revision":1,"dependency_bindings":{"parent":{"content_version":1,"acceptance_decision":"parent-choice"}}}],
      "decisions":[{"id":"d","task_id":"child","task_version":1,"artifact_id":"a","disposition":"adopt","checked_criteria":["c"],"reason":"checked","created_revision":2}]});
    let command = hct_core::domain::Command::AcceptTask {
        task_id: "child".into(),
        decision_id: "d".into(),
    };
    let state: hct_core::domain::State = serde_json::from_value(raw.clone()).unwrap();
    assert!(state.apply(&command).is_err());
    raw["artifacts"][0]["dependency_bindings"]["parent"]["content_version"] = json!(2);
    let state: hct_core::domain::State = serde_json::from_value(raw).unwrap();
    assert_eq!(
        state.apply(&command).unwrap().tasks[1].status,
        hct_core::domain::Status::Accepted
    );
}
