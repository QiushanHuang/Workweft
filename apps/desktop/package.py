"""Assemble a local macOS app from built binaries; never packages user data."""

from pathlib import Path
import plistlib
import shutil
import subprocess
import argparse

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--name", default="Workweft.app")
parser.add_argument("--profile", choices=("debug", "release"), default="release")
args = parser.parse_args()
if Path(args.name).name != args.name or not args.name.endswith(".app"):
    raise SystemExit("Expected an app bundle filename")
app = root / "dist" / args.name
if app.exists():
    raise SystemExit(
        "App already exists; preserve it and choose a new release directory before rebuilding."
    )
macos = app / "Contents/MacOS"
resources = app / "Contents/Resources"
workspace = resources / "workspace"
macos.mkdir(parents=True)
workspace.mkdir(parents=True)
shutil.copy2(
    root / f"apps/desktop/target-workweft/{args.profile}/workweft-desktop",
    macos / "workweft-desktop",
)
ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
shutil.copytree(root / "apps/workbench", workspace / "apps/workbench", ignore=ignore)
(workspace / "target/debug").mkdir(parents=True)
shutil.copy2(root / f"target/{args.profile}/hct-core", workspace / "target/debug/hct-core")
shutil.copy2(root / "apps/desktop/icons/icon.png", resources / "icon.png")
shutil.copy2(root / "apps/desktop/icons/icon.icns", resources / "icon.icns")
shutil.copy2(root / "LICENSE", resources / "LICENSE")
shutil.copy2(root / "docs/THIRD-PARTY-NOTICES.txt", resources / "THIRD-PARTY-NOTICES.txt")
info = {
    "CFBundleExecutable": "workweft-desktop",
    "CFBundleIdentifier": "local.harness.control",
    "CFBundleName": "Workweft",
    "CFBundleDisplayName": "Workweft",
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": "0.4.0",
    "CFBundleVersion": "4",
    "CFBundleIconFile": "icon.icns",
    "LSMinimumSystemVersion": "12.0",
    "NSHighResolutionCapable": True,
}
with (app / "Contents/Info.plist").open("wb") as file:
    plistlib.dump(info, file)
subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
print(app)
