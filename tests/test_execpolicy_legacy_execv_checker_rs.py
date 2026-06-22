"""Rust-derived tests for ``codex-execpolicy-legacy/src/execv_checker.rs``."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from pycodex.execpolicy_legacy import ArgType
from pycodex.execpolicy_legacy import CannotCheckRelativePath
from pycodex.execpolicy_legacy import ExecCall
from pycodex.execpolicy_legacy import ExecvChecker
from pycodex.execpolicy_legacy import MatchedArg
from pycodex.execpolicy_legacy import MatchedExec
from pycodex.execpolicy_legacy import MatchedOpt
from pycodex.execpolicy_legacy import PolicyParser
from pycodex.execpolicy_legacy import ReadablePathNotInReadableFolders
from pycodex.execpolicy_legacy import ValidExec
from pycodex.execpolicy_legacy import WriteablePathNotInWriteableFolders


def _make_checker(fake_cp: Path) -> ExecvChecker:
    source = f"""
define_program(
    program="cp",
    args=[ARG_RFILE, ARG_WFILE],
    system_path=[{str(fake_cp)!r}],
)
"""
    return ExecvChecker.new(PolicyParser.new("#test", source).parse())


def _make_executable(path: Path) -> None:
    path.write_text("", encoding="utf-8")
    if os.name != "nt":
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_check_valid_input_files_matches_rust_module_test(tmp_path: Path) -> None:
    # Rust crate/module/test:
    # codex-execpolicy-legacy/src/execv_checker.rs::test_check_valid_input_files.
    # Contract: readable/writeable args are absolutized against cwd and must
    # live under their respective canonical allow-list roots; executable
    # system_path replaces the original program.
    fake_cp = tmp_path / "cp"
    _make_executable(fake_cp)
    checker = _make_checker(fake_cp)

    source_path = tmp_path / "source"
    dest_path = tmp_path / "dest"
    valid_exec = checker.match(
        ExecCall.new("cp", [str(source_path), str(dest_path)])
    ).exec
    assert valid_exec is not None

    with pytest.raises(ReadablePathNotInReadableFolders) as readable_e:
        checker.check(valid_exec, tmp_path, [], [])
    assert readable_e.value == ReadablePathNotInReadableFolders(source_path, [])

    with pytest.raises(WriteablePathNotInWriteableFolders) as writeable_e:
        checker.check(valid_exec, tmp_path, [tmp_path], [])
    assert writeable_e.value == WriteablePathNotInWriteableFolders(dest_path, [])

    assert checker.check(valid_exec, tmp_path, [tmp_path], [tmp_path]) == str(fake_cp)


def test_check_accepts_folder_arguments_inside_their_allowed_roots(tmp_path: Path) -> None:
    # Rust anchor: execv_checker.rs::test_check_valid_input_files, "Args are
    # the readable and writeable folders, not files within the folders."
    fake_cp = tmp_path / "cp"
    _make_executable(fake_cp)
    checker = _make_checker(fake_cp)

    valid_exec = checker.match(ExecCall.new("cp", [str(tmp_path), str(tmp_path)])).exec
    assert valid_exec is not None

    assert checker.check(valid_exec, tmp_path, [tmp_path], [tmp_path]) == str(fake_cp)


def test_check_rejects_parent_of_allowed_readable_folder(tmp_path: Path) -> None:
    # Rust anchor: execv_checker.rs::test_check_valid_input_files constructs a
    # ValidExec whose readable arg is the parent of the allowed readable root.
    dest_path = tmp_path / "dest"
    valid_exec = ValidExec(
        program="cp",
        flags=(),
        opts=(),
        args=(
            MatchedArg.new(0, ArgType.readable_file(), str(tmp_path.parent)),
            MatchedArg.new(1, ArgType.writeable_file(), str(dest_path)),
        ),
        system_path=(),
    )
    checker = ExecvChecker.new(PolicyParser.new("#empty", "").parse())

    with pytest.raises(ReadablePathNotInReadableFolders) as readable_e:
        checker.check(valid_exec, tmp_path, [tmp_path], [dest_path])
    assert readable_e.value == ReadablePathNotInReadableFolders(
        tmp_path.parent,
        [tmp_path],
    )


def test_check_rejects_relative_file_without_cwd() -> None:
    # Rust anchor: ensure_absolute_path returns CannotCheckRelativePath when a
    # ReadableFile/WriteableFile value is relative and cwd is None.
    valid_exec = ValidExec.new(
        "cat",
        [MatchedArg.new(0, ArgType.readable_file(), "relative.txt")],
        [],
    )
    checker = ExecvChecker.new(PolicyParser.new("#empty", "").parse())

    with pytest.raises(CannotCheckRelativePath) as exc:
        checker.check(valid_exec, None, [], [])
    assert exc.value == CannotCheckRelativePath(Path("relative.txt"))


def test_check_preserves_program_when_system_path_is_not_executable(tmp_path: Path) -> None:
    # Rust contract: ExecvChecker::check iterates system_path and only replaces
    # program with the first path accepted by is_executable_file.
    non_executable = tmp_path / "tool"
    non_executable.write_text("", encoding="utf-8")
    if os.name != "nt":
        non_executable.chmod(stat.S_IRUSR | stat.S_IWUSR)

    valid_exec = ValidExec(
        program="tool",
        flags=(),
        opts=(MatchedOpt.new("--output", str(tmp_path / "out"), ArgType.writeable_file()),),
        args=(),
        system_path=(str(non_executable),),
    )
    checker = ExecvChecker.new(PolicyParser.new("#empty", "").parse())

    expected = str(non_executable) if os.name == "nt" else "tool"
    assert checker.check(valid_exec, tmp_path, [], [tmp_path]) == expected


def test_match_delegates_to_policy_check(tmp_path: Path) -> None:
    # Rust anchor: ExecvChecker::match is a direct Policy::check delegate.
    fake_cp = tmp_path / "cp"
    _make_executable(fake_cp)
    checker = _make_checker(fake_cp)

    assert checker.match(ExecCall.new("cp", ["a", "b"])) == MatchedExec.match(
        ValidExec(
            program="cp",
            flags=(),
            opts=(),
            args=(
                MatchedArg.new(0, ArgType.readable_file(), "a"),
                MatchedArg.new(1, ArgType.writeable_file(), "b"),
            ),
            system_path=(str(fake_cp),),
        )
    )
