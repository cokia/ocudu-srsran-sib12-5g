"""실행 제한과 단계별 실제 결과 기록."""

import argparse
import os
from pathlib import Path
import signal
import subprocess
import time
from .reporting import audit, report, write_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--mode", choices=["non-sdr", "sdr-bladerf-x40"], default="non-sdr")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--output", type=Path, default=Path("artifacts/checkpoints"))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 2700 or not args.command or not args.name.replace("-", "").isalnum():
        parser.error("timeout=1..2700, 영숫자 단계 이름, 실행 명령이 필요합니다.")
    command = args.command[1:] if args.command[0] == "--" else args.command
    if not command:
        parser.error("실행 명령이 필요합니다.")
    args.output.mkdir(parents=True, exist_ok=True)
    log_path = args.output / f"{args.name}.log"
    started = time.monotonic()
    status, code = "BLOCKED", 3
    with log_path.open("w") as log:
        try:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=args.timeout)
                status = {0: "PASS", 3: "BLOCKED", 77: "SKIP"}.get(code, "FAIL")
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                status, code = "FAIL", 4
        except OSError as exc:
            log.write(str(exc))
    result = report(
        args.mode,
        args.name,
        status,
        {"exit_code": code, "elapsed_seconds": round(time.monotonic() - started, 3), "timeout_seconds": args.timeout},
        artifact=log_path,
    )
    write_report(args.output / f"{args.name}.json", result)
    audit(args.output, args.name, status)
    print(f"{args.name}: {status} ({code}) — {log_path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
