import copy
import pytest
from controller.config_loader import load_config, validate_schema
from controller.errors import LabError
from controller.message_model import LaboratoryMessage


@pytest.mark.parametrize("value", [None, [], "test", 1, True])
def test_invalid_root(value):
    with pytest.raises(LabError, match="E_SCHEMA"):
        validate_schema(value)


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_version",), 2),
        (("schema_version",), True),
        (("radio", "rf_transmission_enabled"), True),
        (("radio", "rf_transmission_enabled"), "false"),
        (("radio", "backend"), "bladerf"),
        (("application", "mode"), "production"),
        (("pws", "message", "text"), ""),
        (("pws", "message", "text"), "가" * 616),
        (("pws", "message", "metadata", "category"), "REAL"),
        (("pws", "message", "metadata", "description"), 42),
        (("pws", "message", "profile"), "ACTUAL"),
        (("pws", "validation", "strict"), False),
        (("pws", "output", "audit_log"), False),
        (("pws", "enabled"), False),
    ],
)
def test_invalid_fields(config, path, value):
    node = config
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(LabError, match="E_SCHEMA"):
        validate_schema(config)


def test_missing_and_unknown_fields(config):
    for group in [config, config["radio"], config["pws"]["message"]["metadata"]]:
        group["unrecognized"] = 1
        with pytest.raises(LabError):
            validate_schema(config)
        del group["unrecognized"]
    del config["pws"]["message"]["id"]
    with pytest.raises(LabError):
        validate_schema(config)


@pytest.mark.parametrize(
    "raw,code",
    [
        (b"a: 1\na: 2\n", "E_DUPLICATE_KEY"),
        (b"a: &a [1]\nb: *a", "E_YAML_ALIAS"),
        (b"\xff", "E_YAML"),
        (b"1: x", "E_KEY_TYPE"),
        (b"x" * 65537, "E_CONFIG_SIZE"),
        (b"!!python/object:os.system {}", "E_YAML"),
    ],
)
def test_yaml_loader_rejects(tmp_path, raw, code):
    path = tmp_path / "invalid.yaml"
    path.write_bytes(raw)
    with pytest.raises(LabError, match=code):
        load_config(path)


@pytest.mark.parametrize("text", [" ", "\x00", "😀", "\ud800"])
def test_invalid_message(config, text):
    config["pws"]["message"]["text"] = text
    with pytest.raises(LabError):
        LaboratoryMessage.from_config(config)


def test_modes_share_message(config):
    other = copy.deepcopy(config)
    other["application"]["mode"] = "sdr-bladerf-x40"
    assert LaboratoryMessage.from_config(config) == LaboratoryMessage.from_config(validate_schema(other))
