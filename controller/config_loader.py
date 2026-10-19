"""크기, alias, 중복 키를 제한하는 YAML 로더."""

from pathlib import Path
import yaml
from jsonschema import Draft202012Validator
from .errors import LabError

ROOT = Path(__file__).resolve().parents[1]


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise LabError("E_KEY_TYPE", "YAML key는 문자열이어야 합니다.")
        if key in result:
            raise LabError("E_DUPLICATE_KEY", key)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_yaml(path: Path):
    try:
        with path.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise LabError("E_CONFIG_SIZE", "설정은 64 KiB 이하이어야 합니다.")
        text = raw.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)):
                raise LabError("E_YAML_ALIAS", "alias/anchor는 지원하지 않습니다.")
        return yaml.load(text, Loader=UniqueLoader)
    except (UnicodeError, yaml.YAMLError, RecursionError, ValueError) as exc:
        raise LabError("E_YAML", "올바른 UTF-8 YAML이 아닙니다.") from exc
    except OSError as exc:
        raise LabError("E_CONFIG_IO", str(exc)) from exc


def validate_schema(data, schema_name="pws.schema.json"):
    import json

    schema = json.loads((ROOT / "configs" / schema_name).read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: str(list(e.path)))
    if errors:
        first = errors[0]
        location = ".".join(map(str, first.path)) or "$"
        raise LabError(
            "E_SCHEMA", f"{location}: {first.validator} 조건을 만족하지 않습니다. 요구값={first.validator_value}"
        )
    return data


def load_config(path: Path):
    return validate_schema(load_yaml(path))
