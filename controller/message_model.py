from dataclasses import dataclass
from .errors import LabError


@dataclass(frozen=True)
class LaboratoryMessage:
    id: str
    language: str
    text: str
    category: str
    description: str

    @classmethod
    def from_config(cls, config):
        item = config["pws"]["message"]
        text = item["text"]
        if not text.strip():
            raise LabError("E_EMPTY_TEXT", "공백만 있는 메시지는 허용하지 않습니다.")
        if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
            raise LabError("E_CONTROL_CHARACTER", "지원하지 않는 제어 문자입니다.")
        if any(ord(c) > 0xFFFF or 0xD800 <= ord(c) <= 0xDFFF for c in text):
            raise LabError("E_ENCODING", "UCS-2 BMP 문자만 지원합니다.")
        return cls(item["id"], item["language"], text, **item["metadata"])
