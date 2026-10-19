#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${LAB_PWS_BUILD_LIMIT:-0}" != 1 ]]; then
  exec python3 -m controller.checkpoints --name docker-pws-integration --timeout 2700 -- \
    env LAB_PWS_BUILD_LIMIT=1 bash scripts/build-pws-integration-docker.sh
fi
bash scripts/build-zmq-docker.sh
container="pws-lab-radio-build-$$"
cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
docker run --rm --name "$container" --memory 2g --cpus 2 -v "$PWD:/lab" \
  pws-lab-zmq-toolchain:0.1.0 bash -c 'scripts/build-sdr.sh && scripts/build-radio-plugin.sh && scripts/test-radio-plugin.sh && python3 scripts/stage-runtime.py radio-plugin'
docker build --build-context lab_build=build/runtime/radio-plugin \
  -f docker/Dockerfile.radio-plugin -t pws-lab-radio-plugin:0.1.0 .
