#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python=${LAB_PYTHON:-.venv/bin/python}
mkdir -p artifacts/non-sdr
export LAB_REQUIRE_CODEC=1
"$python" -m pytest tests/unit tests/integration tests/non-sdr --junitxml=artifacts/non-sdr/junit.xml
"$python" -m controller validate --output artifacts/non-sdr
"$python" -m controller inspect-sib12 --output artifacts/non-sdr
if [[ "${1:-}" == --gnb ]]; then
  scripts/run-non-sdr.sh --output artifacts/non-sdr
fi
