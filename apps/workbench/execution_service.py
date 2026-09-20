"""Select execution backend without relabelling or replaying historical school runs."""

from local_runner import LocalRunner
from dispatch import Dispatcher


class ExecutionService:
    def __init__(self, database):
        self.legacy = Dispatcher(database.with_name(database.stem + "-runs.sqlite3"))
        self.local = LocalRunner(database.parent / "codex-runs")

    def list(self):
        historical = [
            dict(job, backend="harness-remote", backend_available=False)
            for job in self.legacy.list()
        ]
        return self.local.list() + historical

    def submit(self, task, revision, profile="codex_document", execution=None):
        if profile not in ("codex_document", "codex_code"):
            raise ValueError("旧执行器已停用，请选择本地 Codex")
        if any(
            job["task_id"] == task["id"]
            and job["phase"]
            not in (
                "reported_success",
                "failed",
                "cancellation_confirmed",
                "prepare_failed",
            )
            for job in self.legacy.list()
        ):
            raise ValueError(
                "该任务的历史运行结果尚不确定，不能直接作为本地重试；请先记录处置决定"
            )
        return self.local.submit(
            task, revision, mode=profile.removeprefix("codex_"), execution=execution
        )

    def refresh(self, identifier):
        if any(job["id"] == identifier for job in self.local.list()):
            return self.local.refresh(identifier)
        job = next((job for job in self.legacy.list() if job["id"] == identifier), None)
        if job is None:
            raise ValueError("运行不存在")
        return dict(
            job,
            backend="harness-remote",
            backend_available=False,
            error="旧执行器已停用；显示最后保存的历史记录",
        )

    def cancel(self, identifier):
        return self.local.cancel(identifier)

    def resume_observation(self):
        for job in self.local.list():
            self.local.refresh(job["id"])
