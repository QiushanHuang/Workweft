use crate::review::{Artifact, ArtifactKind, Criterion, Decision, Disposition, Verification};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use uuid::Uuid;

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct State {
    pub revision: u64,
    pub projects: Vec<Project>,
    pub tasks: Vec<Task>,
    #[serde(default)]
    pub assets: Vec<AssetReference>,
    #[serde(default)]
    pub artifacts: Vec<Artifact>,
    #[serde(default)]
    pub decisions: Vec<Decision>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AssetKind {
    LocalFile,
    Url,
    ExternalRef,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AssetReference {
    pub id: String,
    pub task_id: String,
    pub title: String,
    pub kind: AssetKind,
    pub target: String,
    pub description: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Project {
    pub id: String,
    pub title: String,
    pub description: String,
    #[serde(default)]
    pub archived: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Todo,
    Doing,
    Review,
    Accepted,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Task {
    pub id: String,
    pub project_id: String,
    pub title: String,
    pub description: String,
    pub status: Status,
    pub dependencies: Vec<String>,
    #[serde(default = "initial_version")]
    pub content_version: u64,
    #[serde(default)]
    pub criteria: Vec<Criterion>,
    #[serde(default)]
    pub acceptance_decision: Option<String>,
}
fn initial_version() -> u64 {
    1
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Command {
    SetCriteria {
        task_id: String,
        criteria: Vec<String>,
    },
    RegisterArtifact {
        task_id: String,
        task_version: u64,
        run_id: String,
        title: String,
        kind: ArtifactKind,
        sha256: String,
        storage_ref: String,
        verification: Verification,
        #[serde(default)]
        dependency_bindings: HashMap<String, crate::review::DependencyBinding>,
    },
    RecordDecision {
        task_id: String,
        artifact_id: String,
        disposition: Disposition,
        checked_criteria: Vec<String>,
        reason: String,
    },
    AcceptTask {
        task_id: String,
        decision_id: String,
    },
    SetProjectArchived {
        project_id: String,
        archived: bool,
    },
    ImportWorkspace {
        snapshot: State,
    },
    AddAsset {
        task_id: String,
        title: String,
        kind: AssetKind,
        target: String,
        description: String,
    },
    RemoveAsset {
        task_id: String,
        asset_id: String,
    },
    CreateProject {
        title: String,
        description: String,
    },
    CreateTask {
        project_id: String,
        title: String,
        description: String,
        #[serde(default)]
        criteria: Vec<String>,
    },
    EditTask {
        task_id: String,
        title: String,
        description: String,
    },
    SetStatus {
        task_id: String,
        status: Status,
    },
    SetDependencies {
        task_id: String,
        dependencies: Vec<String>,
    },
}

fn title(value: &str) -> Result<String, String> {
    let value = value.trim();
    if value.is_empty() || value.chars().count() > 160 {
        return Err("标题需为 1–160 个字符".into());
    }
    Ok(value.into())
}

fn description(value: &str) -> Result<String, String> {
    if value.chars().count() > 10000 {
        return Err("描述不能超过 10000 个字符".into());
    }
    Ok(value.into())
}

fn reaches(tasks: &[Task], from: &str, target: &str, seen: &mut HashSet<String>) -> bool {
    if from == target {
        return true;
    }
    if !seen.insert(from.into()) {
        return false;
    }
    tasks.iter().find(|t| t.id == from).is_some_and(|t| {
        t.dependencies
            .iter()
            .any(|d| reaches(tasks, d, target, seen))
    })
}

impl State {
    pub fn import_copy(&self, source: &State) -> Result<Self, String> {
        if source.projects.len() > 100 || source.tasks.len() > 10000 || source.assets.len() > 20000
        {
            return Err("导入规模超过单次上限".into());
        }
        let mut seen = HashSet::new();
        for id in source
            .projects
            .iter()
            .map(|p| &p.id)
            .chain(source.tasks.iter().map(|t| &t.id))
            .chain(source.assets.iter().map(|a| &a.id))
        {
            if id.is_empty() || !seen.insert(id) {
                return Err("导入包含空或重复 ID".into());
            }
        }
        let mut copy = State::default();
        let mut projects = HashMap::new();
        let mut tasks = HashMap::new();
        for p in &source.projects {
            copy = copy.apply(&Command::CreateProject {
                title: p.title.clone(),
                description: p.description.clone(),
            })?;
            projects.insert(p.id.clone(), copy.projects.last().unwrap().id.clone());
        }
        for t in &source.tasks {
            let project_id = projects
                .get(&t.project_id)
                .ok_or("导入任务的项目不存在")?
                .clone();
            copy = copy.apply(&Command::CreateTask {
                project_id,
                title: t.title.clone(),
                description: t.description.clone(),
                criteria: t.criteria.iter().map(|c| c.text.clone()).collect(),
            })?;
            tasks.insert(t.id.clone(), copy.tasks.last().unwrap().id.clone());
        }
        for t in &source.tasks {
            let dependencies = t
                .dependencies
                .iter()
                .map(|id| tasks.get(id).cloned().ok_or("导入依赖不存在".to_string()))
                .collect::<Result<Vec<_>, _>>()?;
            copy = copy.apply(&Command::SetDependencies {
                task_id: tasks[&t.id].clone(),
                dependencies,
            })?;
        }
        for a in &source.assets {
            copy = copy.apply(&Command::AddAsset {
                task_id: tasks.get(&a.task_id).ok_or("导入引用的任务不存在")?.clone(),
                title: a.title.clone(),
                kind: a.kind.clone(),
                target: a.target.clone(),
                description: a.description.clone(),
            })?;
        }
        let mut next = self.clone();
        next.projects.extend(copy.projects);
        next.tasks.extend(copy.tasks);
        next.assets.extend(copy.assets);
        next.revision = self.revision + 1;
        Ok(next)
    }
    /// Candidate transition. The storage transaction publishes only on success.
    pub fn apply(&self, command: &Command) -> Result<Self, String> {
        if let Some(result) = crate::review::apply(self, command) {
            return result;
        }
        let owner = match command {
            Command::CreateTask { project_id, .. } => Some(project_id.as_str()),
            Command::AddAsset { task_id, .. }
            | Command::RemoveAsset { task_id, .. }
            | Command::EditTask { task_id, .. }
            | Command::SetStatus { task_id, .. }
            | Command::SetDependencies { task_id, .. } => self
                .tasks
                .iter()
                .find(|t| &t.id == task_id)
                .map(|t| t.project_id.as_str()),
            _ => None,
        };
        if owner.is_some_and(|id| self.projects.iter().any(|p| p.id == id && p.archived)) {
            return Err("项目已归档，请先恢复".into());
        }
        let mut next = self.clone();
        match command {
            Command::SetCriteria { .. }
            | Command::RegisterArtifact { .. }
            | Command::RecordDecision { .. }
            | Command::AcceptTask { .. } => unreachable!(),
            Command::ImportWorkspace { snapshot } => return self.import_copy(snapshot),
            Command::SetProjectArchived {
                project_id,
                archived,
            } => {
                next.projects
                    .iter_mut()
                    .find(|p| &p.id == project_id)
                    .ok_or("项目不存在")?
                    .archived = *archived;
            }
            Command::AddAsset {
                task_id,
                title: name,
                kind,
                target,
                description: body,
            } => {
                let task = self
                    .tasks
                    .iter()
                    .find(|t| &t.id == task_id)
                    .ok_or("任务不存在")?;
                if task.status == Status::Accepted {
                    return Err("请先重新打开已验收任务".into());
                }
                let target = target.trim();
                if target.is_empty() || target.len() > 4096 || target.chars().any(char::is_control)
                {
                    return Err("引用不能为空、超过 4096 字节或包含控制字符".into());
                }
                match kind {
                    AssetKind::LocalFile if !target.starts_with('/') => {
                        return Err("本地文件引用需要绝对路径".into())
                    }
                    AssetKind::Url => {
                        let rest = target
                            .strip_prefix("https://")
                            .or_else(|| target.strip_prefix("http://"))
                            .ok_or("网址仅支持 http 或 https")?;
                        let host = rest.split(['/', '?', '#']).next().unwrap_or_default();
                        if host.is_empty()
                            || host.contains('@')
                            || target.chars().any(char::is_whitespace)
                            || target.contains('\\')
                        {
                            return Err("网址格式无效，不能包含登录凭据".into());
                        }
                    }
                    _ => {}
                }
                if self
                    .assets
                    .iter()
                    .any(|a| &a.task_id == task_id && a.kind == *kind && a.target == target)
                {
                    return Err("该任务已登记此引用".into());
                }
                next.assets.push(AssetReference {
                    id: Uuid::now_v7().to_string(),
                    task_id: task_id.clone(),
                    title: title(name)?,
                    kind: kind.clone(),
                    target: target.into(),
                    description: description(body)?,
                });
            }
            Command::RemoveAsset { task_id, asset_id } => {
                let task = self
                    .tasks
                    .iter()
                    .find(|t| &t.id == task_id)
                    .ok_or("任务不存在")?;
                if task.status == Status::Accepted {
                    return Err("请先重新打开已验收任务".into());
                }
                let index = next
                    .assets
                    .iter()
                    .position(|a| &a.id == asset_id && &a.task_id == task_id)
                    .ok_or("引用不存在或属于其他任务")?;
                next.assets.remove(index);
            }
            Command::CreateProject {
                title: name,
                description: body,
            } => {
                next.projects.push(Project {
                    id: Uuid::now_v7().to_string(),
                    title: title(name)?,
                    description: description(body)?,
                    archived: false,
                });
            }
            Command::CreateTask {
                project_id,
                title: name,
                description: body,
                criteria,
            } => {
                if !self.projects.iter().any(|p| &p.id == project_id) {
                    return Err("项目不存在".into());
                }
                next.tasks.push(Task {
                    id: Uuid::now_v7().to_string(),
                    project_id: project_id.clone(),
                    title: title(name)?,
                    description: description(body)?,
                    status: Status::Todo,
                    dependencies: vec![],
                    content_version: 1,
                    criteria: crate::review::make_criteria(criteria)?,
                    acceptance_decision: None,
                });
            }
            Command::EditTask {
                task_id,
                title: name,
                description: body,
            } => {
                let task = next
                    .tasks
                    .iter_mut()
                    .find(|t| &t.id == task_id)
                    .ok_or("任务不存在")?;
                if task.status == Status::Accepted {
                    return Err("请先将任务重新打开，再修改已验收内容".into());
                }
                task.title = title(name)?;
                task.description = description(body)?;
            }
            Command::SetDependencies {
                task_id,
                dependencies,
            } => {
                let task = self
                    .tasks
                    .iter()
                    .find(|t| &t.id == task_id)
                    .ok_or("任务不存在")?;
                if task.status != Status::Todo {
                    return Err("只能修改待办任务的依赖".into());
                }
                let mut unique = HashSet::new();
                for id in dependencies {
                    if !unique.insert(id) {
                        return Err("不能重复添加依赖".into());
                    }
                    let other = self
                        .tasks
                        .iter()
                        .find(|t| &t.id == id)
                        .ok_or("依赖任务不存在")?;
                    if other.project_id != task.project_id {
                        return Err("首版仅支持同项目依赖".into());
                    }
                    if reaches(&self.tasks, id, task_id, &mut HashSet::new()) {
                        return Err("依赖会产生循环".into());
                    }
                }
                next.tasks
                    .iter_mut()
                    .find(|t| &t.id == task_id)
                    .unwrap()
                    .dependencies = dependencies.clone();
            }
            Command::SetStatus { task_id, status } => {
                let task = self
                    .tasks
                    .iter()
                    .find(|t| &t.id == task_id)
                    .ok_or("任务不存在")?;
                if *status == Status::Accepted {
                    return Err("请通过产物验收区完成逐项检查与人工验收".into());
                }
                let valid = task.status == *status
                    || *status == Status::Todo
                    || matches!(
                        (&task.status, status),
                        (Status::Todo, Status::Doing)
                            | (Status::Doing, Status::Review)
                            | (Status::Review, Status::Accepted)
                            | (Status::Review, Status::Doing)
                    );
                if !valid {
                    return Err("请按待办 → 进行中 → 待验收 → 人工验收的顺序推进".into());
                }
                if *status != Status::Todo
                    && task.dependencies.iter().any(|id| {
                        self.tasks
                            .iter()
                            .any(|t| &t.id == id && t.status != Status::Accepted)
                    })
                {
                    return Err("前置任务尚未人工验收".into());
                }
                if task.status == Status::Accepted
                    && *status != Status::Accepted
                    && self
                        .tasks
                        .iter()
                        .any(|t| t.dependencies.contains(task_id) && t.status != Status::Todo)
                {
                    return Err("请先重新打开下游任务，再撤回前置任务验收".into());
                }
                next.tasks
                    .iter_mut()
                    .find(|t| &t.id == task_id)
                    .unwrap()
                    .status = status.clone();
                if *status == Status::Todo {
                    next.tasks
                        .iter_mut()
                        .find(|t| &t.id == task_id)
                        .unwrap()
                        .acceptance_decision = None;
                }
            }
        }
        if let Command::EditTask { task_id, .. } | Command::SetDependencies { task_id, .. } =
            command
        {
            let t = next.tasks.iter_mut().find(|t| &t.id == task_id).unwrap();
            let old = self.tasks.iter().find(|t| &t.id == task_id).unwrap();
            if t.title != old.title
                || t.description != old.description
                || t.dependencies != old.dependencies
            {
                t.content_version += 1;
                t.acceptance_decision = None;
            }
        }
        next.revision += 1;
        Ok(next)
    }
}
