"""실제 임시 Git 저장소에서 고정 patch 적용과 사용자 변경 보존을 검사한다."""

import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import pytest


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "fetch_upstream", Path(__file__).resolve().parents[2] / "scripts/fetch-upstream.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dest = tmp_path / "upstream/ocudu"
    dest.mkdir(parents=True)
    (tmp_path / "controller/offline_codec").mkdir(parents=True)
    before, after = "original\n", "patched\n"
    (dest / "worker.cpp").write_text(before)
    (dest / "other.cpp").write_text("user base\n")
    for args in (
        ["init", "-q"],
        ["add", "."],
        ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
    ):
        subprocess.run(["git", "-C", str(dest), *args], check=True)
    revision = subprocess.check_output(["git", "-C", str(dest), "rev-parse", "HEAD"], text=True).strip()
    patch = tmp_path / "fix.patch"
    patch.write_text(
        "".join(
            difflib.unified_diff(
                before.splitlines(True), after.splitlines(True), fromfile="a/worker.cpp", tofile="b/worker.cpp"
            )
        )
    )
    item = {
        "file": "fix.patch",
        "source": "worker.cpp",
        "original_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "patched_sha256": hashlib.sha256(after.encode()).hexdigest(),
        "sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
    }
    (tmp_path / "dependencies.lock.json").write_text(json.dumps({"ocudu": {"commit": revision, "patches": [item]}}))
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["fetch-upstream.py", "ocudu"])
    return module, dest, patch


def test_patch_is_idempotent(checkout, capsys):
    module, dest, _ = checkout
    module.main()
    module.main()
    assert (dest / "worker.cpp").read_text() == "patched\n"
    revision = json.loads((module.ROOT / "dependencies.lock.json").read_text())["ocudu"]["commit"]
    assert capsys.readouterr().out.splitlines() == [f"ocudu: {revision}"] * 2


@pytest.mark.parametrize("name", ["worker.cpp", "other.cpp"])
def test_user_change_is_preserved(checkout, name):
    module, dest, _ = checkout
    module.main()
    (dest / name).write_text("user change\n")
    with pytest.raises(SystemExit, match="E_UPSTREAM_DIRTY"):
        module.main()
    assert (dest / name).read_text() == "user change\n"


def test_changed_patch_is_rejected_before_application(checkout):
    module, dest, patch = checkout
    patch.write_text(patch.read_text() + "\n")
    with pytest.raises(SystemExit, match="E_PATCH_FILE"):
        module.main()
    assert (dest / "worker.cpp").read_text() == "original\n"
