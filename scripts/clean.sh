#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# 선택한 재생성 가능 build 디렉터리만 삭제한다. upstream/output은 보존한다.
case "${1:-}" in
 non-sdr) rm -rf build/non-sdr ;;
 sdr-bladerf-x40) rm -rf build/sdr build/sdr-mock build/bladerf ;;
 zmq) rm -rf build/zmq-gnb build/srsue build/runtime/zmq ;;
 *) echo '사용법: scripts/clean.sh non-sdr|sdr-bladerf-x40|zmq' >&2; exit 2 ;;
esac
