# User guide

[English](#installation) · [简体中文](#中文操作说明)

## Installation

The v0.3.0 downloadable app targets Apple Silicon macOS. It contains optimized
Rust binaries and the Python workbench, but does not bundle Python or Codex CLI.

1. Download the ZIP from this repository's Releases and extract it.
2. Check that `/usr/bin/python3 --version` reports Python 3.9 or newer. If the
   Apple developer tools are missing, install them with `xcode-select --install`.
3. Open the app. You can keep it in Applications or another local folder.
4. For agent execution, install and sign in to Codex CLI using its
   [official instructions](https://developers.openai.com/codex/cli/).
   Check `codex --version` and `codex login status` in your terminal.

This release is ad-hoc signed and not notarized by Apple. macOS may block a
downloaded app. Follow Apple's per-app approval instructions only if you trust
this release, or build from source. Do not disable Gatekeeper globally. No
installer changes your security settings or adds a background login service.

For a Python installed somewhere else, launch the executable with an explicit
`HCT_PYTHON` environment variable, for example:

```sh
HCT_PYTHON=/opt/homebrew/bin/python3 "/Applications/Harness Control Terminal 0.3.0.app/Contents/MacOS/harness-control-desktop"
```

## Your first document task

Create a project and a task. Example title: "Draft the launch checklist".
Describe the output: "Write result.md with installation, a first-use walkthrough
and a short troubleshooting section." Add two criteria, one per line:

```text
Lists prerequisites before installation steps
Includes a complete first-use example
```

Open **执行记录**, select the task and **本地 Codex · 文档任务**, then submit.
The task must have criteria and its dependencies must be accepted. Watch status
and inspect the returned document. Use **归档并进入验收** to capture the output,
then open the task, read its frozen content and check each criterion.

Record an adoption with a reason, then choose **确认人工验收**. If the result is
unsuitable, record a rejection and explain what needs to change. A saved decision
does not change any external source file.

## Task versions and dependencies

Changing a task title, description, criteria or dependencies advances its content
version. Saving unchanged text does not. An accepted task must be reopened before
editing. Old outputs and decision checklists stay visible as history.

To accept a code result, all current criteria must be checked, its independent
verification must have passed, and dependencies must match the accepted versions
used by the run. Test success is separate from your decision to accept the work.

## Code tasks

Code mode currently targets this workbench's Python modules, not arbitrary Git
repositories. The runner copies selected source into an isolated job directory,
restricts changed paths and runs the selected pre-existing tests independently.
Specify relative allowed Python paths and test files in the execution form.
The active runner/controller modules are excluded from agent editing.

For an installed app, register a source checkout in the app-data `sources.json`:

```json
{"workbench_root": "/absolute/path/to/Harness-Control-Terminal"}
```

Use an actual existing checkout. Changing this setting does not move source files.
Review the result patch and apply selected changes separately with your editor or
Git tools. There is no automatic source-patch adoption in v0.3.0.

## Search and file references

**全局查找** searches registered task text, criteria, file pointers, artifact
sources and decision reasons/checklists. It includes old versions and archived
projects and links each match back to its task. It does not index file contents.

File references are pointers, not uploads or managed copies. MindDesk export/import
exchanges metadata explicitly; it does not synchronize application databases.
Import creates a separate copy. Imported tasks retain criteria but not evidence
or acceptance claims from the source project.

## Backup and upgrades

On macOS, application data is under:

```text
~/Library/Application Support/local.harness.control/
  workbench.sqlite3       projects, criteria, artifacts and decisions
  artifacts/             frozen result bundles
  codex-runs/            local job database, inputs, output and logs
  sources.json           optional source checkout registration
  service.log            native app service log
```

Older installations may also have `workbench-runs.sqlite3` and other legacy
observation databases. Retain them when copying the directory.

Before an upgrade or complete backup, finish/cancel active runs, quit every app
window and stop any separately started browser server. Copy the entire data
directory to a dated backup. JSON and Markdown exports do not contain every run
input or artifact byte and are not a replacement for that copy.

v0.3.0 uses schema 4. Before first opening an older database with this release,
make the full backup described above; this public build does not automatically
create that backup. Older binaries cannot open schema 4. To try a backup, use a
separate copied data directory and set `HCT_DATABASE` to its `workbench.sqlite3`.
Do not test restoration over live data. Full restore rehearsal is still planned.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Native service cannot start | Check `service.log`, Python availability and any stale `sources.json` path. |
| Codex is not found | Put it on PATH or in the supported npm-global/Homebrew binary location; restart the app. |
| Authentication or quota error | Check your Codex CLI login/account. Preserve the failed run before retrying. |
| Result won't enter acceptance | Check task version, criteria, result availability, dependency versions and code verification. |
| Browser port is busy | Start with `HCT_PORT=4180 python3 apps/workbench/server.py`; open that loopback port. |
| Old school run cannot refresh | It is retained local history; this release does not reconnect to that executor. |

Closing the app stops its UI service. A detached model worker can continue, so
request cancellation before quitting if you want it to stop. Cancellation during
verification waits for the current bounded test to finish. Reopening observes
the saved job; it does not automatically resubmit it.

<a id="中文操作说明"></a>

## 中文操作说明

### 安装

下载 Release 中的 Apple Silicon ZIP，解压并打开应用。运行服务需要 Python 3.9+，
默认用 `/usr/bin/python3`；缺少 Apple 命令行工具时可运行 `xcode-select --install`。
执行 AI 任务还需要按 [Codex 官方说明](https://developers.openai.com/codex/cli/)
安装并登录 CLI。项目规划和已有记录查看不需要联网调用模型。

安装包使用临时本地签名，尚未经过 Apple 公证。若 macOS 拦截，请仅在确认信任此
下载来源后按系统的单应用批准流程处理，或选择从源码构建，不要全局关闭 Gatekeeper。

### 第一个任务

创建项目，再创建“编写发布清单”任务。描述输出要求，例如“生成 result.md，包含
安装、首次操作和常见问题”。验收条件每行一条，例如“安装前列出依赖”和“包含完整
首次操作示例”。到“执行记录”选任务及本地文档模式，提交并等待结果。

点击“归档并进入验收”，打开冻结内容，逐项检查并勾选条件。写明理由后记录采用，
再确认人工验收。不合适的结果可以记录拒绝。采用只保存选择，不会直接应用代码补丁。

### 继续项目

用依赖图看任务关系，用“下一步”选当前可推进的任务。“全局查找”可以搜索任务内容、
文件引用、产物来源和决定，包括历史版本与归档项目；不会遍历外部文件内容。
修改任务内容或条件会产生新版本，旧产物和旧决定仍然保留。已验收任务先重新打开再编辑。

代码模式当前限定工作台 Python 源码和预存测试。安装版可以用数据目录中的
`sources.json` 登记本地源码目录，字段为 `workbench_root`，值填写真实绝对路径。
执行在独立副本中进行，产生补丁后由你在编辑器或 Git 中应用。

### 备份、升级与排错

完整备份：先结束或取消运行任务，退出所有应用窗口和自行启动的浏览器服务，再复制
`~/Library/Application Support/local.harness.control/` 整个目录到带日期的备份位置。
该目录含数据库、冻结产物、运行输入和日志。Markdown/JSON 导出用于阅读交接，不等于完整备份。

0.3.0 使用 schema 4。升级前自行备份；公开版不会自动生成升级前备份，旧版程序也不能
读取新结构。恢复测试应在副本上使用 `HCT_DATABASE`，不要覆盖正在使用的数据。
若启动失败，检查 `service.log`、Python 和 `sources.json` 中的路径。

关闭应用只停止界面服务，已经启动的模型任务可能继续执行；需要停止时先请求取消。
验证阶段的取消会等待当前有时间限制的测试结束。重新打开应用会读取运行记录，不会自动重发任务。
