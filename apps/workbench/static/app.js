import { renderReviewPanel } from "./review-panel.js";
const $ = (selector) => document.querySelector(selector);
const labels = {
  todo: "待办",
  doing: "进行中",
  review: "待验收",
  accepted: "已人工验收",
};
let state = { projects: [], tasks: [], events: [], revision: 0 };
let projectId = localStorage.getItem("hct-project");
let view = "board";
let editing = null;
let editRevision = null;
let token = "";
let busy = false;
let runPoll = null;
let showArchived = false;
let importPreview = null;

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}
function error(message = "") {
  $("#error").textContent = message;
  $("#error").hidden = !message;
}
async function request(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "读取失败");
  return body;
}
async function refresh() {
  try {
    state = await request("/api/snapshot");
    if (!state.projects.some((p) => p.id === projectId))
      projectId = state.projects[0]?.id;
    error();
    render();
  } catch (e) {
    error(e.message);
  }
}
async function command(value, revision = state.revision) {
  if (busy) return false;
  busy = true;
  document
    .querySelectorAll("button[type=submit]")
    .forEach((b) => (b.disabled = true));
  try {
    state = await request("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-HCT-Token": token },
      body: JSON.stringify({ expected_revision: revision, command: value }),
    });
    if (!projectId) projectId = state.projects[0]?.id;
    error();
    render();
    return true;
  } catch (e) {
    error(e.message);
    const dialog = document.querySelector("dialog[open]");
    if (dialog) {
      let notice = dialog.querySelector(".form-error");
      if (!notice) {
        notice = element("p", "form-error");
        notice.setAttribute("role", "alert");
        dialog.append(notice);
      }
      notice.textContent = e.message;
    }
    return false;
  } finally {
    busy = false;
    document
      .querySelectorAll("button[type=submit]")
      .forEach((b) => (b.disabled = false));
  }
}
function selectedTasks() {
  return state.tasks.filter((t) => t.project_id === projectId);
}
function blocked(task) {
  return task.dependencies.some(
    (id) => state.tasks.find((t) => t.id === id)?.status !== "accepted",
  );
}
function render() {
  clearTimeout(runPoll);
  const projects = $("#projects");
  projects.replaceChildren();
  state.projects
    .filter((p) => showArchived || !p.archived)
    .forEach((p) => {
      const button = element(
        "button",
        `project-item ${p.id === projectId ? "selected" : ""}`,
        `${p.archived ? "▣" : "◦"}  ${p.title}`,
      );
      button.onclick = () => {
        projectId = p.id;
        localStorage.setItem("hct-project", p.id);
        render();
      };
      projects.append(button);
    });
  const project = state.projects.find((p) => p.id === projectId);
  $("#heading").textContent =
    view === "board" || view === "canvas"
      ? project?.title || "项目工作台"
      : view === "runs"
        ? "执行记录"
        : view === "lookup"
          ? "全局查找 · 项目元数据"
          : view === "next"
            ? "下一步 · 推荐与阻塞"
            : "活动记录";
  $("#description").textContent =
    project && (view === "board" || view === "canvas")
      ? project.description || "把目标拆成清晰的下一步，让执行过程有据可查。"
      : "项目规划、人工决定和执行结果，各自保留来源。";
  $("#new-task").disabled = !project || project.archived;
  $("#archive-project").disabled = !project;
  $("#archive-project").textContent = project?.archived
    ? "恢复项目"
    : "归档项目";
  $("#revision").textContent = `版本 ${state.revision}`;
  document.querySelectorAll("[data-view]").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === view);
    b.setAttribute("aria-current", b.dataset.view === view ? "page" : "false");
  });
  const tasks = selectedTasks();
  const metrics = $("#metrics");
  metrics.replaceChildren();
  [
    [tasks.length, "全部任务", "清晰拆解项目目标"],
    [
      tasks.filter((t) => t.status === "doing").length,
      "进行中",
      "当前投入的工作",
    ],
    [tasks.filter(blocked).length, "等待依赖", "先完成前置任务"],
    [
      tasks.filter((t) => t.status === "accepted").length,
      "已人工验收",
      "你的确认与管理决定",
    ],
  ].forEach(([count, title, note]) => {
    const card = element("div", "metric");
    card.append(
      element("small", "", title),
      element("strong", "", String(count)),
      element("span", "", note),
    );
    metrics.append(card);
  });
  $("#view-label").textContent = {
    board: "任务看板",
    canvas: "依赖关系 · 只读",
    runs: "执行记录 · 本地与历史",
    next: "下一步 · 按当前任务事实推荐",
    lookup: "查找任务、引用、产物与决定",
    activity: "最近活动 · 最多 100 条",
  }[view];
  $("#search").closest("label").hidden = view !== "board";
  const content = $("#content");
  content.replaceChildren();
  if (view === "lookup") {
    renderLookup(content);
    return;
  }
  if (view === "next") {
    renderNextUp(content);
    return;
  }
  if (view === "runs") {
    renderRuns(content);
    return;
  }
  if (view === "activity") {
    renderActivity(content);
    return;
  }
  if (!project) {
    const empty = element("div", "empty");
    empty.append(
      element("h2", "", "从一个明确的目标开始"),
      element("p", "", "创建项目，拆分任务，再用依赖关系安排工作顺序。"),
    );
    const button = element("button", "", "创建第一个项目");
    button.onclick = openProject;
    empty.append(button);
    content.append(empty);
    return;
  }
  if (view === "canvas") {
    renderCanvas(content, tasks);
    return;
  }
  const query = $("#search").value.toLowerCase();
  const filtered = tasks.filter((t) =>
    (t.title + " " + t.description).toLowerCase().includes(query),
  );
  const board = element("div", "board");
  Object.entries(labels).forEach(([status, label]) => {
    const column = element("section", "column");
    const heading = element("div", "column-heading", label);
    const list = filtered.filter((t) => t.status === status);
    heading.append(element("span", "", String(list.length)));
    column.append(heading);
    if (!list.length)
      column.append(
        element(
          "div",
          "empty",
          status === "todo" ? "点击「新建任务」添加下一步" : "暂无任务",
        ),
      );
    list.forEach((task) => {
      const card = element("button", "task-card");
      card.setAttribute("aria-label", `打开任务：${task.title}`);
      card.append(
        element(
          "span",
          `tag ${blocked(task) ? "blocked" : ""}`,
          blocked(task) ? "等待前置任务" : labels[task.status],
        ),
        element("h3", "", task.title),
        element("p", "", task.description || "添加描述与验收要点"),
      );
      const bottom = element("div", "card-bottom");
      bottom.append(
        element(
          "span",
          "",
          task.dependencies.length
            ? `${task.dependencies.length} 个前置任务`
            : "独立任务",
        ),
        element("span", "", "查看详情 ↗"),
      );
      card.append(bottom);
      card.onclick = () => openTask(task);
      column.append(card);
    });
    board.append(column);
  });
  content.append(board);
}

function openProject() {
  $("#project-form").reset();
  $("#project-dialog").querySelector(".form-error")?.remove();
  $("#project-dialog").showModal();
}
function openTask(task = null) {
  editing = task?.id || null;
  editRevision = state.revision;
  const form = $("#task-form");
  form.reset();
  form.elements.title.value = task?.title || "";
  form.elements.description.value = task?.description || "";
  form.elements.criteria.value = "";
  form.elements.criteria.closest("label").hidden = Boolean(task);
  form.elements.title.disabled = task?.status === "accepted";
  form.elements.description.disabled = task?.status === "accepted";
  $("#task-dialog-title").textContent = task ? "任务详情" : "新建任务";
  $("#task-meta").textContent = task
    ? `任务 ${task.id} · 内容版本 v${task.content_version}`
    : "保存后可设置前置任务";
  $("#task-dialog").querySelector(".form-error")?.remove();
  const controls = $("#task-controls");
  controls.replaceChildren();
  controls.hidden = !task;
  if (task) {
    const label = element("label", "", "任务状态");
    const select = element("select");
    Object.entries(labels).forEach(([key, value]) => {
      const option = element("option", "", value);
      option.value = key;
      if (key === "accepted") option.disabled = true;
      select.append(option);
    });
    select.value = task.status;
    label.append(select);
    const update = element("button", "secondary", "更新状态");
    update.onclick = async () => {
      if (
        await command(
          { type: "set_status", task_id: task.id, status: select.value },
          editRevision,
        )
      )
        $("#task-dialog").close();
    };
    controls.append(label, update);
    renderReviewPanel(controls, task, {
      state,
      element,
      request,
      error,
      command: (value) => command(value, editRevision),
      reopen: () => openTask(state.tasks.find((t) => t.id === task.id)),
    });
    const title = element("p", "", "前置任务（仅待办状态可修改）");
    controls.append(title);
    const choices = selectedTasks().filter((t) => t.id !== task.id);
    if (!choices.length)
      controls.append(element("small", "", "同项目尚无其他任务"));
    choices.forEach((t) => {
      const row = element("label", "check");
      const check = document.createElement("input");
      check.type = "checkbox";
      check.value = t.id;
      check.checked = task.dependencies.includes(t.id);
      check.disabled = task.status !== "todo";
      check.name = "dependency";
      row.append(check, document.createTextNode(t.title));
      controls.append(row);
    });
    const deps = element("button", "secondary", "保存前置任务");
    deps.disabled = task.status !== "todo";
    deps.onclick = async () => {
      const dependencies = [...controls.querySelectorAll("input:checked")].map(
        (c) => c.value,
      );
      if (
        await command(
          { type: "set_dependencies", task_id: task.id, dependencies },
          editRevision,
        )
      )
        $("#task-dialog").close();
    };
    controls.append(deps);
    controls.append(
      element("small", "", "人工验收不会自动标记远程执行或独立验证成功。"),
    );
    controls.append(
      element("h3", "", "文件与外部引用"),
      element(
        "p",
        "",
        "仅登记位置，不读取、移动或删除源文件。MindDesk 引用作为不透明标识保存。",
      ),
    );
    (state.assets || [])
      .filter((asset) => asset.task_id === task.id)
      .forEach((asset) => {
        const card = element("div", "run-card");
        card.append(
          element("strong", "", asset.title),
          element("p", "", `${asset.kind} · ${asset.target}`),
          element("p", "", asset.description),
        );
        const remove = element("button", "secondary", "移除引用（保留源文件）");
        remove.disabled = task.status === "accepted";
        remove.onclick = async () => {
          if (
            await command(
              { type: "remove_asset", task_id: task.id, asset_id: asset.id },
              editRevision,
            )
          )
            openTask(state.tasks.find((t) => t.id === task.id));
        };
        card.append(remove);
        controls.append(card);
      });
    const assets = element("form");
    const field = (caption, node) => {
      const label = element("label", "", caption);
      label.append(node);
      assets.append(label);
      return node;
    };
    const name = field("引用名称", element("input"));
    name.required = true;
    name.maxLength = 160;
    const kind = field("引用类型", element("select"));
    for (const [key, label] of Object.entries({
      local_file: "本地文件路径",
      url: "网页地址",
      external_ref: "MindDesk / 外部不透明引用",
    })) {
      const option = element("option", "", label);
      option.value = key;
      kind.append(option);
    }
    const target = field("绝对路径 / URL / 外部标识", element("input"));
    target.required = true;
    target.maxLength = 4096;
    const desc = field("用途说明", element("input"));
    const add = element("button", "secondary", "登记引用");
    add.type = "submit";
    add.disabled = task.status === "accepted";
    assets.append(add);
    assets.onsubmit = async (event) => {
      event.preventDefault();
      if (
        await command(
          {
            type: "add_asset",
            task_id: task.id,
            title: name.value,
            kind: kind.value,
            target: target.value,
            description: desc.value,
          },
          editRevision,
        )
      )
        openTask(state.tasks.find((t) => t.id === task.id));
    };
    controls.append(assets);
  }
  $("#task-dialog").showModal();
}

function renderLookup(content) {
  content.append(
    element(
      "p",
      "view-note",
      "只搜索本应用已登记的元数据，不扫描文件内容。结果包含历史及归档项目。",
    ),
  );
  const form = element("form", "run-card"),
    input = element("input"),
    submit = element("button", "", "查找");
  input.setAttribute("aria-label", "全局搜索词");
  input.maxLength = 200;
  input.placeholder = "任务名称、文件路径、运行 ID 或决定理由";
  submit.type = "submit";
  form.append(input, submit);
  const results = element("div");
  content.append(form, results);
  form.onsubmit = async (event) => {
    event.preventDefault();
    submit.disabled = true;
    try {
      const data = await request(
        "/api/search?q=" + encodeURIComponent(input.value),
      );
      results.replaceChildren(
        element(
          "p",
          "",
          `找到 ${data.total} 条 · 数据版本 ${data.revision}${data.has_more ? " · 仅显示前 100 条" : ""}`,
        ),
      );
      const names = {
        task: "任务",
        asset: "文件引用",
        artifact: "产物版本",
        decision: "采用/拒绝决定",
      };
      for (const item of data.items) {
        const card = element("article", "run-card");
        card.append(
          element(
            "span",
            "tag",
            `${names[item.kind]}${item.stale ? " · 旧版本" : ""}${item.archived ? " · 已归档" : ""}`,
          ),
          element("h3", "", item.label),
          element("p", "", item.project_title),
          element("p", "", item.excerpt),
        );
        const open = element("button", "secondary", "打开所属任务");
        open.onclick = async () => {
          try {
            state = await request("/api/snapshot");
            projectId = item.project_id;
            showArchived = true;
            view = "board";
            render();
            const task = state.tasks.find((t) => t.id === item.task_id);
            if (task) openTask(task);
            else error("任务已不可用");
          } catch (e) {
            error(e.message);
          }
        };
        card.append(open);
        results.append(card);
      }
    } catch (e) {
      error(e.message);
    } finally {
      submit.disabled = false;
    }
  };
}
async function renderNextUp(content) {
  try {
    const data = await request("/api/next-up");
    if (view !== "next" || !content.isConnected) return;
    if (data.revision !== state.revision) {
      error("任务状态已变化，请刷新后查看推荐");
      return;
    }
    const tasks = new Map(selectedTasks().map((t) => [t.id, t]));
    const rows = data.items.filter((row) => tasks.has(row.task_id));
    if (!rows.length)
      content.append(element("p", "empty", "当前项目没有待处理任务。"));
    const names = {
      review: "待验收",
      doing: "继续进行",
      ready: "可以开始",
      blocked: "等待依赖",
    };
    rows.forEach((row) => {
      const card = element("article", "run-card");
      card.append(
        element("span", "tag", names[row.category]),
        element("h3", "", tasks.get(row.task_id).title),
        element("p", "", row.reason),
      );
      if (row.blocking_ids.length)
        card.append(
          element(
            "p",
            "",
            `阻塞：${row.blocking_ids.map((id) => tasks.get(id)?.title || id).join("、")}`,
          ),
        );
      const open = element("button", "secondary", "查看任务");
      open.onclick = () => openTask(tasks.get(row.task_id));
      card.append(open);
      content.append(card);
    });
  } catch (e) {
    error(e.message);
  }
}
function renderCanvas(content, tasks) {
  if (!tasks.length) {
    content.append(
      element("div", "empty", "先创建任务，再在任务详情中设置依赖关系。"),
    );
    return;
  }
  content.append(
    element(
      "p",
      "view-note",
      "箭头从前置任务指向后续任务。此图和看板使用同一份项目数据；下方列表提供完整名称与键盘入口。",
    ),
  );
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  const depth = new Map();
  const levels = (t) => {
    if (depth.has(t.id)) return depth.get(t.id);
    const d = t.dependencies.length
      ? Math.max(
          ...t.dependencies.map((id) => levels(tasks.find((x) => x.id === id))),
        ) + 1
      : 0;
    depth.set(t.id, d);
    return d;
  };
  tasks.forEach(levels);
  const counts = new Map();
  const positions = new Map();
  tasks.forEach((t) => {
    const d = depth.get(t.id);
    const n = counts.get(d) || 0;
    counts.set(d, n + 1);
    positions.set(t.id, { x: 30 + d * 245, y: 30 + n * 100 });
  });
  const width = Math.max(700, (Math.max(...depth.values()) + 1) * 245 + 30),
    height = Math.max(250, Math.max(...counts.values()) * 100 + 30);
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "任务依赖关系图");
  const defs = document.createElementNS(ns, "defs");
  const marker = document.createElementNS(ns, "marker");
  Object.entries({
    id: "arrow",
    viewBox: "0 0 10 10",
    refX: 9,
    refY: 5,
    markerWidth: 7,
    markerHeight: 7,
    orient: "auto-start-reverse",
  }).forEach(([k, v]) => marker.setAttribute(k, v));
  const arrow = document.createElementNS(ns, "path");
  arrow.setAttribute("d", "M 0 0 L 10 5 L 0 10");
  marker.append(arrow);
  defs.append(marker);
  svg.append(defs);
  tasks.forEach((t) =>
    t.dependencies.forEach((id) => {
      const a = positions.get(id),
        b = positions.get(t.id);
      const path = document.createElementNS(ns, "path");
      path.setAttribute(
        "d",
        `M ${a.x + 205} ${a.y + 30} C ${a.x + 230} ${a.y + 30},${b.x - 25} ${b.y + 30},${b.x} ${b.y + 30}`,
      );
      path.setAttribute("marker-end", "url(#arrow)");
      svg.append(path);
    }),
  );
  tasks.forEach((t) => {
    const p = positions.get(t.id);
    const rect = document.createElementNS(ns, "rect");
    Object.entries({ x: p.x, y: p.y, width: 205, height: 62, rx: 10 }).forEach(
      ([k, v]) => rect.setAttribute(k, v),
    );
    const text = document.createElementNS(ns, "text");
    text.setAttribute("x", p.x + 13);
    text.setAttribute("y", p.y + 25);
    text.textContent =
      [...t.title].slice(0, 13).join("") +
      ([...t.title].length > 13 ? "…" : "");
    const status = document.createElementNS(ns, "text");
    status.setAttribute("x", p.x + 13);
    status.setAttribute("y", p.y + 46);
    status.textContent = labels[t.status];
    svg.append(rect, text, status);
  });
  const graph = element("div", "graph");
  graph.append(svg);
  content.append(graph);
  const list = element("ul", "graph-list");
  tasks.forEach((t) => {
    const row = element("li");
    const button = element("button", "secondary", t.title);
    button.onclick = () => openTask(t);
    row.append(
      button,
      document.createTextNode(
        " ← " +
          (t.dependencies
            .map((id) => tasks.find((x) => x.id === id)?.title)
            .join("、") || "无前置任务"),
      ),
    );
    list.append(row);
  });
  content.append(list);
}
async function renderRuns(content) {
  content.append(
    element(
      "p",
      "view-note",
      "新任务使用本机 Codex CLI 与当前账户额度；模型推理仍需网络。旧执行器已停用，历史结果保留。代码在独立副本内修改，不自动覆盖原源码。",
    ),
  );
  try {
    const data = await request("/api/runs");
    if (view !== "runs" || !content.isConnected) return;
    const dispatchForm = element("form", "run-card");
    const dispatchSelect = element("select");
    dispatchSelect.setAttribute("aria-label", "待派发任务");
    selectedTasks()
      .filter((task) => task.status !== "accepted")
      .forEach((task) => {
        const option = element("option", "", task.title);
        option.value = task.id;
        dispatchSelect.append(option);
      });
    const profileSelect = element("select");
    profileSelect.setAttribute("aria-label", "执行模式");
    for (const [value, label] of Object.entries({
      codex_document: "本地 Codex · 文档任务",
      codex_code: "本地 Codex · 工作台 Python 代码任务",
    })) {
      const option = element("option", "", label);
      option.value = value;
      profileSelect.append(option);
    }
    const allowedInput = element("input");
    allowedInput.placeholder = "apps/workbench/next_up.py";
    allowedInput.setAttribute("aria-label", "允许修改的文件（逗号分隔）");
    const testsInput = element("input");
    testsInput.placeholder = "test_next_up.py";
    testsInput.setAttribute("aria-label", "已有测试文件（逗号分隔）");
    allowedInput.hidden = testsInput.hidden = true;
    profileSelect.onchange = () => {
      allowedInput.hidden = testsInput.hidden =
        profileSelect.value !== "codex_code";
    };
    const dispatchButton = element("button", "", "派发至本地 Codex");
    dispatchButton.type = "submit";
    dispatchButton.disabled = !dispatchSelect.options.length;
    dispatchForm.append(
      element("h3", "", "直接派发任务"),
      element(
        "p",
        "",
        "使用当前 Codex 登录 · 模型阶段最多 15 分钟 · 每个验证最多 60 秒 · 同时 1 个任务。代码输入限本产品工作台 Python 源码，控制器不可作为修改目标。",
      ),
      dispatchSelect,
      profileSelect,
      allowedInput,
      testsInput,
      dispatchButton,
    );
    dispatchForm.onsubmit = async (event) => {
      event.preventDefault();
      dispatchButton.disabled = true;
      try {
        await post("/api/runs/dispatch", {
          task_id: dispatchSelect.value,
          profile: profileSelect.value,
          execution:
            profileSelect.value === "codex_code"
              ? {
                  allowed_paths: allowedInput.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                  test_files: testsInput.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                }
              : {},
          expected_revision: state.revision,
        });
        error();
        render();
      } catch (e) {
        error(e.message);
        dispatchButton.disabled = false;
      }
    };
    content.append(dispatchForm);
    const form = element("form", "run-card");
    const select = element("select");
    select.setAttribute("aria-label", "关联任务");
    selectedTasks().forEach((task) => {
      const option = element("option", "", task.title);
      option.value = task.id;
      select.append(option);
    });
    const input = element("input");
    input.placeholder = "云端 logical_run_id（UUID）";
    input.setAttribute("aria-label", "云端运行 ID");
    input.required = true;
    const submit = element("button", "", "关联运行");
    submit.type = "submit";
    submit.disabled = !selectedTasks().length;
    form.append(
      element("h3", "", "关联历史执行记录（不联网）"),
      select,
      input,
      submit,
    );
    const post = async (path, payload) =>
      request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-HCT-Token": token },
        body: JSON.stringify(payload),
      });
    form.onsubmit = async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        await post("/api/runs/bind", {
          task_id: select.value,
          run_id: input.value.trim(),
        });
        error();
        render();
      } catch (e) {
        error(e.message);
      } finally {
        submit.disabled = false;
      }
    };
    content.append(form);
    const ids = new Set(selectedTasks().map((task) => task.id));
    const dispatched = new Set((data.dispatches || []).map((run) => run.id));
    (data.dispatches || [])
      .filter((run) => ids.has(run.task_id))
      .forEach((run) => {
        const card = element("article", "run-card");
        card.append(
          element("h3", "", run.title),
          element(
            "p",
            "",
            `${run.backend === "codex-local" ? "本地 Codex" : "历史执行器 · 只读"} · ${run.phase}`,
          ),
          element("p", "", run.id),
        );
        if (run.error) card.append(element("p", "", run.error));
        if (run.backend === "codex-local") {
          if (run.session_id)
            card.append(element("p", "", `会话：${run.session_id}`));
          if (
            run.cancel_requested &&
            ![
              "cancelled",
              "reported_success",
              "failed",
              "interrupted",
              "verification_failed",
            ].includes(run.phase)
          )
            card.append(element("p", "", "正在取消，等待执行进程确认停止…"));
        }
        if (run.result) {
          const result = JSON.parse(run.result);
          const details = element("details");
          details.append(
            element(
              "summary",
              "",
              result.kind === "code"
                ? "查看代码结果（不会自动覆盖本地源码）"
                : "查看交付文档（模型输出，尚未人工验收）",
            ),
            element("pre", "", result.text),
          );
          if (result.truncated)
            details.append(
              element("p", "", "结果超过显示上限，当前为截断内容。"),
            );
          if (result.kind === "code") {
            card.append(
              element(
                "p",
                "",
                `独立测试：${result.verification_passed ? "通过" : "未通过"} · 修改文件：${result.changed_paths.join("、")}`,
              ),
            );
            const verification = element("details");
            verification.append(
              element("summary", "", "测试日志"),
              element("pre", "", result.verification_log),
            );
            card.append(verification);
          }
          const download = element(
            "button",
            "",
            result.kind === "code" ? "下载代码补丁" : "下载 Markdown",
          );
          download.onclick = () => {
            const url = URL.createObjectURL(
              new Blob([result.kind === "code" ? result.patch : result.text], {
                type: "text/plain;charset=utf-8",
              }),
            );
            const link = element("a");
            link.href = url;
            link.download = `workweft-${run.id}.${result.kind === "code" ? "patch" : "md"}`;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          };
          card.append(details, download);
          const capture = element("button", "secondary", "归档并进入验收");
          capture.onclick = async () => {
            capture.disabled = true;
            try {
              state = await post("/api/artifacts/capture", {
                run_id: run.id,
                expected_revision: state.revision,
              });
              render();
              openTask(state.tasks.find((t) => t.id === run.task_id));
            } catch (e) {
              error(e.message);
              capture.disabled = false;
            }
          };
          card.append(capture);
        }
        const button = element("button", "", "刷新执行与结果");
        button.onclick = async () => {
          button.disabled = true;
          button.textContent = "读取中…";
          try {
            await post("/api/runs/reconcile", { run_id: run.id });
            error();
            render();
          } catch (e) {
            error(e.message);
            button.disabled = false;
            button.textContent = "重试读取";
          }
        };
        button.disabled = run.backend === "harness-remote";
        card.append(button);
        if (
          run.backend === "codex-local" &&
          ![
            "reported_success",
            "failed",
            "cancellation_confirmed",
            "unrecoverable",
            "prepare_failed",
            "verification_failed",
            "cancelled",
            "interrupted",
          ].includes(run.phase)
        ) {
          const cancel = element("button", "", "取消本地任务");
          cancel.disabled = run.cancel_requested;
          cancel.onclick = async () => {
            cancel.disabled = true;
            try {
              await post("/api/runs/cancel", { run_id: run.id });
              error();
              render();
            } catch (e) {
              error(e.message);
              cancel.disabled = false;
            }
          };
          card.append(cancel);
        }
        content.append(card);
      });
    (data.linked || [])
      .filter((run) => ids.has(run.task_id) && !dispatched.has(run.id))
      .forEach((run) => {
        const card = element("article", "run-card");
        const task = state.tasks.find((task) => task.id === run.task_id);
        card.append(
          element("h3", "", task.title),
          element("p", "", run.id),
          element("p", "", `云端日志状态：${run.state}`),
          element("p", "", `上次成功查询：${run.checked_at || "尚未查询"}`),
        );
        if (run.error) card.append(element("p", "", run.error));
        const button = element("button", "", "查询云端状态");
        button.onclick = async () => {
          button.disabled = true;
          button.textContent = "查询中…";
          try {
            await post("/api/runs/refresh", { run_id: run.id });
            error();
            render();
          } catch (e) {
            error(e.message);
            button.disabled = false;
            button.textContent = "重试查询";
          }
        };
        card.append(button);
        content.append(card);
      });
    content.append(element("h2", "", "历史验证记录（非实时）"));
    data.runs.forEach((run) => {
      const card = element("article", "run-card");
      card.append(
        element("span", "tag", "历史记录 · 独立测试通过"),
        element("h3", "", run.model_requested),
        element(
          "p",
          "",
          `记录时间：${run.recorded_at} · 耗时 ${(run.duration_ms / 1000).toFixed(1)} 秒`,
        ),
        element("p", "", `改动：${run.changed_paths.join("、")}`),
        element("p", "", `来源：${run.source}`),
        element("p", "", `限制：${run.limitations.join(" ")}`),
      );
      content.append(card);
    });
    const fingerprint = JSON.stringify(data.dispatches);
    const poll = async () => {
      if (view !== "runs" || !content.isConnected) return;
      try {
        const latest = await request("/api/runs");
        if (
          JSON.stringify(latest.dispatches) !== fingerprint &&
          !content.querySelector("form:focus-within")
        ) {
          render();
          return;
        }
      } catch (_) {
        /* Keep last observed state; explicit refresh reports connection errors. */
      }
      runPoll = setTimeout(poll, 5000);
    };
    runPoll = setTimeout(poll, 5000);
  } catch (e) {
    error(e.message);
  }
}
function renderActivity(content) {
  const names = {
    create_project: "创建项目",
    create_task: "创建任务",
    edit_task: "编辑任务",
    set_status: "更新状态",
    set_dependencies: "更新依赖",
    add_asset: "登记文件引用",
    remove_asset: "移除文件引用",
    set_project_archived: "归档/恢复项目",
    import_workspace: "导入项目副本",
    set_criteria: "更新验收条件",
    register_artifact: "归档产物版本",
    record_decision: "记录产物决定",
    accept_task: "按版本人工验收",
  };
  const ids = new Set(selectedTasks().map((t) => t.id));
  const events = state.events.filter(
    (e) =>
      !projectId ||
      e.command.project_id === projectId ||
      ids.has(e.command.task_id) ||
      e.command.type === "create_project",
  );
  if (!events.length)
    content.append(
      element("div", "empty", "创建项目或更新任务后，操作会自动记录在这里。"),
    );
  events.forEach((e) => {
    const card = element("div", "event-card");
    const task = state.tasks.find((t) => t.id === e.command.task_id);
    card.append(
      element(
        "span",
        "",
        `${names[e.command.type]} · ${e.command.title || task?.title || ""} ${e.command.status ? `→ ${labels[e.command.status]}` : ""}`,
      ),
      element("time", "", new Date(e.created_at).toLocaleString()),
    );
    content.append(card);
  });
}
$("#new-project").onclick = openProject;
$("#new-task").onclick = () => openTask();
$("#refresh").onclick = refresh;
$("#search").oninput = render;
document.querySelectorAll("[data-view]").forEach(
  (b) =>
    (b.onclick = () => {
      view = b.dataset.view;
      error();
      render();
    }),
);
document
  .querySelectorAll(".close")
  .forEach((b) => (b.onclick = () => b.closest("dialog").close()));
$("#project-form").onsubmit = async (e) => {
  e.preventDefault();
  const data = new FormData(e.target);
  if (
    await command({
      type: "create_project",
      title: data.get("title"),
      description: data.get("description"),
    })
  ) {
    projectId = state.projects.at(-1).id;
    $("#project-dialog").close();
    render();
  }
};
$("#task-form").onsubmit = async (e) => {
  e.preventDefault();
  if (
    editing &&
    state.tasks.find((t) => t.id === editing)?.status === "accepted"
  ) {
    error("请先重新打开已验收任务");
    return;
  }
  const data = new FormData(e.target);
  const value = {
    type: editing ? "edit_task" : "create_task",
    title: data.get("title"),
    description: data.get("description"),
    ...(editing
      ? { task_id: editing }
      : {
          project_id: projectId,
          criteria: String(data.get("criteria") || "")
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean),
        }),
  };
  if (await command(value, editRevision)) $("#task-dialog").close();
};
const projectTools = element("div", "header-actions");
const archive = element("button", "secondary", "归档项目");
archive.id = "archive-project";
archive.onclick = async () => {
  const project = state.projects.find((p) => p.id === projectId);
  if (
    project &&
    (await command({
      type: "set_project_archived",
      project_id: project.id,
      archived: !project.archived,
    }))
  ) {
    showArchived = true;
    render();
  }
};
const archived = element("button", "secondary", "显示/隐藏归档");
archived.onclick = () => {
  showArchived = !showArchived;
  render();
};
const importButton = element("button", "secondary", "导入 JSON / MindDesk");
importButton.onclick = () => $("#import-dialog").showModal();
const minddesk = element("a", "button secondary", "导出 MindDesk");
minddesk.href = "/api/minddesk/export";
minddesk.download = "workweft-minddesk.json";
projectTools.append(archive, archived, importButton, minddesk);
$("#description").after(projectTools);
$("#close-import").onclick = () => $("#import-dialog").close();
$("#import-file").onchange = async (event) => {
  importPreview = null;
  $("#apply-import").disabled = true;
  $("#import-error").textContent = "";
  try {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 1000000) throw new Error("单次导入限 1 MB，请分项目导出");
    const document = JSON.parse(await file.text());
    importPreview = await request("/api/import/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-HCT-Token": token },
      body: JSON.stringify(document),
    });
    $("#import-preview").textContent =
      `项目 ${importPreview.projects} · 任务 ${importPreview.tasks} · 引用 ${importPreview.assets}\n${importPreview.titles.join("\n")}\n\n${importPreview.warning}`;
    $("#apply-import").disabled = false;
  } catch (e) {
    $("#import-error").textContent = e.message;
  }
};
$("#apply-import").onclick = async () => {
  if (!importPreview) return;
  $("#apply-import").disabled = true;
  try {
    state = await request("/api/import/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-HCT-Token": token },
      body: JSON.stringify({ preview_id: importPreview.preview_id }),
    });
    importPreview = null;
    $("#import-dialog").close();
    projectId = state.projects.at(-1)?.id;
    render();
  } catch (e) {
    $("#import-error").textContent = e.message;
  }
};
try {
  token = (await request("/api/session")).token;
  await refresh();
} catch (e) {
  error(e.message);
}
