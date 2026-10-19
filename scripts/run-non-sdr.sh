#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python=${LAB_PYTHON:-.venv/bin/python}
"$python" -m controller validate --output output/non-sdr
if [[ "$(ls /sys/class/net 2>/dev/null)" == lo ]]; then
  exec "$python" -m controller.gnb "$@"
fi
# namespace 안에서 loopback만 활성화한다. 실패 시 network isolation을 생략하지 않는다.
exec unshare --user --map-root-user --net sh -c 'ip link set lo up; exec "$@"' sh "$python" -m controller.gnb "$@"
