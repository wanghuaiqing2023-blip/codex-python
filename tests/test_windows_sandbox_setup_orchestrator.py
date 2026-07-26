from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.windows_sandbox import setup
from pycodex.windows_sandbox.setup import ElevationPayload
from pycodex.windows_sandbox.setup_error import SetupErrorCode, SetupErrorReport, SetupFailure, write_setup_error_report


def _payload(home: Path) -> ElevationPayload:
    return ElevationPayload(5, "offline", "online", home, home, (), (), (), (), (), False, "user", False)


def test_orchestrator_passes_serialized_payload_to_helper(tmp_path: Path, monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(
        encoded: str,
        *,
        needs_elevation: bool,
        codex_home: Path,
    ) -> int:
        observed["encoded"] = encoded
        observed["needs_elevation"] = needs_elevation
        observed["codex_home"] = codex_home
        return 0

    monkeypatch.setattr(setup, "_run_helper_process", fake_run)
    setup.run_setup_exe(_payload(tmp_path), needs_elevation=True, codex_home=tmp_path)
    assert observed["needs_elevation"] is True
    assert observed["codex_home"] == tmp_path
    assert isinstance(observed["encoded"], str)


def test_orchestrator_restores_structured_helper_failure(tmp_path: Path, monkeypatch) -> None:
    def fake_run(
        _encoded: str,
        *,
        needs_elevation: bool,
        codex_home: Path,
    ) -> int:
        write_setup_error_report(
            tmp_path,
            SetupErrorReport(SetupErrorCode.HELPER_FIREWALL_RULE_VERIFY_FAILED, "scope mismatch"),
        )
        return 1

    monkeypatch.setattr(setup, "_run_helper_process", fake_run)
    with pytest.raises(SetupFailure) as raised:
        setup.run_setup_exe(_payload(tmp_path), needs_elevation=False, codex_home=tmp_path)
    assert raised.value.code is SetupErrorCode.HELPER_FIREWALL_RULE_VERIFY_FAILED
    assert raised.value.message == "scope mismatch"


def test_setup_process_uses_materialized_current_executable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observed: list[object] = []

    class Completed:
        returncode = 0

    def fake_run(command, **kwargs):
        observed.extend((command, kwargs))
        return Completed()

    monkeypatch.setattr(setup.subprocess, "run", fake_run)

    assert (
        setup._run_helper_process(
            "payload",
            needs_elevation=False,
            codex_home=tmp_path,
        )
        == 0
    )
    assert observed[0][0] == str(Path(setup.sys.executable))
    assert observed[0][1:4] == [
        "-m",
        "pycodex.windows_sandbox.bin.setup_main",
        "payload",
    ]
