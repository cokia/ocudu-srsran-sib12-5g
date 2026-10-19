import configparser
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from controller import cb_data, lte_sib12 as lte
from controller.errors import LabError


def lines(text, identifier=4372):
    payload = cb_data.encode(text, padding="ocudu-zero")
    chunks = [payload[i : i + 100] for i in range(0, len(payload), 100)]
    return [
        f"LAB_LTE_SIB12 id={identifier} serial=0 segment={i} last={int(i == len(chunks) - 1)} "
        f"dcs={'48' if i == 0 else 'none'} payload={chunk.hex()}\n"
        for i, chunk in enumerate(chunks)
    ]


@pytest.mark.parametrize(
    "text,count", [("[시험] 한글", 1), ("[TEST] English", 1), ("가" * 41, 1), ("가" * 42, 2), ("나" * 615, 13)]
)
def test_reassembles_actual_lte_segmentation_with_duplicates_and_reordering(text, count):
    segments = lines(text)
    result = lte.recovered("".join(reversed(segments)) + segments[0], 4372)
    assert result == {"text": text, "segments": count, "payload_hex": cb_data.encode(text, padding="ocudu-zero").hex()}


@pytest.mark.parametrize(
    "before,after,code",
    [
        ("id=4372", "id=4380", "E_LTE_METADATA"),
        ("serial=0", "serial=1", "E_LTE_METADATA"),
        ("segment=0", "segment=64", "E_LTE_METADATA"),
        ("dcs=48", "dcs=00", "E_LTE_DCS"),
        ("payload=", "payload=f", "E_LTE_METADATA"),
    ],
)
def test_rejects_received_metadata_mismatch(before, after, code):
    with pytest.raises(LabError, match=code):
        lte.recovered(lines("한글")[0].replace(before, after), 4372)


def test_incomplete_logs_are_pending():
    segments = lines("가" * 615)
    assert lte.recovered("".join(segments[:-1]), 4372) is None
    assert lte.recovered(segments[-1], 4372) is None
    assert lte.recovered(segments[0][:-1], 4372) is None
    assert lte.recovered("SIB12 received", 4372) is None


def test_rejects_conflicting_duplicates():
    item = lines("한글")[0]
    with pytest.raises(LabError, match="E_LTE_CONFLICT"):
        lte.recovered(item + item.replace("d55c", "d55d"), 4372)


def test_rejects_multiple_last_segments():
    segments = lines("가" * 615)
    segments[0] = segments[0].replace("last=0", "last=1")
    with pytest.raises(LabError, match="E_LTE_LAST"):
        lte.recovered("".join(segments), 4372)


def test_rejects_trailing_segments():
    segments = lines("가" * 615)
    segments[-1] = segments[-1].replace("last=1", "last=0")
    # 마지막이 아닌 짧은 segment도 실패한다.
    with pytest.raises(LabError, match="E_LTE_SIZE"):
        lte.recovered("".join(segments), 4372)


def test_rejects_wrong_cb_padding():
    item = lines("한글")[0].replace("000004\n", "000104\n")
    with pytest.raises(LabError, match="E_CB_PADDING"):
        lte.recovered(item, 4372)


@pytest.mark.parametrize("plmn", ["45005", "45008", "45006", "00101"])
@pytest.mark.parametrize("profile,identifier", [("korean-safety", 4372), ("monthly-test", 4380)])
def test_generated_profiles_are_consistent_and_deterministic(config, tmp_path, plmn, profile, identifier):
    config["pws"]["message"]["text"] = '[시험] 한글 "따옴표" \\ 개행\n두 번째 줄\t탭\r'
    path, message = lte.prepare(config, profile, tmp_path, plmn)
    enb, ue = configparser.ConfigParser(), configparser.ConfigParser()
    enb.read(path)
    ue.read(tmp_path / "ue.conf")
    assert enb["enb"]["mcc"] + enb["enb"]["mnc"] == plmn
    assert ue["usim"]["imsi"] == plmn + "0123456780"
    assert ue["rat.nr"]["nof_carriers"] == "0"
    assert enb["rf"]["device_name"] == ue["rf"]["device_name"] == "zmq"
    sib = (tmp_path / "sib.conf").read_text()
    assert f"message_id = {identifier};" in sib
    assert json.dumps(message.text, ensure_ascii=False) in sib
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    lte.prepare(config, profile, tmp_path, plmn)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize(
    "text,code",
    [("", "E_SCHEMA"), ("경고", "E_TEST_LABEL"), ("[시험] 😀", "E_ENCODING"), ("[시험] " + "가" * 611, "E_SCHEMA")],
)
def test_rejects_bad_input_before_config_write(config, tmp_path, text, code):
    config["pws"]["message"]["text"] = text
    with pytest.raises(LabError, match=code):
        lte.prepare(config, "korean-safety", tmp_path)
    assert not (tmp_path / "enb.conf").exists()


def test_rejects_unsupported_plmn(config, tmp_path):
    with pytest.raises(LabError, match="E_LTE_PROFILE"):
        lte.prepare(config, "korean-safety", tmp_path, "45099")


def test_plmn_requires_received_sib1_record():
    assert lte.received_plmn("requested=45005\n", "45005") is None
    assert lte.received_plmn("LAB_LTE_SIB1 plmn=45005", "45005") is None
    assert lte.received_plmn("LAB_LTE_SIB1 plmn=45005\n" * 2, "45005") == "45005"
    with pytest.raises(LabError, match="E_LTE_PLMN"):
        lte.received_plmn("LAB_LTE_SIB1 plmn=45008\n", "45005")


def test_nonisolated_network_cannot_start_processes(monkeypatch, tmp_path):
    original = Path.iterdir
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(
        Path,
        "iterdir",
        lambda self: iter([Path("lo"), Path("eth0")]) if str(self) == "/sys/class/net" else original(self),
    )
    with pytest.raises(LabError, match="E_NETWORK_ISOLATION"):
        lte.receive(SimpleNamespace(output=tmp_path), tmp_path / "enb.conf", None)


def test_cli_prepare_report_does_not_claim_reception(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["lte", "prepare", "--output", str(tmp_path)])
    assert lte.main() == 0
    report = json.loads((tmp_path / "lte-sib12.json").read_text())
    assert report["rat"] == "LTE" and report["ocudu_used"] is False
    assert report["details"]["reception"] == "NOT VERIFIED"
    assert report["srsran4g_commit"] == "6bcbd9e5bf8686aa7085202cd847c5ddd64a9c16"


def test_actual_srsue_lte_log_fixture():
    log = (Path(__file__).parents[1] / "fixtures/srsue-lte-sib12-45005.txt").read_text()
    assert lte.received_plmn(log, "45005") == "45005"
    assert lte.recovered(log, 4372)["text"] == "[시험 데이터] PWS 프로토콜 검증 메시지입니다."
