import pytest

from controller.errors import LabError
from controller.radio_smoke import stream_evidence


SUMMARY = "LAB_RADIO_STOP hardware=0 tx_samples=8 rx_samples=8 errors=0 late=0 overflow=0 underflow=0\n"


@pytest.mark.parametrize("code", ["E_USB", "E_RX_CONTINUITY", "E_BUFFER", "E_DURATION"])
def test_fault_after_successful_samples_cannot_pass(code):
    with pytest.raises(LabError, match="E_STREAM_EVIDENCE"):
        stream_evidence(f"bladeRF x40 plugin: {code} driver=-5 fault\n" + SUMMARY)


@pytest.mark.parametrize("counter", ["errors", "late", "overflow", "underflow"])
def test_reported_stream_events_cannot_pass(counter):
    with pytest.raises(LabError, match="E_STREAM_EVIDENCE"):
        stream_evidence(SUMMARY.replace(f"{counter}=0", f"{counter}=1"))


@pytest.mark.parametrize(
    "log",
    [
        "",
        SUMMARY + SUMMARY,
        SUMMARY.replace("hardware=0", "hardware=1"),
        SUMMARY.replace("tx_samples=8", "tx_samples=0"),
        SUMMARY.replace(" errors=0 late=0 overflow=0 underflow=0", ""),
        SUMMARY.replace("late=0", "late=unknown"),
    ],
)
def test_incomplete_or_ambiguous_evidence_cannot_pass(log):
    with pytest.raises(LabError, match="E_STREAM_EVIDENCE"):
        stream_evidence(log)


def test_healthy_summary_contains_samples_and_zero_faults():
    assert stream_evidence(SUMMARY) == {
        "tx_samples": 8,
        "rx_samples": 8,
        "errors": 0,
        "late": 0,
        "overflow": 0,
        "underflow": 0,
    }
