#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${LAB_PYTHON:-.venv/bin/python}" -m controller.pws_integration "$@"
