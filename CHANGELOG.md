# Releases

## 0.4.0 · 2026-09-21

Workweft · 织程 is the new product name.

- New woven-W logo across the app, desktop icon and README.
- Renamed application, repository and download package; clearer bilingual introduction.
- Existing data directory, bundle identifier and export schemas remain compatible.
- Project rules and execution scope are unchanged from 0.3.0.

Workweft 是一款运行在本地的 AI 项目管理工具。新版统一产品名称与 W 形图标，
保留原数据目录和导入格式，已有项目无需搬迁。安装包仍为 Apple Silicon 构建，
使用本地签名，尚未经过 Apple 公证。

See [the user guide](docs/guide.md) for installation and backup instructions.

## 0.3.0 · 2026-09-21

First public early-access release for Apple Silicon macOS.

- Persistent projects, tasks, dependencies, board and Next Up recommendations.
- Local Codex document tasks and bounded workbench Python execution.
- Structured criteria, frozen results, versioned adoption/rejection and acceptance.
- Metadata search, Markdown/JSON exports and explicit MindDesk metadata exchange.
- New Harness application logo and bilingual same-page README navigation.
- Archived execution history retained through a read-only adapter; no private cloud
  transport, credentials, development receipts or user data included.

Package: optimized Rust build, ad-hoc signed, not notarized. Requires system
Python; agent execution requires authenticated Codex CLI. UI is Simplified Chinese.

### 中文

首个公开早期体验版：本地项目看板与依赖、Codex 执行、版本化产物和验收、元数据
查找及导出。新增项目 Logo 与同页中英文 README。公开版保留历史读取接口，不携带
私有连接信息、运行记录或用户数据。安装包为 Apple Silicon 优化构建，尚未 Apple 公证。
