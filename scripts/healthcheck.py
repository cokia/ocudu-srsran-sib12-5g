#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

try:
    state = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "output/non-sdr/gnb.health.json").read_text())
    if state["status"] != "STARTED":
        raise ValueError("not running")
    os.kill(state["pid"], 0)
except (OSError, ValueError, KeyError):
    raise SystemExit(1)
