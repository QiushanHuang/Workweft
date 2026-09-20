"""Build ordered next-step recommendations from a workspace snapshot.

Produced by local Codex run 29d5e099-53cc-4045-b32f-3f4858b5281e.
"""


def recommend(snapshot):
    """Return recommendations without modifying the snapshot or its tasks."""
    active_projects = {
        project["id"]
        for project in snapshot.get("projects", [])
        if not project.get("archived", False)
    }
    tasks = snapshot.get("tasks", [])
    accepted_ids = {task["id"] for task in tasks if task["status"] == "accepted"}
    buckets = {category: [] for category in ("review", "doing", "ready", "blocked")}
    reasons = {
        "review": "待验收，请检查任务成果。",
        "doing": "进行中，请继续推进。",
        "ready": "依赖已满足，可以开始。",
        "blocked": "依赖缺失或尚未验收，请先处理依赖。",
    }
    for task in tasks:
        if task["project_id"] not in active_projects or task["status"] == "accepted":
            continue
        blocking_ids = [
            dependency
            for dependency in task.get("dependencies", [])
            if dependency not in accepted_ids
        ]
        if blocking_ids:
            category = "blocked"
        elif task["status"] in ("review", "doing"):
            category = task["status"]
        else:
            category = "ready"
        buckets[category].append(
            {
                "task_id": task["id"],
                "category": category,
                "reason": reasons[category],
                "blocking_ids": blocking_ids,
            }
        )
    return [row for rows in buckets.values() for row in rows]
