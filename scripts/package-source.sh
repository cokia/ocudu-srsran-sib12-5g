#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/fetch-upstream.py ocudu
python3 scripts/fetch-upstream.py bladerf
python3 scripts/fetch-upstream.py srsran4g
mkdir -p artifacts/release
# 원본 소스 + 패치 + 재현 스크립트를 함께 보존한다. build와 개인 설정은 제외한다.
tar --exclude='./.git' --exclude='*/.git' --exclude='./build' --exclude='./.venv' \
 --exclude='./artifacts' --exclude='./output' --exclude='*/__pycache__' --exclude='./.pytest_cache' \
 --exclude='./.ruff_cache' --exclude='*/.DS_Store' \
 --exclude='./.env*' --exclude='*.pem' --exclude='*.key' --exclude='./configs/*.local.yaml' \
 -czf artifacts/release/ocudu-pws-lab-0.1.0-source.tar.gz .
