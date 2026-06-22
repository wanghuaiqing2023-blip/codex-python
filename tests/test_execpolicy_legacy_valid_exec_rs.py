"""Rust-derived tests for ``codex-execpolicy-legacy/src/valid_exec.rs``."""

from __future__ import annotations

import pytest

from pycodex.execpolicy_legacy import ArgType
from pycodex.execpolicy_legacy import EmptyFileName
from pycodex.execpolicy_legacy import InvalidPositiveInteger
from pycodex.execpolicy_legacy import MatchedArg
from pycodex.execpolicy_legacy import MatchedFlag
from pycodex.execpolicy_legacy import MatchedOpt
from pycodex.execpolicy_legacy import SedCommandNotProvablySafe
from pycodex.execpolicy_legacy import ValidExec


def test_valid_exec_new_matches_rust_constructor_defaults() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/valid_exec.rs.
    # Rust suite anchors: tests/suite/cp.rs and tests/suite/ls.rs use
    # ValidExec::new to keep flags/opts empty, preserve args, and copy
    # prioritized system paths.
    arg = MatchedArg.new(0, ArgType.readable_file(), "foo/bar")

    exec_match = ValidExec.new("ls", [arg], ["/bin/ls", "/usr/bin/ls"])

    assert exec_match.program == "ls"
    assert exec_match.flags == ()
    assert exec_match.opts == ()
    assert exec_match.args == (arg,)
    assert exec_match.system_path == ("/bin/ls", "/usr/bin/ls")


def test_matched_arg_new_validates_arg_type_and_stores_fields() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/valid_exec.rs.
    # Rust suite anchors: cp/head/ls/literal/sed create MatchedArg through
    # MatchedArg::new, which delegates to ArgType::validate before storing.
    arg = MatchedArg.new(1, ArgType.writeable_file(), "../baz")

    assert arg.index == 1
    assert arg.arg_type == ArgType.writeable_file()
    assert arg.value == "../baz"

    with pytest.raises(EmptyFileName):
        MatchedArg.new(0, ArgType.readable_file(), "")


def test_matched_opt_new_validates_and_name_method_matches_rust() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/valid_exec.rs.
    # Rust suite anchors: tests/suite/head.rs uses MatchedOpt::new("-n",
    # "100", ArgType::PositiveInteger); tests/suite/sed.rs uses a sed command
    # opt. MatchedOpt::name returns the matched option name string.
    opt = MatchedOpt.new("-n", "100", ArgType.positive_integer())

    assert opt.name == "-n"
    assert opt.name() == "-n"
    assert opt.value == "100"
    assert opt.arg_type == ArgType.positive_integer()

    with pytest.raises(InvalidPositiveInteger):
        MatchedOpt.new("-n", "0", ArgType.positive_integer())
    with pytest.raises(SedCommandNotProvablySafe):
        MatchedOpt.new("-e", "s/y/echo hi/e", ArgType.sed_command())


def test_matched_flag_new_keeps_flag_name() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/valid_exec.rs.
    # Rust suite anchors: tests/suite/ls.rs, tests/suite/pwd.rs, and
    # tests/suite/sed.rs compare MatchedFlag::new values.
    assert MatchedFlag.new("-a") == MatchedFlag(name="-a")
    assert MatchedFlag.new("-P").to_mapping() == {"name": "-P"}


def test_valid_exec_might_write_files_checks_opts_and_args() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/valid_exec.rs.
    # Contract: ValidExec::might_write_files is true when any matched option or
    # positional argument has an ArgType that might write files.
    read_only = ValidExec.new(
        "ls",
        [MatchedArg.new(0, ArgType.readable_file(), "foo")],
        ["/bin/ls"],
    )
    write_arg = ValidExec.new(
        "cp",
        [MatchedArg.new(1, ArgType.writeable_file(), "dest")],
        ["/bin/cp"],
    )
    write_opt = ValidExec(
        program="tool",
        flags=(),
        opts=(MatchedOpt.new("--out", "dest", ArgType.writeable_file()),),
        args=(),
        system_path=(),
    )

    assert read_only.might_write_files() is False
    assert write_arg.might_write_files() is True
    assert write_opt.might_write_files() is True


def test_valid_exec_mapping_shape_preserves_rust_serde_field_names() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/valid_exec.rs.
    # Contract: structs derive Serialize with fields program, flags, opts,
    # args, system_path; MatchedArg/MatchedOpt expose the raw Rust field
    # name `type` in serialized output.
    exec_match = ValidExec(
        program="sed",
        flags=(MatchedFlag.new("-n"),),
        opts=(MatchedOpt.new("-e", "122,202p", ArgType.sed_command()),),
        args=(MatchedArg.new(2, ArgType.readable_file(), "hello.txt"),),
        system_path=("/bin/sed", "/usr/bin/sed"),
    )

    assert exec_match.to_mapping() == {
        "program": "sed",
        "flags": [{"name": "-n"}],
        "opts": [
            {
                "name": "-e",
                "value": "122,202p",
                "type": {"type": "SedCommand"},
            }
        ],
        "args": [
            {
                "index": 2,
                "type": {"type": "ReadableFile"},
                "value": "hello.txt",
            }
        ],
        "system_path": ["/bin/sed", "/usr/bin/sed"],
    }
