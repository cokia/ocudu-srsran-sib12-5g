import pytest
from controller.config_loader import ROOT, load_yaml, validate_schema
from controller.errors import LabError


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("device", "rf_transmission_enabled", True),
        ("device", "model", "bladerf2"),
        ("diagnostics", "loopback_mode", "rf_lna1"),
        ("diagnostics", "sample_rate", 40000000),
        ("diagnostics", "payload", "PWS"),
    ],
)
def test_diagnostic_config_is_closed(section, key, value):
    data = load_yaml(ROOT / "configs/bladerf-x40.yaml")
    data[section][key] = value
    with pytest.raises(LabError):
        validate_schema(data, "bladerf-x40.schema.json")
