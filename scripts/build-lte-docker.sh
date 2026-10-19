#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# bind mount 안의 build가 root로 실행되기 전에 host 사용자 소유로 생성한다.
mkdir -p artifacts/lte-sib12/docker
jobs=${LAB_BUILD_JOBS:-2}
memory=${LAB_BUILD_MEMORY:-4g}
[[ "$jobs" =~ ^[1-4]$ && "$memory" =~ ^[468]g$ ]] || exit 2
if [[ "${LAB_LTE_BUILD_LIMIT:-0}" != 1 ]]; then
  exec python3 -m controller.checkpoints --name docker-lte --timeout 2700 -- \
    env LAB_LTE_BUILD_LIMIT=1 bash scripts/build-lte-docker.sh
fi
container="pws-lab-lte-build-$$"
cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
docker build -f docker/Dockerfile.build -t pws-lab-toolchain:0.1.0 .
docker build -f docker/Dockerfile.zmq-build -t pws-lab-zmq-toolchain:0.1.0 .
docker build -f docker/Dockerfile.lte-build -t pws-lab-lte-toolchain:0.1.0 .
docker run --rm --name "$container" --memory "$memory" --cpus "$jobs" -e LAB_BUILD_JOBS="$jobs" -v "$PWD:/lab" pws-lab-lte-toolchain:0.1.0 bash scripts/build-lte.sh
docker run --rm -v "$PWD:/lab" pws-lab-lte-toolchain:0.1.0 python3 scripts/stage-runtime.py lte
docker build -f docker/Dockerfile.runtime -t pws-lab-runtime:0.1.0 .
docker build --build-context lab_build=build/runtime/lte -f docker/Dockerfile.lte -t pws-lab-lte:0.1.0 .
