"""Print dependency notices from Cargo's resolved registry packages."""
import json
from pathlib import Path
import subprocess
import hashlib

root = Path(__file__).resolve().parents[1]
packages = {}
for manifest in (root / "Cargo.toml", root / "apps/desktop/Cargo.toml"):
    metadata = json.loads(subprocess.check_output([
        "cargo", "metadata", "--offline", "--locked", "--format-version", "1",
        "--filter-platform", "aarch64-apple-darwin", "--manifest-path", str(manifest)
    ], text=True))
    for package in metadata["packages"]:
        if package["source"]:
            packages[package["id"]] = package

print("Third-party Cargo dependency notices\n")
print("Includes resolved build dependencies. Component licenses remain their own.\n")
notices = {}
for package in sorted(packages.values(), key=lambda item: (item["name"], item["version"])):
    print(f"\n{'=' * 72}\n{package['name']} {package['version']}\nLicense: {package['license']}\n")
    directory = Path(package["manifest_path"]).parent
    files = set()
    if package.get("license_file"):
        files.add(directory / package["license_file"])
    for pattern in ("LICENSE*", "LICENCE*", "COPYING*", "NOTICE*"):
        files.update(directory.glob(pattern))
    for file in sorted(files):
        if file.is_file():
            body = '\n'.join(line.rstrip() for line in file.read_text(errors='replace').splitlines()).strip()
            digest = hashlib.sha256(body.encode()).hexdigest()
            notices[digest] = body
            print(f"{file.name}: notice {digest}")
for digest, body in notices.items():
    print(f"\n--- notice {digest} ---\n{body}")
