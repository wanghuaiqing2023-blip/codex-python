from __future__ import annotations

import pytest

from pycodex.exec_server import (
    ByteChunk,
    ExecOutputDeltaNotification,
    ExecOutputStream,
    ExecResponse,
    ExecServerRuntimePaths,
    ProcessId,
)


def test_process_id_string_newtype_contract() -> None:
    # Rust crate/module: codex-exec-server/src/process_id.rs.
    # Contract: ProcessId is a transparent String newtype with new/as_str/into_inner,
    # Display, From<String>/From<&str>, Eq/Hash/Ord, Borrow<str>, and AsRef<str>.
    pid = ProcessId.new("proc-1")

    assert pid.as_str() == "proc-1"
    assert str(pid) == "proc-1"
    assert pid.into_inner() == "proc-1"
    assert ProcessId("proc-1") == pid
    assert pid == "proc-1"
    assert {pid: "running"}[ProcessId("proc-1")] == "running"
    assert sorted([ProcessId("proc-2"), ProcessId("proc-1")]) == [
        ProcessId("proc-1"),
        ProcessId("proc-2"),
    ]


def test_process_id_protocol_fields_keep_transparent_value() -> None:
    # Rust crate/modules: codex-exec-server/src/process_id.rs and protocol.rs.
    # Contract: protocol process_id fields carry the ProcessId transparent
    # string identity without adding a nested object shape.
    pid = ProcessId.new("proc-42")

    assert ExecResponse(process_id=pid).process_id.as_str() == "proc-42"
    notification = ExecOutputDeltaNotification(
        process_id=pid,
        seq=7,
        stream=ExecOutputStream.STDOUT,
        chunk=ByteChunk(b"hello"),
    )
    assert str(notification.process_id) == "proc-42"


def test_runtime_paths_from_optional_paths_requires_codex_self_exe() -> None:
    # Rust crate/module: codex-exec-server/src/runtime_paths.rs.
    # Contract: from_optional_paths returns InvalidInput when codex_self_exe
    # is absent, with the user-facing message below.
    with pytest.raises(ValueError, match="Codex executable path is not configured"):
        ExecServerRuntimePaths.from_optional_paths(None, None)


def test_runtime_paths_new_absolutizes_configured_paths(tmp_path, monkeypatch) -> None:
    # Rust crate/module: codex-exec-server/src/runtime_paths.rs.
    # Contract: new wraps codex_self_exe and codex_linux_sandbox_exe through
    # AbsolutePathBuf::from_absolute_path, which absolutizes relative paths.
    monkeypatch.chdir(tmp_path)

    paths = ExecServerRuntimePaths.new("bin/codex", "bin/codex-linux-sandbox")

    assert paths.codex_self_exe.as_path() == tmp_path / "bin" / "codex"
    assert paths.codex_linux_sandbox_exe is not None
    assert paths.codex_linux_sandbox_exe.as_path() == tmp_path / "bin" / "codex-linux-sandbox"
    assert paths.to_mapping() == {
        "codex_self_exe": str(tmp_path / "bin" / "codex"),
        "codex_linux_sandbox_exe": str(tmp_path / "bin" / "codex-linux-sandbox"),
    }


def test_runtime_paths_accepts_missing_linux_sandbox_path(tmp_path, monkeypatch) -> None:
    # Rust crate/module: codex-exec-server/src/runtime_paths.rs.
    # Contract: codex_linux_sandbox_exe is optional after codex_self_exe is
    # configured and successfully converted to AbsolutePathBuf.
    monkeypatch.chdir(tmp_path)

    paths = ExecServerRuntimePaths.from_optional_paths("bin/codex", None)

    assert paths.codex_self_exe.as_path() == tmp_path / "bin" / "codex"
    assert paths.codex_linux_sandbox_exe is None
    assert paths.to_mapping() == {
        "codex_self_exe": str(tmp_path / "bin" / "codex"),
        "codex_linux_sandbox_exe": None,
    }
