from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.windows_sandbox.setup import ElevationPayload
from pycodex.windows_sandbox.setup_error import SetupErrorCode, SetupErrorReport, SetupFailure, write_setup_error_report
from pycodex.windows_sandbox import setup_orchestrator


def _payload(home: Path) -> ElevationPayload:
    return ElevationPayload(5, "offline", "online", home, home, (), (), (), (), (), False, "user", False)


def test_orchestrator_passes_serialized_payload_to_helper(tmp_path: Path, monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(encoded: str, *, elevate: bool) -> int:
        observed["encoded"] = encoded
        observed["elevate"] = elevate
        return 0

    monkeypatch.setattr(setup_orchestrator, "_run_helper_process", fake_run)
    setup_orchestrator.run_setup_helper(_payload(tmp_path), elevate=True)
    assert observed["elevate"] is True
    assert isinstance(observed["encoded"], str)


def test_orchestrator_restores_structured_helper_failure(tmp_path: Path, monkeypatch) -> None:
    def fake_run(_encoded: str, *, elevate: bool) -> int:
        write_setup_error_report(
            tmp_path,
            SetupErrorReport(SetupErrorCode.HELPER_FIREWALL_RULE_VERIFY_FAILED, "scope mismatch"),
        )
        return 1

    monkeypatch.setattr(setup_orchestrator, "_run_helper_process", fake_run)
    with pytest.raises(SetupFailure) as raised:
        setup_orchestrator.run_setup_helper(_payload(tmp_path), elevate=False)
    assert raised.value.code is SetupErrorCode.HELPER_FIREWALL_RULE_VERIFY_FAILED
    assert raised.value.message == "scope mismatch"
