from __future__ import annotations

from io import StringIO
from pathlib import Path

from pycodex.windows_sandbox.bin.setup_main import __main__ as setup_main
from pycodex.windows_sandbox.bin.setup_main import win
from pycodex.windows_sandbox.bin.setup_main.win import read_acl_mutex
from pycodex.windows_sandbox.bin.setup_main.win import setup_runtime_bin


def test_setup_binary_main_delegates_to_windows_owner(monkeypatch) -> None:
    called: list[object] = []
    monkeypatch.setattr(
        setup_main,
        "windows_setup_main",
        lambda argv=None: called.append(argv) or 7,
    )

    assert setup_main.main(["payload"]) == 7
    assert called == [["payload"]]


def test_read_acl_mutex_uses_fixed_rust_name() -> None:
    assert read_acl_mutex.READ_ACL_MUTEX_NAME == r"Local\CodexSandboxReadAcl"


def test_setup_runtime_bin_uses_local_app_data_and_records_acl_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_bin = tmp_path / "OpenAI" / "Codex" / "bin"
    runtime_bin.mkdir(parents=True)
    errors: list[str] = []
    log = StringIO()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(
        setup_runtime_bin,
        "path_mask_allows",
        lambda *_args, **_kwargs: False,
    )

    def fail_grant(*_args, **_kwargs):
        raise OSError("denied")

    monkeypatch.setattr(setup_runtime_bin, "ensure_allow_mask_aces", fail_grant)

    setup_runtime_bin.ensure_codex_app_runtime_bin_readable(123, errors, log)

    assert errors == [
        f"grant read/execute ACE failed on {runtime_bin} for sandbox_group: denied"
    ]
    assert "granting read/execute ACE" in log.getvalue()


def test_setup_win_exports_rust_owned_entrypoints() -> None:
    assert callable(win.main)
    assert callable(win.run_setup_payload)
