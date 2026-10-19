#!/usr/bin/env python3
"""빌드 산출물을 검증 가능한 Docker named context로 준비한다."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
mode = sys.argv[1]
if mode not in {"non-sdr", "sdr-bladerf-x40", "controller", "zmq", "radio-plugin"}:
    raise SystemExit(2)
stage = ROOT / "build" / "runtime" / mode
if stage.exists():
    shutil.rmtree(stage)
(stage / "bin").mkdir(parents=True, exist_ok=True)
(stage / "lib").mkdir(exist_ok=True)
files = {
    "non-sdr": ["pws-codec", "gnb"],
    "sdr-bladerf-x40": ["pws-codec", "bladerf-x40-diag"],
    "controller": ["pws-codec"],
    "zmq": ["gnb-zmq", "srsue"],
    "radio-plugin": ["gnb-zmq"],
}[mode]
manifest = {"mode": mode, "pins": json.loads((ROOT / "dependencies.lock.json").read_text()), "sha256": {}}
for name in files:
    path = ROOT / "build" / "bin" / name
    if not path.is_file():
        raise SystemExit(f"E_BUILD_MISSING: {path}")
    shutil.copy2(path, stage / "bin" / name)
    manifest["sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
if mode in {"sdr-bladerf-x40", "radio-plugin"}:
    for path in (ROOT / "build/deps/lib").glob("libbladeRF.so*"):
        shutil.copy2(path, stage / "lib" / path.name)
    manifest["bladerf_patch_sha256"] = hashlib.sha256(
        (ROOT / "patches/bladerf-x40-only.patch").read_bytes()
    ).hexdigest()
if mode == "radio-plugin":
    cache = (ROOT / "build/radio-plugin/CMakeCache.txt").read_text()
    if "LAB_ENABLE_BLADERF_RF:BOOL=OFF" not in cache:
        raise SystemExit("E_RF_BUILD: Docker mock 이미지에는 RF OFF build만 허용합니다.")
    plugin = ROOT / "build/radio-plugin/libocudu_radio_bladerf_x40.so"
    shutil.copy2(plugin, stage / "lib" / plugin.name)
    manifest["sha256"][plugin.name] = hashlib.sha256(plugin.read_bytes()).hexdigest()
    manifest["rf_enabled"] = False
manifest["packages"] = subprocess.check_output(["dpkg-query", "-W"], text=True).splitlines()
(stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
