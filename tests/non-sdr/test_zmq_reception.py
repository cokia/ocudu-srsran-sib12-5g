from pathlib import Path
import json
import pytest
from controller.errors import LabError
from controller import zmq_rx

MIB = "Cell search found ARFCN=0 PCI=1 epre=-11.2 snr=+78.8 sfn=11 ssb_idx=0 hrf=n scs=15 ssb_offset=6 dmrs_typeA_pos=pos2 coreset0=12 ss0=0 barred=n"


def test_zmq_profile_pins():
    zmq_rx.validate_profiles()


def test_reject_external_endpoint(tmp_path, monkeypatch):
    configs = tmp_path / "configs"
    configs.mkdir()
    for name in zmq_rx.PROFILES:
        (configs / name).write_bytes((zmq_rx.ROOT / "configs" / name).read_bytes())
    path = configs / "gnb.zmq.yaml"
    path.write_text(path.read_text().replace("127.0.0.1:2000", "0.0.0.0:2000"))
    monkeypatch.setattr(zmq_rx, "ROOT", Path(tmp_path))
    with pytest.raises(LabError, match="E_ZMQ_PROFILE"):
        zmq_rx.validate_profiles()


@pytest.mark.parametrize("ue", ["", "RRC Connected", "SIB1 received, CellID=1", "Cell search found ARFCN=368410 PCI=2"])
def test_incomplete_reception_is_not_success(ue):
    found = zmq_rx.evidence("gNB started", ue)
    assert not all(found[k] for k in ("mib_decoded", "sib1_received", "sib1_acquired"))


@pytest.mark.parametrize("arfcn", ["0", "368410"])
def test_actual_source_markers(arfcn):
    found = zmq_rx.evidence(
        "==== gNB started ===",
        "\n".join(
            [
                MIB.replace("ARFCN=0", f"ARFCN={arfcn}"),
                "PHY configuration with MIB parameters completed.",
                "[RRC-NR] SIB1 received, CellID=1",
                "[RRC-NR] SIB1 acquired successfully",
            ]
        ),
    )
    assert found["gnb_started"] and found["mib_decoded"] and found["sib1_received"] and found["sib1_acquired"]
    assert not found["rrc_connected"]
    assert not zmq_rx.ready_to_stop(found)


def test_received_and_released_ue_can_stop():
    found = zmq_rx.evidence(
        'gNB started\nue=0: "UE Removal Routine" finished successfully',
        MIB + "\nPHY configuration with MIB parameters completed.\nSIB1 received, CellID=4095\n"
        "SIB1 acquired successfully\nRRC Connected\nReceived RRC Release",
    )
    assert zmq_rx.ready_to_stop(found)


def test_other_pci_does_not_match_prefix():
    assert not zmq_rx.evidence(
        "gNB started", MIB.replace("PCI=1", "PCI=10") + "\nPHY configuration with MIB parameters completed."
    )["mib_decoded"]


@pytest.mark.parametrize("before,after", [("scs=15", "scs=30"), ("coreset0=12", "coreset0=1")])
def test_wrong_mib_profile_is_rejected(before, after):
    assert not zmq_rx.evidence(
        "gNB started", MIB.replace(before, after) + "\nPHY configuration with MIB parameters completed."
    )["mib_decoded"]


def test_preflight_failure_does_not_reuse_old_reception(tmp_path, monkeypatch):
    (tmp_path / "srsue.log").write_text("Cell search found ARFCN=368410 PCI=1\nSIB1 acquired successfully")
    (tmp_path / "gnb.log").write_text("gNB started")
    monkeypatch.setattr("sys.argv", ["zmq-rx", "--output", str(tmp_path)])

    def reject():
        raise LabError("E_ZMQ_PROFILE", "변경된 설정")

    monkeypatch.setattr(zmq_rx, "validate_profiles", reject)
    assert zmq_rx.main() != 0
    result = json.loads((tmp_path / "zmq-rx.json").read_text())
    assert result["result"] == "FAIL"
    assert not result["details"]["mib_decoded"]
    assert not result["details"]["gnb_started"]
