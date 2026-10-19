"""TS 23.041 §9.3.51/§9.4.2.2.5 및 TS 23.038 UCS-2 CB Data."""

from .errors import LabError

PAGE_BYTES = 82
MAX_PAGES = 15


def encode(text: str) -> bytes:
    if not text or any(ord(c) > 0xFFFF or 0xD800 <= ord(c) <= 0xDFFF for c in text):
        raise LabError("E_ENCODING", "비어 있지 않은 UCS-2 BMP 문자열이 필요합니다.")
    raw = text.encode("utf-16-be")
    if len(raw) > PAGE_BYTES * MAX_PAGES:
        raise LabError("E_LENGTH", "최대 615 UCS-2 문자입니다.")
    chunks = [raw[i : i + PAGE_BYTES] for i in range(0, len(raw), PAGE_BYTES)]
    return bytes([len(chunks)]) + b"".join(
        c + b"\x00\r" * ((PAGE_BYTES - len(c)) // 2) + bytes([len(c)]) for c in chunks
    )


def decode(data: bytes) -> str:
    if not data or not 1 <= data[0] <= MAX_PAGES or len(data) != 1 + data[0] * 83:
        raise LabError("E_CB_LENGTH", "CB Data page 수 또는 길이가 잘못되었습니다.")
    raw = bytearray()
    for i in range(data[0]):
        page = data[1 + i * 83 : 1 + (i + 1) * 83]
        size = page[-1]
        if not 2 <= size <= 82 or size % 2 or (i + 1 < data[0] and size != 82):
            raise LabError("E_CB_PAGE", "비정규 page 길이입니다.")
        if page[size:82] != b"\x00\r" * ((82 - size) // 2):
            raise LabError("E_CB_PADDING", "UCS-2 CR padding이 잘못되었습니다.")
        raw.extend(page[:size])
    try:
        text = bytes(raw).decode("utf-16-be")
        if any(ord(c) > 0xFFFF for c in text):
            raise UnicodeError("non-BMP")
        return text
    except UnicodeError as exc:
        raise LabError("E_ENCODING", "잘못된 UCS-2 데이터입니다.") from exc
