import os
from pathlib import Path
import pytest
from controller.config_loader import load_config
from controller.protocol import OfflineCodec

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return load_config(ROOT / "configs/pws.example.yaml")


@pytest.fixture
def codec():
    path = Path(os.environ.get("PWS_CODEC", str(ROOT / "build/bin/pws-codec")))
    if not path.is_file():
        if os.environ.get("LAB_REQUIRE_CODEC") == "1":
            pytest.fail(f"codec build 필요: {path}")
        pytest.skip("OCUDU codec 미빌드")
    return OfflineCodec(path)


@pytest.fixture
def diagnostic():
    path = Path(os.environ.get("BLADERF_DIAG", str(ROOT / "build/bin/bladerf-x40-diag")))
    if not path.is_file():
        if os.environ.get("LAB_REQUIRE_DIAG") == "1":
            pytest.fail(f"진단 executable build 필요: {path}")
        pytest.skip("진단 executable 미빌드")
    return str(path)
