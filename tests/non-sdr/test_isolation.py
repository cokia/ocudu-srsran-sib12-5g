import pytest
import yaml
from controller.config_loader import ROOT
from controller.errors import LabError
from controller.gnb import validate_gnb


def test_fixed_dummy_profile():
    cfg = validate_gnb(ROOT / "configs/gnb.non-sdr.yaml")
    assert cfg["cu_cp"]["amf"]["no_core"] is True
    assert "ru_sdr" not in cfg


def test_rejects_rf_profile(tmp_path):
    cfg = yaml.safe_load((ROOT / "configs/gnb.non-sdr.yaml").read_text())
    cfg["ru_sdr"] = {"device_driver": "bladerf"}
    path = tmp_path / "rf.yaml"
    path.write_text(yaml.safe_dump(cfg))
    with pytest.raises(LabError):
        validate_gnb(path)
