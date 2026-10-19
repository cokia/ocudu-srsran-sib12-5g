"""장치 설정 전용 진단 실행기. PWS 데이터를 장치에 전달하지 않는다."""

import argparse
import json
import os
from pathlib import Path
import subprocess
from .config_loader import load_yaml, validate_schema
from .errors import LabError
from .reporting import audit, report, write_report


def main():
    parser = argparse.ArgumentParser(description="bladeRF x40 bounded diagnostics")
    parser.add_argument("command", choices=["info", "capabilities", "verify", "loopback", "rx"])
    parser.add_argument("--config", type=Path, default=Path("configs/bladerf-x40.yaml"))
    parser.add_argument("--binary", default=os.environ.get("BLADERF_DIAG", "build/bin/bladerf-x40-diag"))
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--fault", default="none")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path("output/sdr")
    code = 1
    try:
        cfg = validate_schema(load_yaml(args.config), "bladerf-x40.schema.json")
        output = args.output or Path(cfg["output"]["directory"])
        if args.hardware and args.mock:
            raise LabError("E_ARGUMENT", "hardware/mock 중 하나만 선택하십시오.")
        hardware = args.hardware or (cfg["device"]["access"] == "hardware" and not args.mock)
        if hardware and not args.hardware:
            raise LabError("E_HARDWARE_OPT_IN", "실제 USB 접근에는 --hardware가 필요합니다.", 3)
        if hardware and args.fault != "none":
            raise LabError("E_ARGUMENT", "실제 장치에 mock fault를 적용할 수 없습니다.")
        command = [args.binary, args.command]
        if hardware:
            command.append("--hardware")
            if cfg["device"]["serial"]:
                command.extend(["--serial", cfg["device"]["serial"]])
        else:
            command.extend(["--mock", "--fault", args.fault])
        run = subprocess.run(
            command, capture_output=True, text=True, timeout=cfg["diagnostics"]["max_duration_seconds"], check=False
        )
        raw = json.loads(run.stdout)
        status = raw["status"]
        code = run.returncode
        result = report("sdr-bladerf-x40", args.command, status, raw, raw.get("error"), output, raw.get("device"))
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{args.command}.txt").write_text(run.stderr, encoding="utf-8")
    except LabError as exc:
        code = exc.exit_code
        result = report(
            "sdr-bladerf-x40",
            args.command,
            "BLOCKED" if code == 3 else "FAIL",
            error={"code": exc.code, "detail": exc.detail},
            artifact=output,
        )
    except subprocess.TimeoutExpired:
        code = 4
        result = report(
            "sdr-bladerf-x40",
            args.command,
            "FAIL",
            error={"code": "E_DIAG_TIMEOUT", "detail": "20초 제한. 장치 상태를 재확인하십시오."},
            artifact=output,
        )
    except (OSError, ValueError, KeyError) as exc:
        code = 3
        result = report(
            "sdr-bladerf-x40",
            args.command,
            "BLOCKED",
            error={"code": "E_DIAG_EXEC", "detail": str(exc)},
            artifact=output,
        )
    write_report(output / f"{args.command}.json", result)
    audit(output, args.command, result["result"], error=result["error"])
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
