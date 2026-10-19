"""격리된 network namespace에서 Dummy RU gNB의 시작/종료를 검증한다."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from .config_loader import load_yaml, ROOT
from .errors import LabError
from .reporting import audit, digest, report, write_report


def validate_gnb(path):
    config = load_yaml(path)
    try:
        config_digest = digest(config)
    except (ValueError, TypeError) as exc:
        raise LabError("E_GNB_PROFILE", "JSON 호환 설정이 아닙니다.") from exc
    # 검증한 단일 smoke profile만 허용한다. 임의 upstream 옵션을 전달하지 않는다.
    if (
        not isinstance(config, dict)
        or config_digest != "96aec5af7eb90447359a8b19db9092441b573160843451dc6d46fbc985bcc6dd"
    ):
        raise LabError("E_GNB_PROFILE", "검증한 gnb.non-sdr.yaml과 다른 설정입니다.")
    if set(config) != {"cu_cp", "ru_dummy", "cell_cfg", "log", "pcap", "buffer_pool"}:
        raise LabError("E_GNB_PROFILE", "허용되지 않은 gNB 최상위 옵션입니다.")
    if config["cu_cp"]["amf"]["no_core"] is not True or "ru_dummy" not in config:
        raise LabError("E_GNB_PROFILE", "no_core 및 Dummy RU가 필요합니다.")
    return config


def main():
    parser = argparse.ArgumentParser(description="최대 60초 Dummy RU smoke test")
    parser.add_argument("--binary", default=os.environ.get("GNB_BINARY", "build/bin/gnb"))
    parser.add_argument("--config", type=Path, default=ROOT / "configs/gnb.non-sdr.yaml")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("output/non-sdr"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    process = None
    health = args.output / "gnb.health.json"
    log_path = args.output / "gnb.log"
    interrupted = False

    def stop_requested(signum, frame):
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGTERM, stop_requested)
    signal.signal(signal.SIGINT, stop_requested)
    code = 1
    try:
        if not 1 <= args.duration <= 30:
            raise LabError("E_DURATION", "유지 시간은 1..30초입니다.")
        validate_gnb(args.config)
        if not Path("/sys/class/net").exists() or {p.name for p in Path("/sys/class/net").iterdir()} != {"lo"}:
            raise LabError("E_NETWORK_ISOLATION", "network none 또는 전용 network namespace가 필요합니다.", 3)
        audit(args.output, "gnb-preflight", "PASS", backend="dummy", no_core=True)
        with log_path.open("w") as log:
            process = subprocess.Popen(
                [args.binary, "-c", str(args.config)],
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            deadline = time.monotonic() + 20
            ready = False
            while time.monotonic() < deadline and process.poll() is None and not interrupted:
                text = log_path.read_text(errors="replace")
                if "gNB started" in text:
                    ready = True
                    break
                time.sleep(0.1)
            if not ready:
                raise LabError("E_GNB_START", f"시작 marker 없음. rc={process.poll()}. {log_path}", 1)
            write_report(health, {"status": "STARTED", "pid": process.pid})
            audit(args.output, "gnb-start", "PASS")
            deadline = time.monotonic() + args.duration
            while time.monotonic() < deadline and not interrupted:
                if process.poll() is not None:
                    raise LabError("E_GNB_EARLY_EXIT", f"rc={process.returncode}", 1)
                time.sleep(0.1)
            os.killpg(process.pid, signal.SIGINT)
            try:
                rc = process.wait(timeout=10)
            except subprocess.TimeoutExpired as exc:
                raise LabError("E_GNB_SHUTDOWN_TIMEOUT", "10초 이내 종료되지 않았습니다.", 4) from exc
            if rc != 0:
                raise LabError("E_GNB_EXIT", f"rc={rc}", 1)
            if "Stopping" not in log_path.read_text(errors="replace"):
                raise LabError("E_GNB_STOP_MARKER", "graceful shutdown marker가 없습니다.", 1)
        result = report(
            "non-sdr",
            "gnb-smoke",
            "PASS",
            {
                "startup": True,
                "graceful_shutdown": True,
                "duration_seconds": args.duration,
                "interrupted": interrupted,
                "backend": "dummy",
                "rf_transmission": False,
                "ue_attach": "NOT VERIFIED",
            },
            artifact=log_path,
        )
        code = 0
    except LabError as exc:
        code = exc.exit_code
        result = report(
            "non-sdr",
            "gnb-smoke",
            "BLOCKED" if code == 3 else "FAIL",
            error={"code": exc.code, "detail": exc.detail},
            artifact=log_path,
        )
    except OSError as exc:
        code = 3
        result = report(
            "non-sdr", "gnb-smoke", "BLOCKED", error={"code": "E_EXEC", "detail": str(exc)}, artifact=log_path
        )
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
        write_report(health, {"status": "STOPPED"})
    write_report(args.output / "gnb-smoke.json", result)
    audit(args.output, "gnb-smoke", result["result"], error=result["error"])
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
