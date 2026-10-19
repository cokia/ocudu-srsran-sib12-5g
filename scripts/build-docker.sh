#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# bind mount 안의 build가 root로 실행되기 전에 host 사용자 소유로 생성한다.
mkdir -p artifacts/docker
jobs=${LAB_BUILD_JOBS:-2}
memory=${LAB_BUILD_MEMORY:-4g}
[[ "$jobs" =~ ^[1-4]$ && "$memory" =~ ^[468]g$ ]] || exit 2
mode=${1:-non-sdr}
case "$mode" in non-sdr|sdr-bladerf-x40|controller) ;; *) exit 2 ;; esac
if [[ "${LAB_DOCKER_LIMIT_ACTIVE:-0}" != 1 ]]; then
 exec python3 -m controller.checkpoints --name "docker-$mode" --mode "$([[ "$mode" == sdr-bladerf-x40 ]] && echo sdr-bladerf-x40 || echo non-sdr)" \
  --timeout 2700 -- env LAB_DOCKER_LIMIT_ACTIVE=1 bash scripts/build-docker.sh "$mode"
fi
mkdir -p artifacts
# 컨테이너 compiler에서 source를 빌드한 다음 최소 runtime을 조립한다.
docker build -f docker/Dockerfile.build -t pws-lab-toolchain:0.1.0 .
if [[ "$mode" == non-sdr ]]; then
 docker run --rm --memory "$memory" --cpus "$jobs" -e LAB_BUILD_JOBS="$jobs" -v "$PWD:/lab" pws-lab-toolchain:0.1.0 bash scripts/build-non-sdr.sh
else
 docker run --rm --memory "$memory" --cpus "$jobs" -e LAB_BUILD_JOBS="$jobs" -v "$PWD:/lab" pws-lab-toolchain:0.1.0 bash scripts/build-non-sdr.sh --codec-only
fi
if [[ "$mode" == sdr-bladerf-x40 ]]; then
 docker run --rm --memory 1g --cpus 1 -e LAB_BUILD_JOBS=1 -v "$PWD:/lab" pws-lab-toolchain:0.1.0 bash scripts/build-sdr.sh
fi
docker run --rm -v "$PWD:/lab" pws-lab-toolchain:0.1.0 python3 scripts/stage-runtime.py "$mode"
docker build -f docker/Dockerfile.runtime -t pws-lab-runtime:0.1.0 .
file=non-sdr
[[ "$mode" == controller ]] && file=controller
[[ "$mode" == sdr-bladerf-x40 ]] && file=sdr
docker build --build-context "lab_build=build/runtime/$mode" -f "docker/Dockerfile.$file" -t "pws-lab-$mode:0.1.0" .
