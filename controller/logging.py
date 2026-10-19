"""stderr JSON event의 최소 log level을 적용한다."""

import sys
from .reporting import canonical

LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}


def emit(event, configured="info", level="info", **details):
    if LEVELS[level] >= LEVELS[configured]:
        print(canonical({"event": event, "level": level, **details}), file=sys.stderr)
