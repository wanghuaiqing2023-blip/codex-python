from pathlib import Path

import pytest

from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
)
from pycodex.windows_sandbox.deny_read_resolver import (
    glob_scan_plan,
    resolve_windows_deny_read_paths,
)


def _deny_path(path: Path) -> FileSystemSandboxEntry:
    return FileSystemSandboxEntry(
        FileSystemPath.explicit_path(path),
        FileSystemAccessMode.DENY,
    )


def _deny_glob(pattern: str) -> FileSystemSandboxEntry:
    return FileSystemSandboxEntry(
        FileSystemPath.glob_pattern(pattern),
        FileSystemAccessMode.DENY,
    )


def test_scan_plan_uses_literal_prefix_and_rust_depth_rules() -> None:
    # Rust source: deny_read_resolver::tests::{scan_root_uses_literal_prefix_before_glob,
    # scan_depth_is_bounded_for_non_recursive_globs,configured_depth_caps_recursive_glob_scans}.
    assert glob_scan_plan("/tmp/work/**/*.env", None).root == Path("/tmp/work")
    assert glob_scan_plan("C:\\Users\\dev\\repo\\**\\*.env", None).root == Path(
        "C:\\Users\\dev\\repo"
    )
    assert glob_scan_plan("/tmp/work/*.env", None).max_depth == 1
    assert glob_scan_plan("/tmp/work/*/*.env", None).max_depth == 2
    assert glob_scan_plan("/tmp/work/**/*.env", None).max_depth is None
    assert glob_scan_plan("/tmp/work/**/*.env", 2).max_depth == 2
    assert glob_scan_plan("/tmp/work/*/*.env", 1).max_depth == 1


def test_exact_missing_paths_are_preserved(tmp_path: Path) -> None:
    # Rust source: deny_read_resolver::tests::exact_missing_paths_are_preserved.
    missing = tmp_path / "missing.env"
    policy = FileSystemSandboxPolicy.restricted([_deny_path(missing)])

    assert resolve_windows_deny_read_paths(policy, tmp_path) == (missing,)


def test_glob_patterns_expand_to_existing_matches(tmp_path: Path) -> None:
    # Rust source: deny_read_resolver::tests::glob_patterns_expand_to_existing_matches.
    root_env = tmp_path / ".env"
    nested_env = tmp_path / "app" / ".env"
    notes = tmp_path / "app" / "notes.txt"
    notes.parent.mkdir()
    root_env.write_text("secret", encoding="utf-8")
    nested_env.write_text("secret", encoding="utf-8")
    notes.write_text("notes", encoding="utf-8")
    policy = FileSystemSandboxPolicy.restricted(
        [_deny_glob(f"{tmp_path.as_posix()}/**/*.env")]
    )

    assert set(resolve_windows_deny_read_paths(policy, tmp_path)) == {
        root_env,
        nested_env,
    }


def test_non_recursive_glob_does_not_expand_nested_matches(tmp_path: Path) -> None:
    # Rust source: deny_read_resolver::tests::non_recursive_globs_do_not_expand_nested_matches.
    root_env = tmp_path / ".env"
    nested_env = tmp_path / "app" / ".env"
    nested_env.parent.mkdir()
    root_env.write_text("secret", encoding="utf-8")
    nested_env.write_text("secret", encoding="utf-8")
    policy = FileSystemSandboxPolicy.restricted(
        [_deny_glob(f"{tmp_path.as_posix()}/*.env")]
    )

    assert resolve_windows_deny_read_paths(policy, tmp_path) == (root_env,)


def test_configured_depth_caps_recursive_glob_expansion(tmp_path: Path) -> None:
    first = tmp_path / "one" / ".env"
    second = tmp_path / "one" / "two" / ".env"
    second.parent.mkdir(parents=True)
    first.write_text("secret", encoding="utf-8")
    second.write_text("secret", encoding="utf-8")
    policy = FileSystemSandboxPolicy(
        entries=(_deny_glob(f"{tmp_path.as_posix()}/**/*.env"),),
        glob_scan_max_depth=2,
    )

    assert resolve_windows_deny_read_paths(policy, tmp_path) == (first,)


def test_invalid_glob_patterns_fail_before_expansion(tmp_path: Path) -> None:
    # Rust source: deny_read_resolver::tests::invalid_glob_patterns_fail_before_expansion.
    policy = FileSystemSandboxPolicy.restricted(
        [_deny_glob(f"{tmp_path.as_posix()}/**/[z-a]")]
    )

    with pytest.raises(ValueError, match="invalid deny-read glob pattern"):
        resolve_windows_deny_read_paths(policy, tmp_path)
