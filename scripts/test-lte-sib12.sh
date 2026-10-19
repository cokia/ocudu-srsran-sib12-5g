#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python=${LAB_PYTHON:-.venv/bin/python}
if [[ "${LAB_LTE_TEST_LIMIT:-0}" != 1 ]]; then
  exec "$python" -m controller.checkpoints --name lte-sib12 --timeout 420 -- \
    env LAB_LTE_TEST_LIMIT=1 bash scripts/test-lte-sib12.sh
fi
out=artifacts/lte-sib12/final
mkdir -p "$out"
"$python" -m pytest tests/unit/test_lte_sib12.py -q --junitxml="$out/unit.xml"
for plmn in 45005 45008 45006; do
  "$python" -m controller.lte_sib12 receive --plmn "$plmn" --output "$out/korean-$plmn"
done
"$python" - <<'PYTHON'
from pathlib import Path
import yaml
from controller.config_loader import load_config
config = load_config(Path('configs/pws.example.yaml'))
config['pws']['message']['text'] = '[TEST] Offline LTE CMAS reception.'
Path('artifacts/lte-sib12/final/english.yaml').write_text(yaml.safe_dump(config))
config['pws']['message']['text'] = '[시험] ' + '가' * 610
Path('artifacts/lte-sib12/final/boundary.yaml').write_text(yaml.safe_dump(config, allow_unicode=True))
PYTHON
"$python" -m controller.lte_sib12 receive --profile monthly-test --plmn 00101 \
  --config "$out/english.yaml" --output "$out/english"
"$python" -m controller.lte_sib12 receive --config "$out/boundary.yaml" --output "$out/boundary"
