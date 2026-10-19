import json
import os
from pathlib import Path
import subprocess
from .errors import LabError


class OfflineCodec:
    def __init__(self, executable=None):
        self.executable = str(executable or os.environ.get("PWS_CODEC", "build/bin/pws-codec"))

    def call(self, request):
        try:
            run = subprocess.run(
                [self.executable], input=json.dumps(request), text=True, capture_output=True, timeout=10, check=False
            )
        except FileNotFoundError as exc:
            raise LabError("E_CODEC_MISSING", self.executable, 3) from exc
        except subprocess.TimeoutExpired as exc:
            raise LabError("E_CODEC_TIMEOUT", "10초 제한", 4) from exc
        try:
            result = json.loads(run.stdout)
        except (ValueError, UnicodeError) as exc:
            raise LabError("E_CODEC_OUTPUT", run.stderr[-2048:], 1) from exc
        if run.returncode or result.get("status") != "PASS":
            raise LabError("E_CODEC", result.get("error", "encoder 실패"), 1)
        return result

    def encode(self, payload, segment_bytes=128):
        return self.call({"operation": "encode-sib8", "payload_hex": payload.hex(), "segment_bytes": segment_bytes})

    def decode(self, segments):
        return self.call({"operation": "decode-sib8", "segments": segments})

    def inspect_sib12(self):
        return self.call({"operation": "inspect-sib12"})


def read_encoded(path: Path):
    if path.stat().st_size > 65536:
        raise LabError("E_INPUT_SIZE", "64 KiB 제한")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj["segments"]
    except (ValueError, KeyError) as exc:
        raise LabError("E_INPUT", "segments JSON 배열이 필요합니다.") from exc
