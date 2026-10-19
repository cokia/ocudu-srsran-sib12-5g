#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# 이 프로젝트의 Compose 리소스만 정지한다. 결과 volume은 유지한다.
docker compose -f docker/compose.yaml --profile non-sdr --profile sdr-bladerf-x40 down --timeout 15
