from __future__ import annotations

import inspect
from pathlib import Path


def test_conpty_and_proc_thread_attr_have_rust_aligned_owners() -> None:
    from pycodex.windows_sandbox import conpty, proc_thread_attr

    assert conpty.ConptyInstance.__module__ == "pycodex.windows_sandbox.conpty"
    assert (
        conpty.spawn_conpty_process_as_user.__module__
        == "pycodex.windows_sandbox.conpty"
    )
    assert (
        proc_thread_attr.ProcThreadAttributeList.__module__
        == "pycodex.windows_sandbox.proc_thread_attr"
    )


def test_process_tty_path_delegates_to_conpty_owner(monkeypatch, tmp_path: Path) -> None:
    from pycodex.windows_sandbox import conpty, process

    observed: list[object] = []
    monkeypatch.setattr(process, "_require_windows", lambda: None)
    monkeypatch.setattr(
        conpty,
        "spawn_conpty_process_as_user",
        lambda *args, **kwargs: observed.append((args, kwargs)) or "conpty-process",
    )

    result = process.create_process_as_user_popen(
        7,
        ["cmd.exe"],
        tmp_path,
        {"A": "B"},
        stdin_open=True,
        tty=True,
        merge_stderr=True,
        use_private_desktop=False,
    )

    assert result == "conpty-process"
    assert observed == [
        (
            (7, ["cmd.exe"], tmp_path, {"A": "B"}),
            {
                "stdin_open": True,
                "use_private_desktop": False,
            },
        )
    ]


def test_process_no_longer_owns_conpty_or_attribute_list_implementations() -> None:
    from pycodex.windows_sandbox import process

    source = inspect.getsource(process)
    assert "class ConptyInstance" not in source
    assert "def create_process_as_user_conpty_popen" not in source
    assert "def _handle_attribute_list" not in source
    assert "def _pseudoconsole_attribute_list" not in source


def test_crate_root_reexports_rust_conpty_entry_points() -> None:
    import pycodex.windows_sandbox as sandbox
    from pycodex.windows_sandbox import conpty

    assert sandbox.ConptyInstance is conpty.ConptyInstance
    assert (
        sandbox.spawn_conpty_process_as_user
        is conpty.spawn_conpty_process_as_user
    )
