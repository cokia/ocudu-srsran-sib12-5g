"""loopback ZMQ에서 실제 srsUE의 NR MIB/SIB1 수신을 검사한다."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from .config_loader import ROOT
from .errors import LabError
from .reporting import audit, report, write_report

# 고정 profile 밖의 RF backend/외부 socket/PWS 설정을 실행하지 않는다.
PROFILES = {
    "gnb.zmq.yaml": "e9e95dd9649ec7438ac5e4b50977f63edc3bf8a06ef3434c673b9cf667206936",
    "srsue.zmq.conf": "5b81ceebe5f93920804d5f7fde85e07f0defde319b13f682e8c0e9454cf7dda7",
}


def validate_profiles():
    for name, expected in PROFILES.items():
        if hashlib.sha256((ROOT / "configs" / name).read_bytes()).hexdigest() != expected:
            raise LabError("E_ZMQ_PROFILE", f"고정 profile과 다릅니다: {name}")
    if len(PROFILES) != 2:
        raise LabError("E_ZMQ_PROFILE", "검증 profile pin이 필요합니다.")


def evidence(gnb, ue):
    # 고정 srsUE revision의 PHY callback은 ssb_arfcn을 채우지 않아 0을 기록한다.
    # PCI뿐 아니라 실제 unpack된 MIB의 SCS/CORESET/SS0와 적용 완료도 확인한다.
    mib = re.search(r"Cell search found ARFCN=(?:0|368410) PCI=1\s[^\n]* scs=15 [^\n]*coreset0=12 ss0=0(?:\s|$)", ue)
    return {
        "gnb_started": "gNB started" in gnb,
        "mib_decoded": bool(mib) and "PHY configuration with MIB parameters completed." in ue,
        "sib1_received": "SIB1 received, CellID=" in ue,
        "sib1_acquired": "SIB1 acquired successfully" in ue,
        "rrc_connected": "RRC Connected" in ue,
        "rrc_released": "Received RRC Release" in ue,
        "gnb_ue_removed": '"UE Removal Routine" finished successfully' in gnb,
    }


def ready_to_stop(found):
    # no-core stub는 NG Reset 응답을 제공하지 않는다. 정상 자동 UE release까지
    # 관찰한 뒤 종료하여 AMF 응답 대기 중의 강제 종료를 피한다.
    return all(found.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gnb", default=os.environ.get("GNB_ZMQ_BINARY", "build/bin/gnb-zmq"))
    parser.add_argument("--ue", default=os.environ.get("SRSUE_BINARY", "build/bin/srsue"))
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output", type=Path, default=Path("output/zmq"))
    args = parser.parse_args()
    if not 5 <= args.timeout <= 120:
        parser.error("timeout은 5..120초입니다.")
    args.output.mkdir(parents=True, exist_ok=True)
    processes = []
    logs = []
    paths = [args.output / "gnb.log", args.output / "srsue.log"]
    status, error = "FAIL", None
    codes = []
    stopped = False

    def stop_requested(signum, frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop_requested)
    signal.signal(signal.SIGINT, stop_requested)
    try:
        validate_profiles()
        if not Path("/sys/class/net").exists() or {p.name for p in Path("/sys/class/net").iterdir()} != {"lo"}:
            raise LabError("E_NETWORK_ISOLATION", "Docker --network none이 필요합니다.", 3)
        commands = [
            [args.gnb, "-c", str(ROOT / "configs/gnb.zmq.yaml")],
            [args.ue, str(ROOT / "configs/srsue.zmq.conf")],
        ]
        for path, command in zip(paths, commands):
            stream = path.open("w")
            logs.append(stream)
            # ZMQ gNB는 UE의 request를 기다릴 수 있어 두 process를 곧바로 시작한다.
            processes.append(
                subprocess.Popen(
                    command, stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True
                )
            )
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline and not stopped:
            if any(p.poll() is not None for p in processes):
                raise LabError("E_ZMQ_EARLY_EXIT", str([p.poll() for p in processes]), 1)
            found = evidence(*(p.read_text(errors="replace") for p in paths))
            if ready_to_stop(found):
                status = "PASS"
                break
            if any(p.stat().st_size > 32 * 1024 * 1024 for p in paths):
                raise LabError("E_LOG_LIMIT", "각 log의 최대 크기는 32 MiB입니다.", 4)
            time.sleep(0.2)
        if status != "PASS":
            raise LabError("E_RX_TIMEOUT", "제한 시간 안에 MIB/SIB1 수신 및 RRC release가 완료되지 않았습니다.", 4)
    except LabError as exc:
        status = "BLOCKED" if exc.exit_code == 3 else "FAIL"
        error = {"code": exc.code, "detail": exc.detail}
    except OSError as exc:
        status, error = "BLOCKED", {"code": "E_EXEC", "detail": str(exc)}
    finally:
        # srsUE PHY가 마지막 RX에서 빠져나올 수 있도록 gNB를 유지하고 UE부터 종료한다.
        codes = [None] * len(processes)
        for index in reversed(range(len(processes))):
            process = processes[index]
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
            try:
                codes[index] = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                codes[index] = process.wait(timeout=2)
                status, error = "FAIL", {"code": "E_SHUTDOWN", "detail": "SIGINT 후 10초 초과"}
        for stream in logs:
            stream.close()
    # preflight 실패 시 이전 실행의 log를 이번 수신 증거로 재사용하지 않는다.
    found = evidence(*(p.read_text(errors="replace") if i < len(logs) else "" for i, p in enumerate(paths)))
    pin = json.loads((ROOT / "dependencies.lock.json").read_text())["srsran4g"]["commit"]
    details = {
        **found,
        "srsran4g_commit": pin,
        "exit_codes": codes,
        "backend": "zmq",
        "rf_transmission": False,
        "pws_routed": False,
        "timeout_seconds": args.timeout,
        "nas_registration": "NOT VERIFIED",
        "ip_connectivity": "NOT VERIFIED",
        "pws_reception": "UNSUPPORTED",
    }
    if status == "PASS" and any(code != 0 for code in codes):
        status, error = "FAIL", {"code": "E_SHUTDOWN", "detail": str(codes)}
    result = report("non-sdr", "zmq-srsue-reception", status, details, error, args.output)
    write_report(args.output / "zmq-rx.json", result)
    audit(args.output, "zmq-srsue-reception", status, error=error)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if status == "PASS" else (3 if status == "BLOCKED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
