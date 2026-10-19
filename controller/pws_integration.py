"""공유 PWS 입력을 OCUDU CMAS test SI에 연결하고 ZMQ 수신 원문을 비교한다."""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

import yaml

from . import cb_data
from .config_loader import ROOT, load_config, load_yaml
from .errors import LabError
from .message_model import LaboratoryMessage
from .reporting import audit, report, write_report
from .zmq_rx import validate_profiles

PROFILES = {"monthly-test": 4380, "korean-safety": 4372}
SEGMENT = re.compile(
    r"LAB_SIB8 id=(\d+) serial=(\d+) segment=(\d+) last=([01]) dcs=(none|[0-9a-fA-F]{2}) payload=([0-9a-fA-F]+)"
)


def prepare(config, profile, backend, output, serial=""):
    validate_profiles()
    message = LaboratoryMessage.from_config(config)
    if not message.text.startswith(("[시험", "[TEST]")):
        raise LabError("E_TEST_LABEL", "연동 시험 문구는 [시험 또는 [TEST]로 시작해야 합니다.")
    cb_data.encode(message.text)
    gnb = load_yaml(ROOT / "configs/gnb.zmq.yaml")
    gnb["cell_cfg"]["sib"] = {
        "si_window_length": 10,
        "cmas": {
            "si_period": 8,
            "test": {
                "message_id": PROFILES[profile],
                "serial_num": 0,
                "data_coding_scheme": 0x48,
                "warning_message": message.text,
            },
        },
    }
    if backend == "bladerf-x40":
        if serial and not re.fullmatch(r"[0-9a-fA-F]{32}", serial):
            raise LabError("E_SERIAL", "serial은 32 hex 문자입니다.")
        gnb["ru_sdr"].update(
            {
                "device_driver": "bladerf_x40",
                "device_args": f"mode=hardware,rf=off,serial={serial.lower()},max_seconds=20",
                "tx_gain": 17,
            }
        )
    elif backend != "zmq":
        raise LabError("E_BACKEND", "zmq 또는 bladerf-x40가 필요합니다.")
    output.mkdir(parents=True, exist_ok=True)
    path = output / "gnb.pws.yaml"
    path.write_text(yaml.safe_dump(gnb, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return path, message


def recovered(log, identifier):
    segments, last = {}, None
    for match in SEGMENT.finditer(log):
        mid, serial, index, final = map(int, match.group(1, 2, 3, 4))
        dcs, payload = match.group(5, 6)
        if mid != identifier or serial != 0 or index > 63 or len(payload) % 2:
            raise LabError("E_SIB8_METADATA", "수신 SIB8 식별자/segment가 일치하지 않습니다.")
        if (index == 0 and dcs.lower() != "48") or (index != 0 and dcs != "none"):
            raise LabError("E_SIB8_DCS", "수신 SIB8 DCS가 UCS-2 profile과 다릅니다.")
        item = (bytes.fromhex(payload), final)
        if index in segments and segments[index] != item:
            raise LabError("E_SIB8_CONFLICT", "동일 segment의 내용이 변경됐습니다.")
        segments[index] = item
        if final:
            if last is not None and last != index:
                raise LabError("E_SIB8_LAST", "last segment가 일치하지 않습니다.")
            last = index
    if last is None or any(i not in segments for i in range(last + 1)):
        return None
    if len(segments) != last + 1 or any(segments[i][1] for i in range(last)):
        raise LabError("E_SIB8_ORDER", "수신 segment 범위가 잘못되었습니다.")
    payload = b"".join(segments[i][0] for i in range(last + 1))
    cb_size = 1 + payload[0] * 83
    if any(len(segments[i][0]) != (84 if i == 0 else 85) for i in range(last + 1)):
        raise LabError("E_SIB8_SIZE", "고정 OCUDU segment 크기와 다릅니다.")
    if cb_size > len(payload) or len(payload) - cb_size >= 85 or any(payload[cb_size:]):
        raise LabError("E_SIB8_PADDING", "OCUDU segment padding이 잘못되었습니다.")
    return {
        "text": cb_data.decode(payload[:cb_size], padding="ocudu-zero"),
        "payload_hex": payload[:cb_size].hex(),
        "wire_payload_hex": payload.hex(),
        "segments": last + 1,
    }


def receive(args, path, message):
    if not Path("/sys/class/net").exists() or {p.name for p in Path("/sys/class/net").iterdir()} != {"lo"}:
        raise LabError("E_NETWORK_ISOLATION", "Docker --network none이 필요합니다.", 3)
    processes, streams, codes = [], [], []
    paths = [args.output / "gnb.log", args.output / "srsue.log"]
    result = None
    error = None
    interrupted = False

    def stop_requested(signum, frame):
        nonlocal interrupted
        interrupted = True

    old = {sig: signal.signal(sig, stop_requested) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        env = dict(os.environ, PWS_LAB_SI_MONITOR="1")
        for log, command in zip(paths, ([args.gnb, "-c", str(path)], [args.ue, str(ROOT / "configs/srsue.zmq.conf")])):
            stream = log.open("w")
            streams.append(stream)
            processes.append(
                subprocess.Popen(
                    command,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    env=env,
                    start_new_session=True,
                )
            )
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline and not interrupted:
            if any(p.poll() is not None for p in processes):
                raise LabError("E_EARLY_EXIT", str([p.poll() for p in processes]), 1)
            if any(p.stat().st_size > 32 * 1024 * 1024 for p in paths):
                raise LabError("E_LOG_LIMIT", "log별 최대 32 MiB", 4)
            ue = paths[1].read_text(errors="replace")
            result = recovered(ue, PROFILES[args.profile])
            if result is not None:
                if (
                    result["text"] != message.text
                    or result["payload_hex"] != cb_data.encode(message.text, padding="ocudu-zero").hex()
                ):
                    raise LabError("E_ROUND_TRIP", "수신 원문 또는 CB Data가 송신 입력과 다릅니다.", 1)
                if (
                    "SIB1 acquired successfully" not in ue
                    or "PHY configuration with MIB parameters completed." not in ue
                ):
                    raise LabError("E_RX_EVIDENCE", "MIB/SIB1 증거가 없습니다.", 1)
                break
            time.sleep(0.2)
        else:
            raise LabError("E_RX_TIMEOUT", "SIB8 전체 수신 제한 시간 또는 중단", 4)
    except LabError as exc:
        error = exc
    finally:
        codes = [None] * len(processes)
        for i in reversed(range(len(processes))):
            p = processes[i]
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
            try:
                codes[i] = p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                codes[i] = p.wait(timeout=2)
        for stream in streams:
            stream.close()
        for sig, handler in old.items():
            signal.signal(sig, handler)
    if error:
        raise error
    if codes != [0, 0]:
        raise LabError("E_SHUTDOWN", str(codes), 1)
    return {
        **result,
        "exit_codes": codes,
        "message_identifier": PROFILES[args.profile],
        "backend": "zmq",
        "rf_transmission": False,
        "pws_routed": True,
        "receiver": "patched-srsUE-SI-monitor",
        "physical_phone": "NOT VERIFIED",
    }


def main():
    parser = argparse.ArgumentParser(description="OCUDU PWS lab 연동")
    parser.add_argument("command", choices=["prepare", "receive"])
    parser.add_argument("--config", type=Path, default=ROOT / "configs/pws.example.yaml")
    parser.add_argument("--profile", choices=PROFILES, default="monthly-test")
    parser.add_argument("--backend", choices=["zmq", "bladerf-x40"], default="zmq")
    parser.add_argument("--serial", default="")
    parser.add_argument("--output", type=Path, default=Path("output/pws-integration"))
    parser.add_argument("--gnb", default=os.environ.get("GNB_ZMQ_BINARY", "build/bin/gnb-zmq"))
    parser.add_argument("--ue", default=os.environ.get("SRSUE_BINARY", "build/bin/srsue"))
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    if not 5 <= args.timeout <= 120:
        parser.error("timeout은 5..120초입니다.")
    code = 0
    try:
        if args.command == "receive" and args.backend != "zmq":
            raise LabError(
                "E_HARDWARE_NOT_VERIFIED", "자동 수신 검증은 ZMQ 전용입니다. 실물 시험 환경은 별도 검증해야 합니다.", 3
            )
        path, message = prepare(load_config(args.config), args.profile, args.backend, args.output, args.serial)
        details = {
            "config": str(path),
            "backend": args.backend,
            "message_identifier": PROFILES[args.profile],
            "rf_transmission": False,
            "hardware_execution": "NOT VERIFIED",
        }
        if args.command == "receive":
            details = receive(args, path, message)
        result = report(
            "non-sdr" if args.backend == "zmq" else "sdr-bladerf-x40",
            "pws-" + args.command,
            "PASS",
            details,
            artifact=args.output,
        )
    except (LabError, OSError) as exc:
        code = exc.exit_code if isinstance(exc, LabError) else 2
        result = report(
            "non-sdr" if args.backend == "zmq" else "sdr-bladerf-x40",
            "pws-" + args.command,
            "BLOCKED" if code == 3 else "FAIL",
            error={"code": getattr(exc, "code", "E_IO"), "detail": str(exc)},
            artifact=args.output,
        )
    write_report(args.output / "pws-integration.json", result)
    audit(args.output, "pws-" + args.command, result["result"], error=result["error"])
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
