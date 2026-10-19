import pytest
from controller import cb_data
from controller.errors import LabError


@pytest.mark.parametrize(
    "text", ["[TEST] Offline only", "[시험] 한국어 메시지", "가" * 41, "A" * 42, "가" * 615, "A\r", "A\nB"]
)
def test_roundtrip(text):
    assert cb_data.decode(cb_data.encode(text)) == text


def test_independent_cb_golden():
    # TS 23.041 page count + UCS-2 A + 40 CR + length(2).
    expected = bytes.fromhex("010041" + "000d" * 40 + "02")
    assert cb_data.encode("A") == expected
    assert cb_data.decode(expected) == "A"


def test_independent_korean_cb_golden():
    # 한 U+D55C, 글 U+AE00: 한 page, 두 UCS-2 문자와 39개 CR padding.
    expected = bytes.fromhex("01d55cae00" + "000d" * 39 + "04")
    assert cb_data.encode("한글") == expected
    assert cb_data.decode(expected) == "한글"


@pytest.mark.parametrize("text", ["", "A" * 616, "😀", "\ud800"])
def test_encoding_errors(text):
    with pytest.raises(LabError):
        cb_data.encode(text)


@pytest.mark.parametrize("mutation", ["empty", "pages", "truncate", "length", "padding", "surrogate"])
def test_bad_cb_data(mutation):
    raw = bytearray(cb_data.encode("A"))
    if mutation == "empty":
        raw = bytearray()
    elif mutation == "pages":
        raw[0] = 16
    elif mutation == "truncate":
        raw.pop()
    elif mutation == "length":
        raw[-1] = 3
    elif mutation == "padding":
        raw[5] = 1
    else:
        raw[1:3] = b"\xd8\x00"
    with pytest.raises(LabError):
        cb_data.decode(raw)
