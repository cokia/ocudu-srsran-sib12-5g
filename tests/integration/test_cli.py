import json
import subprocess
import sys
import pytest
from controller.config_loader import load_config
from pathlib import Path


@pytest.mark.parametrize("mode", ["non-sdr", "sdr-bladerf-x40"])
def test_cli_report(codec, tmp_path, mode):
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "controller",
            "validate",
            "--mode",
            mode,
            "--codec",
            codec.executable,
            "--output",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert run.returncode == 0, run.stderr + run.stdout
    report = json.loads(run.stdout)
    assert report["result"] == "PASS"
    assert report["mode"] == mode
    assert report["details"]["rf_transmission"] is False
    assert len(report["ocudu_commit"]) == 40
    audit = (tmp_path / "audit.jsonl").read_text()
    assert "프로토콜 검증 메시지" not in audit
    assert (tmp_path / "offline-sib8.json").exists()
    decoded = subprocess.run(
        [
            sys.executable,
            "-m",
            "controller",
            "decode",
            "--mode",
            mode,
            "--codec",
            codec.executable,
            "--input",
            str(tmp_path / "offline-sib8.json"),
            "--output",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert decoded.returncode == 0, decoded.stderr + decoded.stdout
    original = load_config(Path("configs/pws.example.yaml"))["pws"]["message"]["text"]
    assert json.loads(decoded.stdout)["details"]["text"] == original
    saved = (tmp_path / f"decode-{mode}.json").read_text(encoding="utf-8")
    assert original in saved
    assert json.loads(saved)["details"]["text"] == original


def test_missing_config_is_failure(tmp_path):
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "controller",
            "validate",
            "--config",
            str(tmp_path / "missing.yaml"),
            "--output",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert run.returncode == 2
    assert json.loads(run.stdout)["result"] == "FAIL"
    assert json.loads((tmp_path / "validate-non-sdr.json").read_text())["error"]["code"] == "E_CONFIG_IO"
