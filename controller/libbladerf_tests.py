"""장비를 열지 않는 실제 libbladeRF API 및 adapter contract 테스트."""

import json
from pathlib import Path
import subprocess
from .reporting import audit, report, write_report


def main():
    output = Path("artifacts/libbladerf")
    output.mkdir(parents=True, exist_ok=True)
    tests = [
        (f"upstream-{name}", [f"build/libbladerf-upstream/bin/libbladeRF_test_{name}"])
        for name in ("c", "cpp", "version", "parse", "interleaver")
    ]
    tests.append(
        (
            "adapter-contract",
            ["build/libbladerf-tests/bladerf-adapter-tests", f"--gtest_output=xml:{output}/adapter.xml"],
        )
    )
    failed = False
    for name, command in tests:
        log = output / f"{name}.log"
        error = None
        try:
            with log.open("w") as stream:
                run = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=20, check=False)
            status = "PASS" if run.returncode == 0 else "FAIL"
            if run.returncode:
                error = {"code": "E_LIBRARY_TEST", "exit_code": run.returncode}
        except (OSError, subprocess.TimeoutExpired) as exc:
            status, error = "FAIL", {"code": "E_LIBRARY_EXEC", "detail": str(exc)}
        result = report(
            "sdr-bladerf-x40",
            name,
            status,
            {"actual_library": True, "hardware_verified": False, "device_api_double": name == "adapter-contract"},
            error,
            log,
        )
        write_report(output / f"{name}.json", result)
        audit(output, name, status)
        print(json.dumps(result, ensure_ascii=False))
        failed |= status != "PASS"
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
