from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace


def test_audit_owner_and_crate_reexport() -> None:
    import pycodex.windows_sandbox as sandbox
    from pycodex.windows_sandbox import audit

    assert (
        audit.audit_everyone_writable.__module__
        == "pycodex.windows_sandbox.audit"
    )
    assert (
        sandbox.apply_world_writable_scan_and_denies_for_permissions
        is audit.apply_world_writable_scan_and_denies_for_permissions
    )


def test_gather_candidates_splits_path_entries(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from pycodex.windows_sandbox import audit

    tools = tmp_path / "Tools"
    binaries = tmp_path / "Program Files"
    tools.mkdir()
    binaries.mkdir()
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.delenv("PUBLIC", raising=False)
    monkeypatch.setattr(audit, "_SYSTEM_ROOTS", ())

    candidates = audit._gather_candidates(
        tmp_path,
        {"PATH": os.pathsep.join((str(tools), str(binaries)))},
    )

    assert tools.resolve() in candidates
    assert binaries.resolve() in candidates


def test_audit_scans_immediate_directories_and_deduplicates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from pycodex.windows_sandbox import audit

    flagged = tmp_path / "flagged"
    safe = tmp_path / "safe"
    flagged.mkdir()
    safe.mkdir()
    monkeypatch.setattr(
        audit,
        "_path_has_world_write_allow",
        lambda path: Path(path).name == "flagged",
    )
    monkeypatch.setattr(audit, "_gather_candidates", lambda *_args: [tmp_path])

    assert audit.audit_everyone_writable(tmp_path, {}, tmp_path) == [flagged]


def test_apply_scan_adds_deny_for_active_readonly_capability(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from pycodex.windows_sandbox import audit

    flagged = tmp_path / "flagged"
    flagged.mkdir()
    denied: list[tuple[Path, str]] = []

    class _Sid:
        def __init__(self, value: str) -> None:
            self.value = value

        def close(self) -> None:
            pass

    permissions = SimpleNamespace(
        is_enforceable_by_windows_sandbox=lambda: True,
        uses_write_capabilities_for_cwd=lambda *_args: False,
    )
    monkeypatch.setattr(
        audit,
        "audit_everyone_writable",
        lambda *_args: [flagged],
    )
    monkeypatch.setattr(
        audit,
        "load_or_create_cap_sids",
        lambda *_args: SimpleNamespace(
            workspace="S-1-15-3-1",
            readonly="S-1-15-3-2",
            workspace_by_cwd={},
            writable_root_by_path={},
        ),
    )
    monkeypatch.setattr(audit, "LocalSid", _Sid)
    monkeypatch.setattr(
        audit,
        "add_deny_write_ace",
        lambda path, sid: denied.append((Path(path), sid.value)) or True,
    )

    audit.apply_world_writable_scan_and_denies_for_permissions(
        tmp_path / "home",
        tmp_path,
        {},
        permissions,
        tmp_path,
    )

    assert denied == [(flagged, "S-1-15-3-2")]
