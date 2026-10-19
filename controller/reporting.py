import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from . import __version__

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {"PASS", "FAIL", "SKIP", "BLOCKED", "NOT VERIFIED"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def report(mode, test_name, status, details=None, error=None, artifact=None, hardware=None):
    if status not in STATUSES:
        raise ValueError(status)
    pin = json.loads((ROOT / "dependencies.lock.json").read_text())["ocudu"]["commit"]
    return {
        "report_schema_version": 1,
        "mode": mode,
        "application_version": __version__,
        "ocudu_commit": pin,
        "host": {
            "os": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
        },
        "sdr_model": hardware.get("model") if hardware else None,
        "firmware_version": hardware.get("firmware") if hardware else None,
        "fpga_version": hardware.get("fpga") if hardware else None,
        "test_name": test_name,
        "result": status,
        "error": error,
        "timestamp": now(),
        "artifact_location": str(artifact) if artifact else None,
        "details": details or {},
    }


def write_report(path: Path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def audit(directory: Path, event, status, **details):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "audit.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(canonical({"timestamp": now(), "event": event, "status": status, **details}) + "\n")
