"""Rust-derived ownership tests for codex-utils-pty."""

from __future__ import annotations

import importlib


def test_rust_modules_have_distinct_python_owners() -> None:
    # Rust baseline:
    # codex/codex-rs/utils/pty/src/{process,pipe,process_group,pty}.rs
    # codex/codex-rs/utils/pty/src/win/{mod,conpty,procthreadattr,psuedocon}.rs
    expected_modules = (
        "pycodex.utils.pty.process",
        "pycodex.utils.pty.pipe",
        "pycodex.utils.pty.process_group",
        "pycodex.utils.pty.pty",
        "pycodex.utils.pty.win",
        "pycodex.utils.pty.win.conpty",
        "pycodex.utils.pty.win.procthreadattr",
        "pycodex.utils.pty.win.psuedocon",
    )

    for module_name in expected_modules:
        assert importlib.import_module(module_name).__name__ == module_name


def test_items_are_defined_by_their_rust_module_counterparts() -> None:
    process = importlib.import_module("pycodex.utils.pty.process")
    pipe = importlib.import_module("pycodex.utils.pty.pipe")
    process_group = importlib.import_module("pycodex.utils.pty.process_group")
    pty = importlib.import_module("pycodex.utils.pty.pty")
    conpty = importlib.import_module("pycodex.utils.pty.win.conpty")
    procthreadattr = importlib.import_module("pycodex.utils.pty.win.procthreadattr")
    psuedocon = importlib.import_module("pycodex.utils.pty.win.psuedocon")

    assert process.TerminalSize.__module__ == process.__name__
    assert process.ProcessHandle.__module__ == process.__name__
    assert process.spawn_from_driver.__module__ == process.__name__
    assert pipe.spawn_process.__module__ == pipe.__name__
    assert process_group.kill_process_group.__module__ == process_group.__name__
    assert pty.spawn_process.__module__ == pty.__name__
    assert conpty.RawConPty.__module__ == conpty.__name__
    assert procthreadattr.ProcThreadAttributeList.__module__ == procthreadattr.__name__
    assert psuedocon.PsuedoCon.__module__ == psuedocon.__name__
