#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python=${LAB_PYTHON:-.venv/bin/python}
mkdir -p artifacts/sdr
export LAB_REQUIRE_DIAG=1 LAB_REQUIRE_CODEC=1
"$python" -m pytest tests/unit tests/integration tests/sdr --junitxml=artifacts/sdr/junit.xml
"$python" -m controller validate --mode sdr-bladerf-x40 --output artifacts/sdr
for command in info capabilities verify rx loopback; do
 "$python" -m controller.hardware "$command" --mock --output artifacts/sdr
 done
# 실제 장치는 별도 명시적 명령으로만 검사한다.
