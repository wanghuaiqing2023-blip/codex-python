from __future__ import annotations

import importlib

from pycodex import shell_escalation


def test_rust_unix_modules_have_distinct_python_owners() -> None:
    # Rust: codex-shell-escalation/src/unix/mod.rs module graph.
    expected = {
        "escalate_protocol": [
            "EscalateAction",
            "EscalateRequest",
            "EscalateResponse",
            "EscalationDecision",
            "EscalationExecution",
            "SuperExecMessage",
            "SuperExecResult",
        ],
        "socket": ["AsyncDatagramSocket", "AsyncSocket", "encode_length"],
        "escalate_client": ["run_shell_escalation_execve_wrapper"],
        "escalate_server": [
            "EscalateServer",
            "EscalationSession",
            "ExecParams",
            "ExecResult",
            "PreparedExec",
            "ShellCommandExecutor",
        ],
        "escalation_policy": ["EscalationPolicy"],
        "execve_wrapper": ["ExecveWrapperCli", "main_execve_wrapper"],
        "stopwatch": ["Stopwatch"],
    }
    for module_name, symbols in expected.items():
        module = importlib.import_module(
            f"pycodex.shell_escalation.unix.{module_name}"
        )
        for symbol in symbols:
            owned = getattr(module, symbol)
            assert owned.__module__ == module.__name__
            if hasattr(shell_escalation, symbol):
                assert getattr(shell_escalation, symbol) is owned


def test_execve_wrapper_binary_has_its_own_owner() -> None:
    # Rust: src/bin/main_execve_wrapper.rs::main.
    module = importlib.import_module(
        "pycodex.shell_escalation.bin.main_execve_wrapper"
    )
    assert module.main.__module__ == module.__name__
