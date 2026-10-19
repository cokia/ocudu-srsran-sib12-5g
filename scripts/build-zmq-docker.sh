#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${LAB_ZMQ_BUILD_LIMIT:-0}" != 1 ]]; then
 exec python3 -m controller.checkpoints --name docker-zmq --timeout 2700 -- \
  env LAB_ZMQ_BUILD_LIMIT=1 bash scripts/build-zmq-docker.sh
fi
container="pws-lab-zmq-build-$$"
cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
docker build -f docker/Dockerfile.build -t pws-lab-toolchain:0.1.0 .
docker build -f docker/Dockerfile.zmq-build -t pws-lab-zmq-toolchain:0.1.0 .
docker run --rm --name "$container" --memory 4g --cpus 2 -v "$PWD:/lab" pws-lab-zmq-toolchain:0.1.0 bash scripts/build-zmq.sh
docker run --rm -v "$PWD:/lab" pws-lab-zmq-toolchain:0.1.0 python3 scripts/stage-runtime.py zmq
docker build -f docker/Dockerfile.runtime -t pws-lab-runtime:0.1.0 .
docker build --build-context lab_build=build/runtime/zmq -f docker/Dockerfile.zmq -t pws-lab-zmq:0.1.0 .
