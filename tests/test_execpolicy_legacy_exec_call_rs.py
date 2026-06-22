"""Rust-derived tests for ``codex-execpolicy-legacy/src/exec_call.rs``."""

from __future__ import annotations

from pycodex.execpolicy_legacy import ExecCall


def test_exec_call_new_copies_program_and_args_as_strings() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/exec_call.rs.
    # Rust suite anchors: tests/suite/{cp,head,literal,ls,pwd,sed}.rs call
    # ExecCall::new(program, &[...]) before policy checks.
    exec_call = ExecCall.new("head", ["-n", 100, "src/extension.ts"])

    assert exec_call.program == "head"
    assert exec_call.args == ("-n", "100", "src/extension.ts")


def test_exec_call_display_matches_rust_space_join() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/exec_call.rs.
    # Contract: Display writes the program, then each arg prefixed by one
    # literal space; there is no shell escaping or quoting.
    assert str(ExecCall.new("pwd", [])) == "pwd"
    assert str(ExecCall.new("sed", ["-n", "122,202p", "hello.txt"])) == (
        "sed -n 122,202p hello.txt"
    )
    assert str(ExecCall.new("fake", ["has space"])) == "fake has space"


def test_exec_call_mapping_shape_matches_rust_serde_fields() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/exec_call.rs.
    # Contract: ExecCall derives Serialize with fields program and args.
    assert ExecCall.new("ls", ["-a", "src"]).to_mapping() == {
        "program": "ls",
        "args": ["-a", "src"],
    }
