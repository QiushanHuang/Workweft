// Review is a projection over core facts. No source patches are applied here.
export function renderReviewPanel(
  container,
  task,
  { state, element, command, reopen, request, error },
) {
  const section = element("section", "run-card");
  section.append(
    element("h3", "", "验收条件与产物版本"),
    element(
      "p",
      "",
      `任务内容版本 v${task.content_version} · 采用不等于验收，也不会自动应用代码补丁。`,
    ),
  );
  const criteria = element("textarea");
  criteria.rows = 4;
  criteria.value = (task.criteria || []).map((c) => c.text).join("\n");
  criteria.setAttribute("aria-label", "验收条件（每行一条）");
  criteria.disabled = task.status === "accepted";
  const save = element("button", "secondary", "保存验收条件");
  save.disabled = criteria.disabled;
  save.onclick = async () => {
    if (
      await command({
        type: "set_criteria",
        task_id: task.id,
        criteria: criteria.value
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      })
    )
      reopen();
  };
  section.append(
    criteria,
    save,
    element(
      "p",
      "",
      "修改任务内容、依赖或条件会使旧版本产物不能直接用于当前验收。",
    ),
  );
  const artifacts = (state.artifacts || []).filter(
    (a) => a.task_id === task.id,
  );
  if (!artifacts.length)
    section.append(
      element(
        "p",
        "",
        "暂无产物版本。运行完成后，在执行记录中点击“归档并进入验收”。",
      ),
    );
  for (const artifact of artifacts.slice().reverse()) {
    const card = element("article", "run-card");
    const current = artifact.task_version === task.content_version;
    const decisions = (state.decisions || []).filter(
      (d) => d.artifact_id === artifact.id,
    );
    const latest = decisions
      .filter((d) => d.task_version === task.content_version)
      .at(-1);
    const verificationNames = {
      passed: "独立验证通过",
      failed: "验证未通过",
      not_run: "未运行机器验证，需人工核对",
      unknown: "验证情况未知",
    };
    card.append(
      element("h4", "", `产物 v${artifact.ordinal} · ${artifact.title}`),
      element(
        "p",
        "",
        `生成任务版本：${artifact.task_version || "未知"} · ${verificationNames[artifact.verification] || artifact.verification} · ${current ? "对应当前任务" : "旧版/未知绑定，不可用于当前采用"}`,
      ),
      element("p", "", `来源运行：${artifact.run_id}`),
    );
    const preview = element("button", "secondary", "查看冻结内容");
    const body = element("pre");
    body.hidden = true;
    preview.onclick = async () => {
      try {
        const bundle = await request("/api/artifacts/" + artifact.id);
        body.textContent =
          bundle.result.kind === "code"
            ? bundle.result.patch
            : bundle.result.text;
        body.hidden = !body.hidden;
      } catch (e) {
        error(e.message);
      }
    };
    card.append(preview, body);
    const choices = [];
    for (const criterion of task.criteria || []) {
      const label = element("label", "check");
      const checkbox = element("input");
      checkbox.type = "checkbox";
      checkbox.checked = Boolean(
        latest?.checked_criteria.includes(criterion.id),
      );
      checkbox.disabled = !current || task.status === "accepted";
      label.append(checkbox, document.createTextNode(criterion.text));
      choices.push([criterion.id, checkbox]);
      card.append(label);
    }
    const reason = element("textarea");
    reason.rows = 2;
    reason.value = latest?.reason || "";
    reason.disabled = task.status === "accepted";
    reason.placeholder = "说明采用或拒绝的依据";
    reason.setAttribute("aria-label", `产物 v${artifact.ordinal} 决定理由`);
    card.append(reason);
    for (const [disposition, label] of [
      ["adopt", "记录采用（不应用补丁）"],
      ["reject", "记录拒绝"],
    ]) {
      const button = element("button", "secondary", label);
      button.disabled =
        task.status === "accepted" || (disposition === "adopt" && !current);
      button.onclick = async () => {
        if (
          await command({
            type: "record_decision",
            task_id: task.id,
            artifact_id: artifact.id,
            disposition,
            checked_criteria: choices
              .filter(([, box]) => box.checked)
              .map(([id]) => id),
            reason: reason.value,
          })
        )
          reopen();
      };
      card.append(button);
    }
    for (const decision of decisions.slice().reverse()) {
      card.append(
        element(
          "p",
          "",
          `${decision.disposition === "adopt" ? "采用" : "拒绝"} · 任务 v${decision.task_version} · 已核对 ${decision.checked_criteria.length}/${decision.criteria_snapshot?.length || 0} 条 · ${decision.reason}`,
        ),
      );
      const recorded = element("details");
      recorded.append(element("summary", "", "查看当时的逐项检查"));
      for (const criterion of decision.criteria_snapshot || [])
        recorded.append(
          element(
            "p",
            "",
            `${decision.checked_criteria.includes(criterion.id) ? "已核对" : "未核对"}：${criterion.text}`,
          ),
        );
      card.append(recorded);
    }
    if (latest?.disposition === "adopt" && current) {
      const accept = element("button", "", "确认人工验收");
      accept.disabled =
        task.status !== "review" ||
        !(task.criteria || []).length ||
        !task.criteria.every((c) => latest.checked_criteria.includes(c.id)) ||
        (artifact.kind === "code" && artifact.verification !== "passed");
      accept.onclick = async () => {
        if (
          await command({
            type: "accept_task",
            task_id: task.id,
            decision_id: latest.id,
          })
        )
          reopen();
      };
      card.append(accept);
    }
    section.append(card);
  }
  if (task.status === "accepted" && !task.acceptance_decision)
    section.append(
      element("p", "", "这是旧版人工状态，未补写或伪造版本化验收记录。"),
    );
  container.append(section);
}
