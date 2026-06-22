import hashlib
import os
from pathlib import Path

import pytest

from pycodex.install_context import CodexPackageLayout, InstallContext, InstallMethod
from pycodex.linux_sandbox import bundled_bwrap
from pycodex.utils.absolute_path import AbsolutePathBuf


def _write_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    path.chmod(0o755)


def test_finds_package_layout_bwrap_from_install_context(tmp_path: Path) -> None:
    # Rust source: bundled_bwrap.rs finds_package_layout_bwrap_from_install_context.
    package_dir = tmp_path
    bin_dir = package_dir / "bin"
    resources_dir = package_dir / "codex-resources"
    expected_bwrap = resources_dir / "bwrap"
    bin_dir.mkdir()
    _write_executable(expected_bwrap)
    context = InstallContext(
        method=InstallMethod.Other(),
        package_layout=CodexPackageLayout(
            package_dir=AbsolutePathBuf.from_absolute_path_checked(package_dir),
            bin_dir=AbsolutePathBuf.from_absolute_path_checked(bin_dir),
            resources_dir=AbsolutePathBuf.from_absolute_path_checked(resources_dir),
            path_dir=None,
        ),
    )

    assert bundled_bwrap.find_for_install_context(context) == expected_bwrap


def test_finds_legacy_standalone_bundled_bwrap_next_to_exe_resources(tmp_path: Path) -> None:
    # Rust source: bundled_bwrap.rs finds legacy codex-resources/bwrap next to exe.
    exe = tmp_path / "codex"
    expected_bwrap = tmp_path / "codex-resources" / "bwrap"
    _write_executable(exe)
    _write_executable(expected_bwrap)

    assert bundled_bwrap.find_legacy_for_exe(exe) == expected_bwrap


def test_finds_npm_bundled_bwrap_next_to_target_vendor_dir(tmp_path: Path) -> None:
    # Rust source: bundled_bwrap.rs finds ../codex-resources/bwrap for npm layout.
    target_dir = tmp_path / "vendor" / "x86_64-unknown-linux-musl"
    exe = target_dir / "codex" / "codex"
    expected_bwrap = target_dir / "codex-resources" / "bwrap"
    _write_executable(exe)
    _write_executable(expected_bwrap)

    assert bundled_bwrap.find_legacy_for_exe(exe) == expected_bwrap


def test_finds_adjacent_dev_bwrap(tmp_path: Path) -> None:
    # Rust source: bundled_bwrap.rs finds adjacent dev bwrap.
    exe = tmp_path / "codex"
    expected_bwrap = tmp_path / "bwrap"
    _write_executable(exe)
    _write_executable(expected_bwrap)

    assert bundled_bwrap.find_legacy_for_exe(exe) == expected_bwrap


def test_digest_verification_skips_missing_expected_digest(tmp_path: Path) -> None:
    # Rust source: verify_digest(file, None, path) skips verification.
    path = tmp_path / "bwrap"
    path.write_bytes(b"contents")
    with path.open("rb") as file:
        bundled_bwrap.verify_digest(file, None, path)


def test_digest_verification_accepts_matching_digest(tmp_path: Path) -> None:
    # Rust source: matching sha256 digest verifies successfully.
    path = tmp_path / "bwrap"
    path.write_bytes(b"contents")
    expected = hashlib.sha256(b"contents").digest()
    with path.open("rb") as file:
        bundled_bwrap.verify_digest(file, expected, path)


def test_digest_verification_rejects_mismatched_digest(tmp_path: Path) -> None:
    # Rust source: mismatched digest reports bundled bubblewrap digest mismatch.
    path = tmp_path / "bwrap"
    path.write_bytes(b"contents")
    with path.open("rb") as file:
        with pytest.raises(ValueError, match="bundled bubblewrap digest mismatch"):
            bundled_bwrap.verify_digest(file, bytes([0xAB]) * 32, path)


def test_parses_sha256_hex_digest() -> None:
    # Rust source: bundled_bwrap.rs parses_sha256_hex_digest.
    assert bundled_bwrap.parse_sha256_hex("ab" * 32) == bytes([0xAB]) * 32
    assert bundled_bwrap.parse_sha256_hex("00" * 32) == bundled_bwrap.NULL_SHA256_DIGEST
    with pytest.raises(ValueError):
        bundled_bwrap.parse_sha256_hex("ab")
    with pytest.raises(ValueError):
        bundled_bwrap.parse_sha256_hex(("00" * 31) + "xx")


def test_expected_sha256_treats_null_digest_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_BWRAP_SHA256", "00" * 32)
    assert bundled_bwrap.expected_sha256() is None

    monkeypatch.setenv("CODEX_BWRAP_SHA256", "ab" * 32)
    assert bundled_bwrap.expected_sha256() == bytes([0xAB]) * 32
