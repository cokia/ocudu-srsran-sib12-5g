import json
import subprocess
import pytest


def run_diag(binary, *args):
    run = subprocess.run([binary, *args], capture_output=True, text=True, timeout=10)
    return run.returncode, json.loads(run.stdout)


@pytest.mark.parametrize("command", ["info", "capabilities", "verify", "loopback", "rx"])
def test_mock_success(diagnostic, command):
    code, result = run_diag(diagnostic, command, "--mock")
    assert code == 0
    assert result["status"] == "PASS"
    assert result["mock"] is True
    assert result["hardware_verified"] is False
    if command == "loopback":
        assert result["diagnostics"]["samples_processed"] == 65536
        assert result["diagnostics"]["timestamp_consistency"] == "SKIP"


@pytest.mark.parametrize(
    "fault,command,status,expected",
    [
        ("no-device", "info", "BLOCKED", 3),
        ("permission", "info", "BLOCKED", 3),
        ("wrong-model", "info", "FAIL", 1),
        ("x115", "info", "FAIL", 1),
        ("firmware", "verify", "FAIL", 1),
        ("fpga", "verify", "FAIL", 1),
        ("usb2", "verify", "FAIL", 1),
        ("unsafe", "loopback", "SKIP", 77),
        ("disconnect", "loopback", "FAIL", 1),
        ("timeout", "loopback", "FAIL", 1),
        ("corrupt", "loopback", "FAIL", 1),
        ("overrun", "loopback", "FAIL", 1),
        ("timestamp", "rx", "FAIL", 1),
        ("cleanup", "loopback", "FAIL", 1),
    ],
)
def test_mock_errors(diagnostic, fault, command, status, expected):
    code, result = run_diag(diagnostic, command, "--mock", "--fault", fault)
    assert code == expected
    assert result["status"] == status
    assert result["error"]["code"].startswith("E_")
    assert result["hardware_verified"] is False


def test_hardware_requires_explicit_opt_in(diagnostic):
    code, result = run_diag(diagnostic, "loopback")
    assert code == 3
    assert result["error"]["code"] == "E_HARDWARE_OPT_IN"


def test_no_payload_interface(diagnostic):
    code, result = run_diag(diagnostic, "loopback", "--mock", "--payload", "warning")
    assert code != 0
    assert result["error"]["code"] == "E_ARGUMENT"
