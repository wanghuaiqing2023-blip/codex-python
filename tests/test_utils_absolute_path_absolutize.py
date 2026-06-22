from __future__ import annotations

from pathlib import Path

import pytest

import pycodex.utils.absolute_path as absolute_path
from pycodex.utils.absolute_path import AbsolutePathBuf, AbsolutePathBufGuard


def test_lib_resolve_with_absolute_path_ignores_base_path(tmp_path: Path) -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/lib.rs
    # Rust test: tests::create_with_absolute_path_ignores_base_path
    base = tmp_path / "base"
    absolute_file = tmp_path / "absolute" / "file.txt"

    assert AbsolutePathBuf.resolve_path_against_base(absolute_file, base).as_path() == absolute_file


def test_lib_from_absolute_path_checked_rejects_relative_path() -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/lib.rs
    # Rust test: tests::from_absolute_path_checked_rejects_relative_path
    with pytest.raises(ValueError, match="path is not absolute"):
        AbsolutePathBuf.from_absolute_path_checked("relative/path")


def test_lib_relative_path_dots_are_normalized_against_base_path(tmp_path: Path) -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/lib.rs
    # Rust test: tests::relative_path_dots_are_normalized_against_base_path
    assert AbsolutePathBuf.resolve_path_against_base("./nested/../file.txt", tmp_path).as_path() == tmp_path / "file.txt"


def test_lib_join_resolves_against_current_absolute_path(tmp_path: Path) -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/lib.rs
    # Contract: AbsolutePathBuf::join delegates to resolve_path_against_base with self as base.
    root = AbsolutePathBuf.from_absolute_path_checked(tmp_path)

    assert root.join("nested/../file.txt").as_path() == tmp_path / "file.txt"


def test_lib_canonicalize_returns_absolute_path_buf(tmp_path: Path) -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/lib.rs
    # Rust test: tests::canonicalize_returns_absolute_path_buf
    target_dir = tmp_path / "two"
    target_dir.mkdir()
    target = target_dir / "file.txt"
    target.write_text("", encoding="utf-8")

    path = AbsolutePathBuf.from_absolute_path(tmp_path / "one" / ".." / "two" / "." / "file.txt")

    assert path.canonicalize().as_path() == target.resolve(strict=True)


def test_lib_canonicalize_returns_error_for_missing_path(tmp_path: Path) -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/lib.rs
    # Rust test: tests::canonicalize_returns_error_for_missing_path
    path = AbsolutePathBuf.from_absolute_path(tmp_path / "missing.txt")

    with pytest.raises(OSError):
        path.canonicalize()


def test_lib_parent_and_ancestors_return_absolute_path_bufs(tmp_path: Path) -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/lib.rs
    # Rust test: tests::ancestors_returns_absolute_path_bufs
    nested = AbsolutePathBuf.from_absolute_path_checked(tmp_path / "one" / "two")

    assert nested.parent() == AbsolutePathBuf.from_absolute_path_checked(tmp_path / "one")
    assert [item.to_path_buf() for item in nested.ancestors()][:3] == [
        tmp_path / "one" / "two",
        tmp_path / "one",
        tmp_path,
    ]


def test_lib_guard_used_in_deserialization(tmp_path: Path) -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/lib.rs
    # Rust test: tests::guard_used_in_deserialization
    with pytest.raises(ValueError, match="without a base path"):
        AbsolutePathBuf.deserialize("subdir/file.txt")

    with AbsolutePathBufGuard(tmp_path):
        assert AbsolutePathBuf.deserialize("subdir/file.txt").as_path() == tmp_path / "subdir" / "file.txt"


def test_lib_home_directory_paths_expand_in_deserialization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/lib.rs
    # Rust tests: home_directory_root_is_expanded_in_deserialization,
    # home_directory_subpath_is_expanded_in_deserialization,
    # home_directory_double_slash_is_expanded_in_deserialization.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    with AbsolutePathBufGuard(tmp_path):
        assert AbsolutePathBuf.deserialize("~").as_path() == home
        assert AbsolutePathBuf.deserialize("~/code").as_path() == home / "code"
        assert AbsolutePathBuf.deserialize("~//code").as_path() == home / "code"


def test_lib_normalize_windows_device_path_strips_supported_verbatim_prefixes() -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/lib.rs
    # Rust test: tests::normalize_windows_device_path_strips_supported_verbatim_prefixes
    assert absolute_path._normalize_windows_device_path(r"\\?\D:\c\x\worktrees\2508\swift-base") == (
        r"D:\c\x\worktrees\2508\swift-base"
    )
    assert absolute_path._normalize_windows_device_path(r"\\.\D:\c\x\worktrees\2508\swift-base") == (
        r"D:\c\x\worktrees\2508\swift-base"
    )
    assert absolute_path._normalize_windows_device_path(r"\\?\UNC\server\share\workspace") == (
        r"\\server\share\workspace"
    )
    assert absolute_path._normalize_windows_device_path(r"\\.\UNC\server\share\workspace") == (
        r"\\server\share\workspace"
    )
    assert absolute_path._normalize_windows_device_path(r"\\?\GLOBALROOT\Device") is None


def test_absolute_path_without_dots_is_unchanged() -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/absolutize.rs
    # Rust test: tests::absolute_path_without_dots_is_unchanged
    path = _test_absolute_path("path/to/123/456")

    assert absolute_path._absolutize(path) == path


def test_absolute_path_dots_are_removed() -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/absolutize.rs
    # Rust test: tests::absolute_path_dots_are_removed
    assert absolute_path._absolutize(_test_absolute_path("path/to/./123/../456")) == _test_absolute_path("path/to/456")


def test_relative_path_without_dot_uses_current_dir(monkeypatch) -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/absolutize.rs
    # Rust test: tests::relative_path_without_dot_uses_base
    monkeypatch.chdir(Path("/base") if Path("/base").exists() else Path.cwd())
    cwd = Path.cwd()

    assert absolute_path._absolutize(Path("path/to/123/456")) == cwd / "path/to/123/456"


def test_normalized_parts_remove_current_dir_and_parent_segments() -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/absolutize.rs
    # Rust tests: relative_path_with_current_dir_uses_base,
    # relative_path_with_parent_dir_uses_base_parent.
    assert Path(*absolute_path._normalized_parts(Path("./path/to/123/456"))) == Path("path/to/123/456")
    assert Path(*absolute_path._normalized_parts(Path("cwd/../path/to/123/456"))) == Path("path/to/123/456")


def test_parent_dir_above_root_stays_at_root() -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/absolutize.rs
    # Rust test: tests::parent_dir_above_root_stays_at_root
    root = Path.cwd().anchor
    assert absolute_path.AbsolutePathBuf.resolve_path_against_base("../../path/to/123/456", root).as_path() == (
        Path(root) / "path/to/123/456"
    )


def test_empty_path_uses_base(tmp_path: Path) -> None:
    # Source: codex/codex-rs/utils/absolute-path/src/absolutize.rs
    # Rust test: tests::empty_path_uses_base
    assert absolute_path.AbsolutePathBuf.resolve_path_against_base("", tmp_path).as_path() == tmp_path


def _test_absolute_path(relative: str) -> Path:
    return Path(Path.cwd().anchor) / relative
