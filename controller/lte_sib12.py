"""srsRAN LTE SIB12를 ZMQ에서 수신하여 공유 UCS-2 CB Data와 비교한다."""

import argparse
import configparser
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from . import cb_data
from .config_loader import ROOT, load_config, validate_schema
from .errors import LabError
from .message_model import LaboratoryMessage
from .pws_profiles import DEFAULT_PLMN, PLMNS, PROFILES
from .reporting import audit, report, write_report

SEGMENT = re.compile(
    r"LAB_LTE_SIB12 id=(\d+) serial=(\d+) segment=(\d+) last=([01]) dcs=(none|[0-9a-fA-F]{2}) payload=([0-9a-fA-F]+)\n"
)
PLMN = re.compile(r"LAB_LTE_SIB1 plmn=(\d{5,6})\n")


def write_ini(path, sections):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_dict(sections)
    contents = io.StringIO()
    parser.write(contents)
    path.write_text(contents.getvalue(), encoding="utf-8")


def prepare(config, profile, output, plmn=DEFAULT_PLMN):
    validate_schema(config)
    if not isinstance(plmn, str) or not isinstance(profile, str) or plmn not in PLMNS or profile not in PROFILES:
        raise LabError("E_LTE_PROFILE", "지원하지 않는 PLMN 또는 message profile입니다.")
    message = LaboratoryMessage.from_config(config)
    if not message.text.startswith(("[시험", "[TEST]")):
        raise LabError("E_TEST_LABEL", "연동 시험 문구는 [시험 또는 [TEST]로 시작해야 합니다.")
    cb_data.encode(message.text)
    templates = ROOT / "configs/lte"
    hashes = json.loads((templates / "sha256.json").read_text())
    for name in ("sib.conf", "rr.conf", "rb.conf"):
        if hashlib.sha256((templates / name).read_bytes()).hexdigest() != hashes[name]:
            raise LabError("E_LTE_TEMPLATE", f"고정 LTE template이 변경됐습니다: {name}")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ("rr.conf", "rb.conf"):
        (output / name).write_bytes((templates / name).read_bytes())
    # JSON string의 quote/backslash/개행 escaping은 허용된 BMP 입력에서 libconfig와 같다.
    sib12 = (
        "\nsib12 = {\n  message_id = %d;\n  serial_num = 0;\n  data_coding_scheme = 72;\n  warning_message = %s;\n};\n"
        % (PROFILES[profile], json.dumps(message.text, ensure_ascii=False))
    )
    (output / "sib.conf").write_text((templates / "sib.conf").read_text() + sib12, encoding="utf-8")
    write_ini(
        output / "enb.conf",
        {
            "enb": {
                "enb_id": "0x19B",
                "mcc": plmn[:3],
                "mnc": plmn[3:],
                "mme_addr": "127.0.1.100",
                "gtp_bind_addr": "127.0.1.1",
                "s1c_bind_addr": "127.0.1.1",
                "n_prb": 25,
            },
            "enb_files": {
                "sib_config": str(output / "sib.conf"),
                "rr_config": str(output / "rr.conf"),
                "rb_config": str(output / "rb.conf"),
            },
            "rf": {
                "device_name": "zmq",
                "device_args": "tx_port=tcp://127.0.0.1:2100,rx_port=tcp://127.0.0.1:2101,id=enb,base_srate=23.04e6,fail_on_disconnect=true,trx_timeout_ms=1000",
                "tx_gain": 0,
                "rx_gain": 0,
            },
            "log": {"filename": "stdout", "all_level": "warning", "rrc_level": "info", "all_hex_limit": 0},
            "expert": {"nof_phy_threads": 1},
        },
    )
    write_ini(
        output / "ue.conf",
        {
            "rf": {
                "device_name": "zmq",
                "device_args": "tx_port=tcp://127.0.0.1:2101,rx_port=tcp://127.0.0.1:2100,id=ue,base_srate=23.04e6,fail_on_disconnect=true,trx_timeout_ms=1000",
                "srate": "23.04e6",
                "nof_antennas": 1,
                "tx_gain": 0,
                "rx_gain": 0,
                "time_adv_nsamples": 0,
            },
            "rat.eutra": {"dl_earfcn": 3350, "nof_carriers": 1},
            "rat.nr": {"nof_carriers": 0},
            "rrc": {"release": 15, "ue_category": 4},
            # 공개 upstream의 soft USIM 시험값. attach는 시작하지 않는다.
            "usim": {
                "mode": "soft",
                "algo": "milenage",
                "opc": "63BFA50EE6523365FF14C1F45F88737D",
                "k": "00112233445566778899aabbccddeeff",
                "imsi": plmn + "0123456780",
                "imei": "353490069873319",
            },
            "log": {"filename": "stdout", "all_level": "warning", "rrc_level": "info", "all_hex_limit": 0},
            "phy": {"nof_phy_threads": 1},
            "pcap": {"enable": "none"},
        },
    )
    return output / "enb.conf", message


def recovered(log, identifier):
    segments, last = {}, None
    for match in SEGMENT.finditer(log):
        mid, serial, index, final = map(int, match.group(1, 2, 3, 4))
        dcs, payload = match.group(5, 6)
        if mid != identifier or serial != 0 or index > 63 or len(payload) % 2:
            raise LabError("E_LTE_METADATA", "수신 SIB12 식별자/segment가 일치하지 않습니다.")
        if (index == 0 and dcs.lower() != "48") or (index != 0 and dcs != "none"):
            raise LabError("E_LTE_DCS", "수신 SIB12 DCS가 UCS-2 profile과 다릅니다.")
        item = (bytes.fromhex(payload), final)
        if not 1 <= len(item[0]) <= 100 or (not final and len(item[0]) != 100):
            raise LabError("E_LTE_SIZE", "고정 srsENB의 segment 길이와 다릅니다.")
        if index in segments and segments[index] != item:
            raise LabError("E_LTE_CONFLICT", "동일 segment의 내용이 변경됐습니다.")
        segments[index] = item
        if final:
            if last is not None and last != index:
                raise LabError("E_LTE_LAST", "last segment가 일치하지 않습니다.")
            last = index
    if last is None or any(i not in segments for i in range(last + 1)):
        return None
    if len(segments) != last + 1 or any(segments[i][1] for i in range(last)):
        raise LabError("E_LTE_ORDER", "수신 segment 범위가 잘못되었습니다.")
    payload = b"".join(segments[i][0] for i in range(last + 1))
    return {"text": cb_data.decode(payload, padding="ocudu-zero"), "payload_hex": payload.hex(), "segments": last + 1}


def received_plmn(log, expected):
    observed = set(PLMN.findall(log))
    if observed and observed != {expected}:
        raise LabError("E_LTE_PLMN", f"요청={expected}, 수신={sorted(observed)}")
    return expected if observed else None


def receive(args, path, message):
    if not Path("/sys/class/net").exists() or {p.name for p in Path("/sys/class/net").iterdir()} != {"lo"}:
        raise LabError("E_NETWORK_ISOLATION", "Docker --network none이 필요합니다.", 3)
    processes, streams = [], []
    paths = [args.output / "srsenb.log", args.output / "srsue.log"]
    interrupted = False
    result, observed, error = None, None, None

    def stop_requested(signum, frame):
        nonlocal interrupted
        interrupted = True

    old = {sig: signal.signal(sig, stop_requested) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        env = dict(os.environ, PWS_LAB_LTE_SI_MONITOR="1")
        for log, command in zip(paths, ([args.enb, str(path)], [args.ue, str(path.parent / "ue.conf")])):
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
            if "Random Access Transmission:" in ue:
                raise LabError("E_RX_MODE", "SI-only monitor에서 Random Access가 시작됐습니다.", 1)
            observed = received_plmn(ue, args.plmn)
            result = recovered(ue, PROFILES[args.profile])
            if result is not None and observed is not None:
                if (
                    result["text"] != message.text
                    or result["payload_hex"] != cb_data.encode(message.text, padding="ocudu-zero").hex()
                ):
                    raise LabError("E_ROUND_TRIP", "수신 원문 또는 CB Data가 송신 입력과 다릅니다.", 1)
                if "Found Cell:" not in ue:
                    raise LabError("E_RX_EVIDENCE", "LTE PHY 셀 획득 증거가 없습니다.", 1)
                break
            time.sleep(0.2)
        else:
            raise LabError("E_RX_TIMEOUT", "LTE SIB12 전체 수신 제한 시간 또는 중단", 4)
    except (LabError, OSError) as exc:
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
        "serial_number": 0,
        "data_coding_scheme": 72,
        "plmn": args.plmn,
        "received_plmn": observed,
        "backend": "zmq",
        "rf_transmission": False,
        "receiver": "patched-srsUE-LTE-SI-monitor",
        "physical_phone": "NOT VERIFIED",
    }


def main():
    parser = argparse.ArgumentParser(description="LTE SIB12 ZMQ 수신 시험")
    parser.add_argument("command", choices=["prepare", "receive"])
    parser.add_argument("--config", type=Path, default=ROOT / "configs/pws.example.yaml")
    parser.add_argument("--profile", choices=PROFILES, default="korean-safety")
    parser.add_argument("--plmn", choices=PLMNS, default=DEFAULT_PLMN)
    parser.add_argument("--output", type=Path, default=Path("output/lte-sib12"))
    parser.add_argument("--enb", default=os.environ.get("SRSENB_LTE_BINARY", "build/bin/srsenb-lte"))
    parser.add_argument("--ue", default=os.environ.get("SRSUE_LTE_BINARY", "build/bin/srsue-lte"))
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    if not 5 <= args.timeout <= 120:
        parser.error("timeout은 5..120초입니다.")
    code = 0
    try:
        path, message = prepare(load_config(args.config), args.profile, args.output, args.plmn)
        details = {
            "config": str(path),
            "plmn": args.plmn,
            "backend": "zmq",
            "rf_transmission": False,
            "reception": "NOT VERIFIED",
        }
        if args.command == "receive":
            details = receive(args, path, message)
        result = report("non-sdr", "lte-sib12-" + args.command, "PASS", details, artifact=args.output)
    except (LabError, OSError) as exc:
        code = exc.exit_code if isinstance(exc, LabError) else 2
        result = report(
            "non-sdr",
            "lte-sib12-" + args.command,
            "BLOCKED" if code == 3 else "FAIL",
            error={"code": getattr(exc, "code", "E_IO"), "detail": str(exc)},
            artifact=args.output,
        )
    result["rat"] = "LTE"
    result["srsran4g_commit"] = json.loads((ROOT / "dependencies.lock.json").read_text())["srsran4g"]["commit"]
    result["ocudu_used"] = False
    write_report(args.output / "lte-sib12.json", result)
    audit(args.output, "lte-sib12-" + args.command, result["result"], error=result["error"])
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
