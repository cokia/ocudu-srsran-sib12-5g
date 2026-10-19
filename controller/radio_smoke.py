"""실제 OCUDU dynamic loader와 bladeRF plugin의 mock stream을 제한 시간 동안 검사한다."""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

import yaml

from .config_loader import ROOT, load_config, load_yaml
from .errors import LabError
from .pws_integration import prepare
from .reporting import audit, report, write_report


def stream_evidence(text):
    summaries = [line for line in text.splitlines() if "LAB_RADIO_STOP" in line]
    pattern = (
        r"LAB_RADIO_STOP hardware=0 tx_samples=(\d+) rx_samples=(\d+) "
        r"errors=(\d+) late=(\d+) overflow=(\d+) underflow=(\d+)"
    )
    count = re.fullmatch(pattern, summaries[0]) if len(summaries) == 1 else None
    if count is None or re.search(r"bladeRF x40 plugin: E_[A-Z_]+", text):
        raise LabError("E_STREAM_EVIDENCE", "정상 stream 종료 증거가 없거나 plugin 오류가 있습니다.", 1)
    evidence = dict(
        zip(("tx_samples", "rx_samples", "errors", "late", "overflow", "underflow"), map(int, count.groups()))
    )
    if min(evidence["tx_samples"], evidence["rx_samples"]) == 0 or any(list(evidence.values())[2:]):
        raise LabError("E_STREAM_EVIDENCE", "sample이 없거나 stream 오류/event가 있습니다.", 1)
    return evidence


def main():
    parser = argparse.ArgumentParser(description="USB 없는 OCUDU bladeRF plugin smoke test")
    parser.add_argument("--gnb", default=os.environ.get("GNB_ZMQ_BINARY", "build/bin/gnb-zmq"))
    parser.add_argument("--library-directory", type=Path, default=Path("build/radio-plugin"))
    parser.add_argument("--output", type=Path, default=Path("output/radio-plugin"))
    parser.add_argument("--duration", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.duration <= 10:
        parser.error("duration은 1..10초입니다.")
    args.output.mkdir(parents=True, exist_ok=True)
    log_path = args.output / "gnb.log"
    process = None
    interrupted = False
    code = 0

    def stop_requested(signum, frame):
        nonlocal interrupted
        interrupted = True

    old = {sig: signal.signal(sig, stop_requested) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        if not Path("/sys/class/net").exists() or {p.name for p in Path("/sys/class/net").iterdir()} != {"lo"}:
            raise LabError("E_NETWORK_ISOLATION", "Docker --network none이 필요합니다.", 3)
        library = args.library_directory.resolve() / "libocudu_radio_bladerf_x40.so"
        if not library.is_file():
            raise LabError("E_PLUGIN_MISSING", str(library), 3)
        path, _ = prepare(load_config(ROOT / "configs/pws.example.yaml"), "korean-safety", "zmq", args.output)
        config = load_yaml(path)
        config["ru_sdr"].update(device_driver="bladerf_x40", device_args="mode=mock,rf=off,max_seconds=45")
        path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=True))
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = (
            str(library.parent) + ":" + str(ROOT / "build/deps/lib") + ":" + env.get("LD_LIBRARY_PATH", "")
        )
        with log_path.open("w") as log:
            process = subprocess.Popen(
                [args.gnb, "-c", str(path)],
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
            deadline = time.monotonic() + 20
            ready = False
            while time.monotonic() < deadline and not interrupted:
                if process.poll() is not None:
                    raise LabError("E_GNB_EXIT", str(process.returncode), 1)
                if log_path.stat().st_size > 32 * 1024 * 1024:
                    raise LabError("E_LOG_LIMIT", "최대 32 MiB", 4)
                if not ready and "gNB started" in log_path.read_text(errors="replace"):
                    ready = True
                    deadline = time.monotonic() + args.duration
                time.sleep(0.1)
            if not ready or interrupted:
                raise LabError("E_GNB_START", "시작 실패 또는 중단", 4)
            os.killpg(process.pid, signal.SIGINT)
            try:
                rc = process.wait(timeout=10)
            except subprocess.TimeoutExpired as exc:
                raise LabError("E_SHUTDOWN_TIMEOUT", "10초 이내 종료되지 않았습니다.", 4) from exc
            if rc != 0:
                raise LabError("E_GNB_EXIT", str(rc), 1)
        text = log_path.read_text(errors="replace")
        evidence = stream_evidence(text)
        result = report(
            "non-sdr",
            "ocudu-bladerf-plugin-mock",
            "PASS",
            {
                **evidence,
                "exit_code": rc,
                "backend": "bladerf_x40",
                "transport": "mock",
                "rf_transmission": False,
                "pws_scheduled_configuration": True,
                "physical_hardware": "NOT VERIFIED",
                "receiver_decode": "NOT VERIFIED",
            },
            artifact=args.output,
        )
    except (LabError, OSError) as exc:
        code = exc.exit_code if isinstance(exc, LabError) else 3
        result = report(
            "non-sdr",
            "ocudu-bladerf-plugin-mock",
            "BLOCKED" if code == 3 else "FAIL",
            error={"code": getattr(exc, "code", "E_IO"), "detail": str(exc)},
            artifact=args.output,
        )
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        for sig, handler in old.items():
            signal.signal(sig, handler)
    write_report(args.output / "radio-smoke.json", result)
    audit(args.output, "radio-plugin-smoke", result["result"], error=result["error"])
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
