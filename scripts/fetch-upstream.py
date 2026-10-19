#!/usr/bin/env python3
"""고정 commit을 가져오며 기존 checkout의 변경을 덮어쓰지 않는다."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", choices=["ocudu", "bladerf", "srsran4g"])
    args = parser.parse_args()
    pin = json.loads((ROOT / "dependencies.lock.json").read_text())[args.project]
    dest = ROOT / "upstream" / ("bladeRF" if args.project == "bladerf" else args.project)
    if not dest.exists():
        dest.parent.mkdir(exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", pin["tag"], pin["url"], str(dest)], check=True, timeout=300
        )
    revision = subprocess.check_output(["git", "-C", str(dest), "rev-parse", "HEAD"], text=True).strip()
    if revision != pin["commit"]:
        raise SystemExit(f"E_REVISION: {dest}: {revision} != {pin['commit']}")
    dirty = subprocess.check_output(["git", "-C", str(dest), "diff", "HEAD", "--name-only"], text=True)
    patches = pin.get("patches", [])
    allowed = {item["source"]: item for item in patches}
    for name in dirty.splitlines():
        if (
            name not in allowed
            or hashlib.sha256((dest / name).read_bytes()).hexdigest() != allowed[name]["patched_sha256"]
        ):
            raise SystemExit(f"E_UPSTREAM_DIRTY: {dirty}")
    for item in patches:
        path = dest / item["source"]
        patch_path = ROOT / item["file"]
        if hashlib.sha256(patch_path.read_bytes()).hexdigest() != item["sha256"]:
            raise SystemExit(f"E_PATCH_FILE: {patch_path}")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha == item["original_sha256"]:
            patch = str(patch_path)
            subprocess.run(["git", "-C", str(dest), "apply", "--check", patch], check=True, timeout=30)
            subprocess.run(["git", "-C", str(dest), "apply", patch], check=True, timeout=30)
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["patched_sha256"]:
            raise SystemExit(f"E_PATCH_HASH: {path}")
    if args.project == "ocudu":
        link = dest / "plugins" / "pws_lab"
        link.parent.mkdir(exist_ok=True)
        target = ROOT / "controller" / "offline_codec"
        if not link.exists():
            link.symlink_to(os.path.relpath(target, link.parent), target_is_directory=True)
        elif link.resolve() != target:
            raise SystemExit("E_PLUGIN_PATH")
    print(f"{args.project}: {revision}")


if __name__ == "__main__":
    main()
