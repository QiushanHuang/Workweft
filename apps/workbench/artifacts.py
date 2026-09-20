"""Write-once result snapshots. Hash one selected artifact, not a whole project tree."""

import hashlib
import json
import os
from pathlib import Path
import re
import stat


class ArtifactStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def read(self, digest):
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("产物标识无效")
        descriptor = os.open(
            self.root / (digest + ".json"), os.O_RDONLY | os.O_NOFOLLOW
        )
        with os.fdopen(descriptor, "rb") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                raise ValueError("产物不是普通文件")
            raw = file.read(16_777_217)
        if len(raw) > 16_777_216 or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("产物内容不完整或已改变，不能验收")
        return json.loads(raw)

    def freeze(self, job):
        if not job.get("result") or job["phase"] not in (
            "reported_success",
            "verification_failed",
        ):
            raise ValueError("此运行尚无可归档的交付物")
        result = json.loads(job["result"])
        kind = "code" if result.get("kind") == "code" else "document"
        payload = result.get("patch" if kind == "code" else "text")
        if (
            not isinstance(payload, str)
            or not payload.strip()
            or result.get("truncated")
        ):
            raise ValueError("缺少完整正文/补丁；截断或空结果不能作为验收产物")
        bundle = {
            "schema": "HCTArtifactBundleV1",
            "run_id": job["id"],
            "run_phase": job["phase"],
            "task_id": job["task_id"],
            "task_title": job.get("title"),
            "task_description": job.get("description"),
            "task_version": job.get("task_version", 0),
            "dependency_bindings": job.get("dependency_bindings", {}),
            "criteria": job.get("criteria", []),
            "backend": job.get("backend", "harness-remote"),
            "source_root": job.get("source_root"),
            "input_bindings": job.get("input_bindings", {}),
            "session_id": job.get("session_id"),
            "allowed_paths": job.get("allowed_paths", []),
            "test_files": job.get("test_files", []),
            "result": result,
        }
        raw = json.dumps(
            bundle, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
        if len(raw) > 16_777_216:
            raise ValueError("单份产物超过 16 MB，请拆分任务")
        digest = hashlib.sha256(raw).hexdigest()
        try:
            fd = os.open(
                self.root / (digest + ".json"),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            self.read(digest)
        else:
            with os.fdopen(fd, "wb") as file:
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
        verification = (
            (
                "passed"
                if result.get("verification_passed") is True
                and job["phase"] == "reported_success"
                else "failed"
            )
            if kind == "code"
            else "not_run"
        )
        return {
            "task_id": job["task_id"],
            "task_version": job.get("task_version", 0),
            "run_id": job["id"],
            "title": str(job.get("title") or "任务")[:120]
            + " · "
            + ("代码补丁" if kind == "code" else "文档")
            + " · "
            + job["id"][:8],
            "kind": kind,
            "sha256": digest,
            "storage_ref": "artifact:" + digest,
            "verification": verification,
            "dependency_bindings": job.get("dependency_bindings", {}),
        }
