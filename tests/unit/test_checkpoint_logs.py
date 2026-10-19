import json
import subprocess
import sys


def test_failure_is_visible_in_step_log_and_report(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "controller.checkpoints",
            "--name",
            "compile-error",
            "--output",
            str(tmp_path),
            "--",
            sys.executable,
            "-c",
            "print('error: missing SIMD type'); raise SystemExit(1)",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "error: missing SIMD type" in result.stderr
    assert json.loads((tmp_path / "compile-error.json").read_text())["result"] == "FAIL"
    assert (tmp_path / "compile-error.log").read_text() == "error: missing SIMD type\n"


def test_success_does_not_dump_the_build_log(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "controller.checkpoints",
            "--name",
            "compile-ok",
            "--output",
            str(tmp_path),
            "--",
            sys.executable,
            "-c",
            "print('compiled')",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0 and result.stderr == ""
    assert "compiled" not in result.stdout
