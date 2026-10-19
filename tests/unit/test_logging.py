import json
from controller.logging import emit


def test_json_log_threshold(capsys):
    emit("quiet", "warning", "info")
    assert capsys.readouterr().err == ""
    emit("details", "debug", "debug", bytes=82)
    assert json.loads(capsys.readouterr().err) == {"event": "details", "level": "debug", "bytes": 82}
