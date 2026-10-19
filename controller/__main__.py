import argparse
import json
from pathlib import Path
import sys
from . import cb_data
from .config_loader import load_config
from .errors import LabError
from .message_model import LaboratoryMessage
from .logging import emit
from .protocol import OfflineCodec, read_encoded
from .reporting import audit, digest, report, write_report


def main():
    parser = argparse.ArgumentParser(description="OCUDU 오프라인 PWS 검증")
    parser.add_argument("command", choices=["validate", "decode", "inspect-sib12"])
    parser.add_argument("--config", type=Path, default=Path("configs/pws.example.yaml"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--codec")
    parser.add_argument("--mode", choices=["non-sdr", "sdr-bladerf-x40"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    mode = args.mode or "non-sdr"
    output = args.output or Path("output")
    code = 0
    level = "info"
    try:
        cfg = load_config(args.config)
        level = cfg["application"]["log_level"]
        emit("config-validated", level, mode=mode)
        mode = args.mode or cfg["application"]["mode"]
        output = args.output or Path(cfg["pws"]["output"]["directory"])
        audit(output, "config-validated", "PASS", config_sha256=digest(cfg))
        codec = OfflineCodec(args.codec)
        if args.command == "validate":
            msg = LaboratoryMessage.from_config(cfg)
            payload = cb_data.encode(msg.text)
            emit("cb-data-encoded", level, "debug", payload_bytes=len(payload))
            encoded = codec.encode(payload)
            decoded = codec.decode(encoded["segments"])
            recovered = cb_data.decode(bytes.fromhex(decoded["payload_hex"]))
            if recovered != msg.text:
                raise LabError("E_ROUND_TRIP", "복원 텍스트가 일치하지 않습니다.", 1)
            if codec.encode(payload) != encoded:
                raise LabError("E_DETERMINISM", "인코딩 결과가 달라졌습니다.", 1)
            write_report(output / "offline-sib8.json", encoded)
            details = {
                "message_id": msg.id,
                "payload_sha256": digest(encoded),
                "segment_count": len(encoded["segments"]),
                "utf8_bytes": len(msg.text.encode()),
                "ucs2_characters": len(msg.text),
                "cmas_sib": 8,
                "sib12_is_cmas": False,
                "rf_transmission": False,
                "round_trip": True,
                "deterministic": True,
            }
        elif args.command == "decode":
            if not args.input:
                raise LabError("E_INPUT", "--input이 필요합니다.")
            details = codec.decode(read_encoded(args.input))
            details["text"] = cb_data.decode(bytes.fromhex(details["payload_hex"]))
        else:
            details = codec.inspect_sib12()
        result = report(mode, args.command, "PASS", details, artifact=output)
    except LabError as exc:
        code = exc.exit_code
        emit("validation-error", level, "error", code=exc.code)
        result = report(
            mode,
            args.command,
            "BLOCKED" if code == 3 else "FAIL",
            error={"code": exc.code, "detail": exc.detail},
            artifact=output,
        )
    except (OSError, ValueError) as exc:
        code = 2
        result = report(mode, args.command, "FAIL", error={"code": "E_IO", "detail": str(exc)}, artifact=output)
    try:
        write_report(output / f"{args.command}-{mode}.json", result)
        audit(output, args.command, result["result"], error=result["error"])
    except OSError as exc:
        print(f"E_REPORT_IO: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
