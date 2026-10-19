#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts/radio-plugin
export LD_LIBRARY_PATH="$PWD/build/radio-plugin:$PWD/build/deps/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
timeout --kill-after=5s 25s build/radio-plugin/radio-plugin-tests --gtest_output=xml:artifacts/radio-plugin/plugin.xml
timeout --kill-after=5s 25s build/radio-plugin/radio-usb-tests --gtest_output=xml:artifacts/radio-plugin/usb.xml
if [[ "${1:-}" == --gnb ]]; then
  exec "${LAB_PYTHON:-.venv/bin/python}" -m controller.radio_smoke --output artifacts/radio-plugin/gnb
fi
