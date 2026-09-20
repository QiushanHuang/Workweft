//! Review facts remain separate from execution and from canonical source adoption.
use crate::domain::{Command, State, Status};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use uuid::Uuid;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Criterion {
    pub id: String,
    pub text: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactKind {
    Code,
    Document,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Verification {
    Passed,
    Failed,
    NotRun,
    Unknown,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Disposition {
    Adopt,
    Reject,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Artifact {
    pub id: String,
    pub task_id: String,
    pub task_version: u64,
    pub run_id: String,
    pub title: String,
    pub kind: ArtifactKind,
    pub sha256: String,
    pub storage_ref: String,
    pub verification: Verification,
    pub ordinal: u64,
    pub created_revision: u64,
    #[serde(default)]
    pub dependency_bindings: HashMap<String, DependencyBinding>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct DependencyBinding {
    pub content_version: u64,
    pub acceptance_decision: Option<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Decision {
    pub id: String,
    pub task_id: String,
    pub task_version: u64,
    pub artifact_id: String,
    pub disposition: Disposition,
    pub checked_criteria: Vec<String>,
    pub reason: String,
    pub created_revision: u64,
    #[serde(default)]
    pub criteria_snapshot: Vec<Criterion>,
}

pub fn make_criteria(criteria: &[String]) -> Result<Vec<Criterion>, String> {
    if criteria.len() > 20
        || criteria
            .iter()
            .any(|s| s.trim().is_empty() || s.chars().count() > 1000)
    {
        return Err("验收条件最多 20 条，每条为 1–1000 字符".into());
    }
    let texts: Vec<_> = criteria.iter().map(|s| s.trim().to_string()).collect();
    if texts.iter().collect::<HashSet<_>>().len() != texts.len() {
        return Err("验收条件不能重复".into());
    }
    Ok(texts
        .into_iter()
        .map(|text| Criterion {
            id: Uuid::now_v7().to_string(),
            text,
        })
        .collect())
}

pub fn apply(state: &State, command: &Command) -> Option<Result<State, String>> {
    let task_id = match command {
        Command::SetCriteria { task_id, .. }
        | Command::RegisterArtifact { task_id, .. }
        | Command::RecordDecision { task_id, .. }
        | Command::AcceptTask { task_id, .. } => task_id,
        _ => return None,
    };
    Some(transition(state, command, task_id))
}

fn transition(state: &State, command: &Command, task_id: &str) -> Result<State, String> {
    let task = state
        .tasks
        .iter()
        .find(|t| t.id == task_id)
        .ok_or("任务不存在")?;
    if state
        .projects
        .iter()
        .any(|p| p.id == task.project_id && p.archived)
    {
        return Err("项目已归档，请先恢复".into());
    }
    if task.status == Status::Accepted && !matches!(command, Command::RegisterArtifact { .. }) {
        return Err("请先重新打开已验收任务".into());
    }
    let mut next = state.clone();
    match command {
        Command::SetCriteria { criteria, .. } => {
            let generated = make_criteria(criteria)?;
            let texts: Vec<_> = criteria.iter().map(|s| s.trim().to_string()).collect();
            let updated = next.tasks.iter_mut().find(|t| t.id == task_id).unwrap();
            if updated
                .criteria
                .iter()
                .map(|c| c.text.clone())
                .collect::<Vec<_>>()
                != texts
            {
                updated.criteria = generated;
                updated.content_version += 1;
                updated.acceptance_decision = None;
            }
        }
        Command::RegisterArtifact {
            task_version,
            run_id,
            title,
            kind,
            sha256,
            storage_ref,
            verification,
            dependency_bindings,
            ..
        } => {
            if sha256.len() != 64
                || !sha256.bytes().all(|c| c.is_ascii_hexdigit())
                || run_id.is_empty()
                || run_id.len() > 200
                || title.trim().is_empty()
                || title.chars().count() > 160
                || storage_ref.is_empty()
                || storage_ref.len() > 4096
                || *task_version > task.content_version
            {
                return Err("产物元数据无效".into());
            }
            if !state
                .artifacts
                .iter()
                .any(|a| a.task_id == task_id && a.run_id == *run_id && a.sha256 == *sha256)
            {
                next.artifacts.push(Artifact {
                    id: Uuid::now_v7().to_string(),
                    task_id: task_id.into(),
                    task_version: *task_version,
                    run_id: run_id.clone(),
                    title: title.trim().into(),
                    kind: kind.clone(),
                    sha256: sha256.clone(),
                    storage_ref: storage_ref.clone(),
                    verification: verification.clone(),
                    ordinal: state
                        .artifacts
                        .iter()
                        .filter(|a| a.task_id == task_id)
                        .count() as u64
                        + 1,
                    created_revision: state.revision + 1,
                    dependency_bindings: dependency_bindings.clone(),
                });
            }
            if *task_version == task.content_version
                && !task.criteria.is_empty()
                && task.status != Status::Accepted
                && (*kind == ArtifactKind::Document || *verification == Verification::Passed)
            {
                next.tasks
                    .iter_mut()
                    .find(|t| t.id == task_id)
                    .unwrap()
                    .status = Status::Review;
            }
        }
        Command::RecordDecision {
            artifact_id,
            disposition,
            checked_criteria,
            reason,
            ..
        } => {
            let artifact = state
                .artifacts
                .iter()
                .find(|a| a.id == *artifact_id && a.task_id == task_id)
                .ok_or("产物不属于此任务")?;
            if artifact.task_version != task.content_version && *disposition == Disposition::Adopt {
                return Err("产物属于旧版或未知版本任务，不能作为当前验收依据".into());
            }
            if reason.trim().is_empty() || reason.chars().count() > 10000 {
                return Err("请填写采用或拒绝的理由".into());
            }
            if checked_criteria.iter().collect::<HashSet<_>>().len() != checked_criteria.len()
                || checked_criteria
                    .iter()
                    .any(|id| !task.criteria.iter().any(|c| &c.id == id))
            {
                return Err("勾选的验收条件无效".into());
            }
            next.decisions.push(Decision {
                id: Uuid::now_v7().to_string(),
                task_id: task_id.into(),
                task_version: task.content_version,
                artifact_id: artifact_id.clone(),
                disposition: disposition.clone(),
                checked_criteria: checked_criteria.clone(),
                reason: reason.trim().into(),
                created_revision: state.revision + 1,
                criteria_snapshot: task.criteria.clone(),
            });
        }
        Command::AcceptTask { decision_id, .. } => {
            let decision = state
                .decisions
                .iter()
                .find(|d| d.id == *decision_id && d.task_id == task_id)
                .ok_or("决定不存在")?;
            let artifact = state
                .artifacts
                .iter()
                .find(|a| a.id == decision.artifact_id)
                .ok_or("产物不存在")?;
            if state
                .decisions
                .iter()
                .rev()
                .find(|d| {
                    d.task_id == task_id
                        && d.artifact_id == artifact.id
                        && d.task_version == task.content_version
                })
                .map(|d| &d.id)
                != Some(decision_id)
            {
                return Err("此产物已有更新的决定，请使用最新记录".into());
            }
            if task.status != Status::Review
                || decision.disposition != Disposition::Adopt
                || decision.task_version != task.content_version
                || artifact.task_version != task.content_version
                || task.criteria.is_empty()
                || task
                    .criteria
                    .iter()
                    .any(|c| !decision.checked_criteria.contains(&c.id))
            {
                return Err("需要当前任务版本、采用决定、全部条件勾选，并处于待验收状态".into());
            }
            if artifact.kind == ArtifactKind::Code && artifact.verification != Verification::Passed
            {
                return Err("代码产物尚未通过独立验证".into());
            }
            if task.dependencies.iter().any(|id| {
                !state.tasks.iter().any(|t| {
                    &t.id == id
                        && t.status == Status::Accepted
                        && artifact.dependency_bindings.get(id)
                            == Some(&DependencyBinding {
                                content_version: t.content_version,
                                acceptance_decision: t.acceptance_decision.clone(),
                            })
                })
            }) {
                return Err("前置任务未验收或其版本/采用依据已改变，需要重新核验产物".into());
            }
            let updated = next.tasks.iter_mut().find(|t| t.id == task_id).unwrap();
            updated.status = Status::Accepted;
            updated.acceptance_decision = Some(decision_id.clone());
        }
        _ => unreachable!(),
    }
    next.revision += 1;
    Ok(next)
}
