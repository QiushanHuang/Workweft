"""Search app-owned metadata only. No filesystem reads or external indexing."""


def search(snapshot, query, limit=100):
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("搜索词不能超过 200 字符")
    needle = query.strip().casefold()
    answer = {
        "revision": snapshot["revision"],
        "query": query,
        "items": [],
        "total": 0,
        "has_more": False,
    }
    if not needle:
        return answer
    tasks = {t["id"]: t for t in snapshot["tasks"]}
    projects = {p["id"]: p for p in snapshot["projects"]}
    candidates = []
    for task in tasks.values():
        text = "\n".join(
            [task["title"], task["description"]]
            + [c["text"] for c in task.get("criteria", [])]
        )
        candidates.append(("task", task, task, task["title"], text, None))
    for kind, key in [
        ("asset", "assets"),
        ("artifact", "artifacts"),
        ("decision", "decisions"),
    ]:
        for record in snapshot.get(key, []):
            task = tasks.get(record["task_id"])
            if task is None:
                continue
            label = record.get("title") or (
                "采用决定" if record.get("disposition") == "adopt" else "拒绝决定"
            )
            text = "\n".join(
                str(record.get(k, ""))
                for k in (
                    "title",
                    "description",
                    "target",
                    "run_id",
                    "reason",
                    "artifact_id",
                )
            )
            text += "\n" + "\n".join(
                c["text"] for c in record.get("criteria_snapshot", [])
            )
            candidates.append(
                (
                    kind,
                    record,
                    task,
                    label,
                    label + "\n" + text,
                    record.get("task_version"),
                )
            )
    for kind, record, task, label, text, version in candidates:
        position = text.casefold().find(needle)
        if position < 0:
            continue
        project = projects.get(task["project_id"], {})
        answer["items"].append(
            {
                "kind": kind,
                "id": record["id"],
                "task_id": task["id"],
                "project_id": task["project_id"],
                "project_title": project.get("title", "未知项目"),
                "label": label,
                "excerpt": text[max(0, position - 40) : position + 180],
                "task_version": version,
                "stale": version is not None
                and version != task.get("content_version", 1),
                "archived": project.get("archived", False),
            }
        )
    answer["total"] = len(answer["items"])
    answer["has_more"] = answer["total"] > limit
    answer["items"] = answer["items"][:limit]
    return answer
