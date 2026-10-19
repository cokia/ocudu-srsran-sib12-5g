import json
import subprocess
import pytest
from controller import cb_data
from controller.errors import LabError

pytestmark = pytest.mark.codec


@pytest.mark.parametrize("text", ["[TEST] offline", "[시험] 방송 없는 프로토콜 검증", "가" * 615])
@pytest.mark.parametrize("size", [20, 128, 256])
def test_actual_upstream_roundtrip(codec, text, size):
    body = cb_data.encode(text)
    one = codec.encode(body, size)
    two = codec.encode(body, size)
    assert one == two
    assert cb_data.decode(bytes.fromhex(codec.decode(one["segments"])["payload_hex"])) == text
    for i, structure in enumerate(one["structures"]):
        assert structure["warningMessageSegmentNumber"] == i
        assert ("dataCodingScheme" in structure) == (i == 0)


def test_upstream_against_independent_uper(codec):
    # SIB8 UPER: 4 presence bits, 16+16 identifiers, 1 last, 6 index,
    # 8-bit length (84), CB Data, DCS. ASN.1 length <128 fixture.
    body = cb_data.encode("A")
    bits = "0100" + format(0x111C, "016b") + "0" * 16 + "1" + "0" * 6
    bits += format(len(body), "08b") + "".join(format(b, "08b") for b in body) + "01001000"
    bits += "0" * (-len(bits) % 8)
    expected = int(bits, 2).to_bytes(len(bits) // 8, "big").hex()
    assert codec.encode(body)["segments"] == [expected]
    assert bytes.fromhex(codec.decode([expected])["payload_hex"]) == body


@pytest.mark.parametrize("mutation", ["truncated", "trailing", "padding", "reordered", "duplicate", "badhex", "empty"])
def test_malformed_uper(codec, mutation):
    segments = codec.encode(cb_data.encode("가" * 150))["segments"]
    if mutation == "truncated":
        segments[-1] = segments[-1][:-2]
    elif mutation == "trailing":
        segments[-1] += "00"
    elif mutation == "padding":
        last = bytearray.fromhex(segments[-1])
        last[-1] |= 1
        segments[-1] = last.hex()
    elif mutation == "reordered":
        segments.reverse()
    elif mutation == "duplicate":
        segments.insert(1, segments[0])
    elif mutation == "badhex":
        segments[0] = "zz"
    else:
        segments = []
    with pytest.raises(LabError):
        codec.decode(segments)


def test_codec_input_limit(codec):
    run = subprocess.run([codec.executable], input=" " * 65537, capture_output=True, text=True, timeout=10)
    assert run.returncode != 0
    assert json.loads(run.stdout)["error"] == "E_INPUT_SIZE"


def test_nr_sib12_is_not_cmas(codec):
    result = codec.inspect_sib12()
    assert result["cmas"] is False
    assert result["asn1_type"] == "NR-SIB12-r16"
    assert result["structure"]["segmentNumber-r16"] == 0
