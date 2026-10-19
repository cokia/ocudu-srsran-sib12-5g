#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python=${LAB_PYTHON:-.venv/bin/python}
if [[ "${LAB_PWS_TEST_LIMIT:-0}" != 1 ]]; then
  exec "$python" -m controller.checkpoints --name pws-integration --timeout 360 -- \
    env LAB_PWS_TEST_LIMIT=1 bash scripts/test-pws-integration.sh
fi
out=artifacts/pws-integration/final
mkdir -p "$out"
"$python" - <<'PYTHON'
from pathlib import Path
import yaml
from controller.config_loader import load_config
config = load_config(Path('tests/fixtures/pws.english.yaml'))
config['pws']['message']['text'] = '[TEST] Offline CMAS reception.'
Path('artifacts/pws-integration/final/english.yaml').write_text(yaml.safe_dump(config))
PYTHON
"$python" -m controller.zmq_rx --output "$out/baseline"
"$python" -m controller.pws_integration receive --profile monthly-test \
  --config "$out/english.yaml" --output "$out/english"
"$python" -m controller.pws_integration receive --profile korean-safety --output "$out/korean"
for plmn in 45008 45006; do
  "$python" -m controller.pws_integration receive --profile korean-safety \
    --plmn "$plmn" --output "$out/korean-$plmn"
done
"$python" - <<'PY'
from pathlib import Path
import yaml
from controller.config_loader import load_config
config = load_config(Path('configs/pws.example.yaml'))
config['pws']['message']['text'] = '[시험] ' + '가' * 610
Path('artifacts/pws-integration/final/boundary.yaml').write_text(yaml.safe_dump(config, allow_unicode=True))
PY
"$python" -m controller.pws_integration receive --profile korean-safety \
  --config "$out/boundary.yaml" --output "$out/boundary"
