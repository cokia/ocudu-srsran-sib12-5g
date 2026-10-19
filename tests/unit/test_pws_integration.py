import configparser
import json
from pathlib import Path

import pytest

from controller import cb_data, pws_integration as pws
from controller.config_loader import load_yaml
from controller.errors import LabError


def lines(text, identifier=4372):
    payload = cb_data.encode(text, padding="ocudu-zero")
    chunks = [payload[:84]]
    if len(payload) > 84:
        rest = payload[84:]
        rest += bytes((-len(rest)) % 85)
        chunks += [rest[i : i + 85] for i in range(0, len(rest), 85)]
    return [
        f"LAB_SIB8 id={identifier} serial=0 segment={i} last={int(i == len(chunks) - 1)} "
        f"dcs={'48' if i == 0 else 'none'} payload={chunk.hex()}"
        for i, chunk in enumerate(chunks)
    ]


@pytest.mark.parametrize("text", ["[시험] 한글", "[TEST] English", "가" * 42, "나" * 615])
def test_reassemble_out_of_order_and_repeated_segments(text):
    segments = lines(text)
    result = pws.recovered("\n".join(reversed(segments)) + "\n" + segments[0], 4372)
    assert result["text"] == text
    assert result["payload_hex"] == cb_data.encode(text, padding="ocudu-zero").hex()


def test_incomplete_reception_is_pending():
    assert pws.recovered("\n".join(lines("가" * 100)[:-1]), 4372) is None
    assert pws.recovered("SIB1 acquired successfully", 4372) is None


@pytest.mark.parametrize(
    "before,after,code",
    [
        ("id=4372", "id=4380", "E_SIB8_METADATA"),
        ("serial=0", "serial=1", "E_SIB8_METADATA"),
        ("segment=0", "segment=64", "E_SIB8_METADATA"),
        ("dcs=48", "dcs=00", "E_SIB8_DCS"),
        ("payload=", "payload=f", "E_SIB8_METADATA"),
    ],
)
def test_invalid_received_metadata(before, after, code):
    with pytest.raises(LabError, match=code):
        pws.recovered(lines("한글")[0].replace(before, after), 4372)


def test_conflicting_duplicate_is_not_accepted():
    item = lines("한글")[0]
    with pytest.raises(LabError, match="E_SIB8_CONFLICT"):
        pws.recovered(item + "\n" + item.replace("d55c", "d55d"), 4372)


def test_bad_segment_padding():
    items = lines("가" * 42)
    items[-1] = items[-1][:-2] + "01"
    with pytest.raises(LabError, match="E_SIB8_PADDING"):
        pws.recovered("\n".join(items), 4372)


@pytest.mark.parametrize("profile,identifier", [("monthly-test", 4380), ("korean-safety", 4372)])
def test_prepare_reuses_actual_ocudu_options(config, tmp_path, profile, identifier):
    path, message = pws.prepare(config, profile, "zmq", tmp_path)
    gnb = load_yaml(path)
    assert gnb["cell_cfg"]["sib"]["cmas"]["test"] == {
        "message_id": identifier,
        "serial_num": 0,
        "data_coding_scheme": 72,
        "warning_message": message.text,
    }
    assert gnb["cu_cp"]["amf"]["no_core"] is True
    assert gnb["ru_sdr"]["device_driver"] == "zmq"
    assert gnb["ru_sdr"]["tx_gain"] == 0
    first = path.read_bytes()
    pws.prepare(config, profile, "zmq", tmp_path)
    assert path.read_bytes() == first


def test_hardware_template_does_not_enable_rf(config, tmp_path):
    path, _ = pws.prepare(config, "korean-safety", "bladerf-x40", tmp_path, "a" * 32)
    radio = load_yaml(path)["ru_sdr"]
    assert radio["device_driver"] == "bladerf_x40"
    assert "rf=off" in radio["device_args"]
    assert radio["tx_gain"] == 17


def test_no_implicit_hardware_receive(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["pws", "receive", "--backend", "bladerf-x40", "--output", str(tmp_path)])
    assert pws.main() == 3
    report = json.loads((tmp_path / "pws-integration.json").read_text())
    assert report["result"] == "BLOCKED"
    assert not (tmp_path / "gnb.log").exists()


def test_test_label_is_required(config, tmp_path):
    config["pws"]["message"]["text"] = "잘못된 문구"
    with pytest.raises(LabError, match="E_TEST_LABEL"):
        pws.prepare(config, "monthly-test", "zmq", tmp_path)


def test_padding_profiles_remain_distinct():
    encoded = cb_data.encode("한글", padding="ocudu-zero")
    assert encoded == bytes.fromhex("01d55cae00" + "0000" * 39 + "04")
    assert cb_data.decode(encoded, padding="ocudu-zero") == "한글"
    with pytest.raises(LabError, match="E_CB_PADDING"):
        cb_data.decode(encoded)
    with pytest.raises(LabError, match="E_CB_PROFILE"):
        cb_data.encode("A", padding="unknown")


@pytest.mark.parametrize("plmn", ["45005", "45008", "45006", "00101"])
@pytest.mark.parametrize("backend", ["zmq", "bladerf-x40"])
def test_plmn_is_consistent_in_cell_tracking_area_and_test_usim(config, tmp_path, plmn, backend):
    path, _ = pws.prepare(config, "korean-safety", backend, tmp_path, "a" * 32, plmn)
    gnb = load_yaml(path)
    assert gnb["cell_cfg"]["plmn"] == plmn
    assert gnb["cu_cp"]["amf"]["supported_tracking_areas"][0]["plmn_list"][0]["plmn"] == plmn
    if backend == "zmq":
        ue = configparser.ConfigParser()
        ue.read(tmp_path / "srsue.pws.conf")
        assert ue["usim"]["imsi"] == plmn + "0123456780"
        assert ue["log"]["rrc_level"] == "debug"
        assert ue["rf"]["device_name"] == "zmq"
        before = (tmp_path / "srsue.pws.conf").read_bytes()
        pws.prepare(config, "korean-safety", backend, tmp_path, "a" * 32, plmn)
        assert (tmp_path / "srsue.pws.conf").read_bytes() == before
    else:
        assert "rf=off" in gnb["ru_sdr"]["device_args"]


def test_default_plmn_is_korean(config, tmp_path):
    path, _ = pws.prepare(config, "korean-safety", "zmq", tmp_path)
    assert load_yaml(path)["cell_cfg"]["plmn"] == "45005"


@pytest.mark.parametrize("plmn", [45005, "4505", "450005", "45099", "45005,00101", "", None])
def test_invalid_plmn_is_rejected_before_output(config, tmp_path, plmn):
    with pytest.raises(LabError, match="E_PLMN"):
        pws.prepare(config, "korean-safety", "zmq", tmp_path, plmn=plmn)
    assert not (tmp_path / "gnb.pws.yaml").exists()


def sib1_log(mcc=(4, 5, 0), mnc=(0, 5)):
    # pinned srsUE BCCH-DL-SCH-Message::to_json의 수신 구조.
    return "[RRC-NR ] [D] Content:" + json.dumps(
        [
            {
                "BCCH-DL-SCH-Message": {
                    "message": {
                        "c1": {
                            "systemInformationBlockType1": {
                                "cellAccessRelatedInfo": {
                                    "plmn-IdentityList": [{"plmn-IdentityList": [{"mcc": mcc, "mnc": mnc}]}]
                                }
                            }
                        }
                    }
                }
            }
        ]
    )


@pytest.mark.parametrize("mnc", [5, 6, 8])
def test_received_sib1_preserves_two_digit_mnc(mnc):
    plmn = f"4500{mnc}"
    assert pws.received_plmn(sib1_log(mnc=(0, mnc)), plmn) == plmn


def test_wrong_or_changing_received_plmn_is_rejected():
    with pytest.raises(LabError, match="E_PLMN_RX"):
        pws.received_plmn(sib1_log(), "45008")
    with pytest.raises(LabError, match="E_PLMN_RX"):
        pws.received_plmn(sib1_log() + "\n" + sib1_log(mnc=(0, 8)), "45005")


@pytest.mark.parametrize("mnc", [[5], [0, 0, 5], [False, 5], [0, 10], "05"])
def test_invalid_received_mnc_is_not_success(mnc):
    with pytest.raises(LabError, match="E_PLMN_RX"):
        pws.received_plmn(sib1_log(mnc=mnc), "45005")


@pytest.mark.parametrize("log", ["", "SIB1 acquired successfully PLMN=45005", sib1_log().split('"mnc"')[0]])
def test_plmn_requires_complete_received_asn1_json(log):
    assert pws.received_plmn(log, "45005") is None


def test_actual_srsue_sib1_log_with_malformed_non_identity_json():
    log = (Path(__file__).parents[1] / "fixtures/srsue-sib1-45005.txt").read_text()
    with pytest.raises(json.JSONDecodeError):
        json.loads(log.split("Content:", 1)[1])
    assert pws.received_plmn(log, "45005") == "45005"
    with pytest.raises(LabError, match="E_PLMN_RX"):
        pws.received_plmn(log, "45008")
