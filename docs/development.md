# Development

Maintainer: [Qiushan (QiushanHuang)](https://github.com/QiushanHuang).

## Layout

| Directory | Responsibility |
| --- | --- |
| `crates/control-core` | Typed task commands, versioned review rules, SQLite transactions |
| `apps/workbench` | Loopback HTTP service, local runner, artifact storage and search |
| `apps/workbench/static` | Shared browser/native interface |
| `apps/desktop` | Tauri window and macOS package assembly |

Keep acceptance rules in the Rust core; keep execution backends and external
references outside it. New commands need state-transition tests. Each meaningful
runner change needs a test of the affected lifecycle or result boundary.

## Checks

Use Rust with Cargo, Python 3.9+ and Node.js for syntax checks. Install Ruff for
Python linting. No JavaScript package installation is needed.

```sh
cargo build --locked -p hct-core
cargo test --locked -p hct-core
python3 -m unittest discover -s apps/workbench -p 'test_*.py'
ruff check apps/workbench
node --check apps/workbench/static/app.js
node --check apps/workbench/static/review-panel.js
```

Python tests use temporary data and fake executors; they do not send model requests.
The retired school's live-dispatch tests and private fixtures are not distributed.
The replacement history adapter is tested for read-only retention and no replay.

## Build a macOS package

On Apple Silicon with Apple's command-line developer tools:

```sh
cargo build --release --locked -p hct-core
cargo build --release --locked --manifest-path apps/desktop/Cargo.toml
python3 apps/desktop/package.py --name 'Harness Control Terminal.app'
codesign --verify --deep --strict 'dist/Harness Control Terminal.app'
ditto -c -k --sequesterRsrc --keepParent 'dist/Harness Control Terminal.app' 'dist/Harness-Control-Terminal-v0.3.0-macos-arm64.zip'
```

The packager refuses to overwrite an existing bundle. Choose a new output name
for another build. It packages runtime code, not application data or cloud
credentials. The icon source is `docs/brand/harness-logo.png`; PNG and ICNS variants
are included under `apps/desktop/icons/`. The original development-only icon
generator is not used by the public build.

The package is ad-hoc signed. Official Developer ID signing and notarization are
separate release work. Do not remove quarantine or disable system security in an
installer script.

## Contribution workflow

Open an issue describing the workflow that needs improvement, or a focused pull
request with reproduction steps and relevant test results. Keep personal paths,
credentials, run databases and user outputs out of changes. Write UI labels in
Simplified Chinese and explain new behaviour in both README language sections
when it changes the first-use workflow.

## 中文开发说明

核心规则在 Rust 中，执行器、文件引用和界面保持独立。运行上方测试命令后提交范围
清晰的 PR，附操作步骤和相关验证结果。测试不应调用真实模型或连接学校服务器。
发布包只包含程序代码与图标，不包含个人数据、认证信息或私有运行记录。
macOS 打包命令见上方；当前为本地签名，Developer ID 和 Apple 公证需单独办理。
