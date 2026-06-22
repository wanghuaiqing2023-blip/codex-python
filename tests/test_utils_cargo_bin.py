from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.utils.cargo_bin import (
    RUNFILES_MANIFEST_ONLY_ENV,
    CargoBinNotFoundError,
    ResolvedPathDoesNotExistError,
    cargo_bin,
    cargo_bin_env_keys,
    find_resource,
    normalize_runfile_path,
    repo_root,
    resolve_bazel_runfile,
    resolve_bin_from_env,
    resolve_cargo_runfile,
    runfiles_available,
)


def test_cargo_bin_env_keys_preserve_dash_and_add_underscore_alias() -> None:
    # Source: codex/codex-rs/utils/cargo-bin/src/lib.rs
    # Contract: Cargo exports both the literal target name and dash-to-underscore alias.
    assert cargo_bin_env_keys("codex-cli") == ["CARGO_BIN_EXE_codex-cli", "CARGO_BIN_EXE_codex_cli"]
    assert cargo_bin_env_keys("codex") == ["CARGO_BIN_EXE_codex"]


def test_runfiles_available_checks_manifest_only_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Source: codex/codex-rs/utils/cargo-bin/src/lib.rs
    # Contract: RUNFILES_MANIFEST_ONLY gates Bazel runfile resolution.
    monkeypatch.delenv(RUNFILES_MANIFEST_ONLY_ENV, raising=False)
    assert not runfiles_available()

    monkeypatch.setenv(RUNFILES_MANIFEST_ONLY_ENV, "1")
    assert runfiles_available()


def test_resolve_bin_from_env_accepts_existing_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Source: codex/codex-rs/utils/cargo-bin/src/lib.rs
    # Contract: Cargo-style absolute CARGO_BIN_EXE path is returned when it exists.
    monkeypatch.delenv(RUNFILES_MANIFEST_ONLY_ENV, raising=False)
    binary = tmp_path / "codex-test-bin"
    binary.write_text("", encoding="utf-8")

    assert resolve_bin_from_env("CARGO_BIN_EXE_codex-test-bin", binary) == binary


def test_resolve_bin_from_env_errors_when_path_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Source: codex/codex-rs/utils/cargo-bin/src/lib.rs
    # Contract: unresolved CARGO_BIN_EXE values preserve the env key and raw path.
    monkeypatch.delenv(RUNFILES_MANIFEST_ONLY_ENV, raising=False)
    missing = tmp_path / "missing-bin"

    with pytest.raises(ResolvedPathDoesNotExistError) as exc_info:
        resolve_bin_from_env("CARGO_BIN_EXE_missing", missing)

    assert exc_info.value.key == "CARGO_BIN_EXE_missing"
    assert exc_info.value.path == missing


def test_cargo_bin_prefers_env_keys_before_path_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Source: codex/codex-rs/utils/cargo-bin/src/lib.rs
    # Contract: cargo_bin checks CARGO_BIN_EXE_* before the fallback resolver.
    monkeypatch.delenv(RUNFILES_MANIFEST_ONLY_ENV, raising=False)
    binary = tmp_path / "codex-test-bin"
    binary.write_text("", encoding="utf-8")
    monkeypatch.setenv("CARGO_BIN_EXE_codex-test-bin", str(binary))

    assert cargo_bin("codex-test-bin") == binary


def test_cargo_bin_reports_env_keys_on_lookup_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    # Source: codex/codex-rs/utils/cargo-bin/src/lib.rs
    # Contract: NotFound includes the generated env keys and fallback failure text.
    monkeypatch.delenv("CARGO_BIN_EXE_missing-bin", raising=False)
    monkeypatch.delenv("CARGO_BIN_EXE_missing_bin", raising=False)
    monkeypatch.setenv("PATH", "")

    with pytest.raises(CargoBinNotFoundError) as exc_info:
        cargo_bin("missing-bin")

    assert exc_info.value.name == "missing-bin"
    assert exc_info.value.env_keys == ["CARGO_BIN_EXE_missing-bin", "CARGO_BIN_EXE_missing_bin"]
    assert exc_info.value.fallback == "PATH lookup failed"


def test_resolve_cargo_runfile_joins_manifest_dir(tmp_path: Path) -> None:
    # Source: codex/codex-rs/utils/cargo-bin/src/lib.rs
    # Contract: Cargo resources are relative to CARGO_MANIFEST_DIR.
    assert resolve_cargo_runfile("fixtures/data.json", manifest_dir=tmp_path) == tmp_path / "fixtures/data.json"
    assert find_resource("fixtures/data.json", manifest_dir=tmp_path) == tmp_path / "fixtures/data.json"


def test_resolve_bazel_runfile_uses_main_package_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Source: codex/codex-rs/utils/cargo-bin/src/lib.rs
    # Contract: Bazel resources resolve as _main/<BAZEL_PACKAGE>/<resource>.
    runfiles_root = tmp_path / "runfiles"
    target = runfiles_root / "_main" / "codex/codex-rs" / "fixtures" / "data.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("RUNFILES_DIR", str(runfiles_root))

    assert resolve_bazel_runfile("codex/codex-rs", Path("./fixtures") / "data.json") == target


def test_resolve_bazel_runfile_requires_package() -> None:
    # Source: codex/codex-rs/utils/cargo-bin/src/lib.rs
    # Contract: missing BAZEL_PACKAGE is a not-found error.
    with pytest.raises(FileNotFoundError, match="BAZEL_PACKAGE was not set"):
        resolve_bazel_runfile(None, "fixtures/data.json")


def test_repo_root_walks_four_parents_from_marker(tmp_path: Path) -> None:
    # Source: codex/codex-rs/utils/cargo-bin/src/lib.rs
    # Contract: repo root is four ancestors above repo_root.marker.
    marker = tmp_path / "a" / "b" / "c" / "repo_root.marker"
    marker.parent.mkdir(parents=True)
    marker.write_text("", encoding="utf-8")

    assert repo_root(marker) == tmp_path


def test_normalize_runfile_path_removes_dot_and_normal_parent_components() -> None:
    # Source: codex/codex-rs/utils/cargo-bin/src/lib.rs
    # Contract: normal parent components cancel only a preceding normal component.
    assert normalize_runfile_path(Path("_main") / "." / "pkg" / "nested" / ".." / "file.txt") == Path(
        "_main/pkg/file.txt"
    )
    assert normalize_runfile_path(Path("..") / "pkg" / ".." / "file.txt") == Path("../file.txt")
