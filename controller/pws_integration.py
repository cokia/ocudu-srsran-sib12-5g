"""공유 PWS 입력을 OCUDU CMAS test SI에 연결하고 ZMQ 수신 원문을 비교한다."""

import argparse
import configparser
import io
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
from .pws_profiles import PROFILES, PLMNS, DEFAULT_PLMN

SEGMENT = re.compile(
    r"LAB_SIB8 id=(\d+) serial=(\d+) segment=(\d+) last=([01]) dcs=(none|[0-9a-fA-F]{2}) payload=([0-9a-fA-F]+)"
)


def prepare(config, profile, backend, output, serial="", plmn=DEFAULT_PLMN):
    validate_profiles()
    if not isinstance(plmn, str) or plmn not in PLMNS:
        raise LabError("E_PLMN", "PLMN은 45005, 45008, 45006 또는 00101 문자열이어야 합니다.")
    message = LaboratoryMessage.from_config(config)
    if not message.text.startswith(("[시험", "[TEST]")):
        raise LabError("E_TEST_LABEL", "연동 시험 문구는 [시험 또는 [TEST]로 시작해야 합니다.")
    cb_data.encode(message.text)
    gnb = load_yaml(ROOT / "configs/gnb.zmq.yaml")
    gnb["cell_cfg"]["plmn"] = plmn
    for area in gnb["cu_cp"]["amf"]["supported_tracking_areas"]:
        for item in area["plmn_list"]:
            item["plmn"] = plmn
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
    if backend == "zmq":
        ue = configparser.ConfigParser(interpolation=None)
        ue.read(ROOT / "configs/srsue.zmq.conf", encoding="utf-8")
        ue["usim"]["imsi"] = plmn + ue["usim"]["imsi"][5:]
        # 고정 upstream의 ASN.1 JSON logger로 수신 SIB1 PLMN을 검증한다.
        ue["log"]["rrc_level"] = "debug"
        contents = io.StringIO()
        ue.write(contents)
        (output / "srsue.pws.conf").write_text(contents.getvalue(), encoding="utf-8")
    return path, message


def received_plmn(log, expected):
    observed = set()
    markers = list(re.finditer(r"\[RRC-NR\s*\]\s+\[D\]\s+Content:", log))
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(log)
        content = log[marker.end() : end]
        prefix = r'\s*\[\s*\{\s*"BCCH-DL-SCH-Message"\s*:\s*\{\s*"message"\s*:\s*\{\s*"c1"\s*:\s*\{'
        if not re.match(prefix + r'\s*"systemInformationBlockType1"\s*:\s*\{', content):
            continue
        access = re.search(r'"cellAccessRelatedInfo"\s*:\s*', content)
        if access is None:
            continue
        try:
            # 고정 srsUE의 pdcch-ConfigCommon JSON은 malformed다. 정상 출력되는
            # 수신 cellAccessRelatedInfo 객체만 읽고 나머지 ASN.1 JSON에 의존하지 않는다.
            identity_info, _ = json.JSONDecoder().raw_decode(content[access.end() :])
        except json.JSONDecodeError:
            # process가 아직 PLMN 객체를 쓰는 중이면 다음 poll에서 다시 읽는다.
            continue
        try:
            entries = identity_info["plmn-IdentityList"]
            if len(entries) != 1 or len(entries[0]["plmn-IdentityList"]) != 1:
                raise ValueError("single PLMN profile")
            identity = entries[0]["plmn-IdentityList"][0]
            mcc, mnc = identity["mcc"], identity["mnc"]
            if len(mcc) != 3 or len(mnc) != 2 or any(type(n) is not int or not 0 <= n <= 9 for n in mcc + mnc):
                raise ValueError("MCC/MNC digits")
            observed.add("".join(str(n) for n in mcc + mnc))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LabError("E_PLMN_RX", "수신 SIB1의 단일 MCC/MNC 구조가 profile과 다릅니다.", 1) from exc
    if observed and observed != {expected}:
        raise LabError("E_PLMN_RX", f"요청 PLMN={expected}, 수신 PLMN={sorted(observed)}", 1)
    return expected if observed else None


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
        for log, command in zip(paths, ([args.gnb, "-c", str(path)], [args.ue, str(args.output / "srsue.pws.conf")])):
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
            observed = received_plmn(ue, args.plmn)
            result = recovered(ue, PROFILES[args.profile])
            if result is not None and observed is not None:
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
        "plmn": args.plmn,
        "mcc": args.plmn[:3],
        "mnc": args.plmn[3:],
        "received_plmn": observed,
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
    parser.add_argument(
        "--plmn", choices=PLMNS, default=DEFAULT_PLMN, help="MCC+MNC: SKT 45005 / KT 45008 / LG U+ 45006"
    )
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
        path, message = prepare(
            load_config(args.config), args.profile, args.backend, args.output, args.serial, args.plmn
        )
        details = {
            "config": str(path),
            "backend": args.backend,
            "message_identifier": PROFILES[args.profile],
            "plmn": args.plmn,
            "mcc": args.plmn[:3],
            "mnc": args.plmn[3:],
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
