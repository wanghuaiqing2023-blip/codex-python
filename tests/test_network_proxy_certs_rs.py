from __future__ import annotations

import os
import stat
from types import SimpleNamespace

import pytest

import pycodex.network_proxy as network_proxy
from pycodex.network_proxy import (
    MANAGED_MITM_CA_CERT,
    MANAGED_MITM_CA_DIR,
    MANAGED_MITM_CA_KEY,
    managed_ca_paths,
    validate_existing_ca_key_file,
    write_atomic_create_new,
)


def test_validate_existing_ca_key_file_rejects_group_world_permissions(tmp_path, monkeypatch) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/certs.rs
    # Rust test: validate_existing_ca_key_file_rejects_group_world_permissions
    # Contract: Unix managed CA private key files must not expose group/world permission bits.
    key_path = tmp_path / "ca.key"
    key_path.write_text("key", encoding="utf-8")
    monkeypatch.setattr(
        network_proxy.os,
        "lstat",
        lambda _path: SimpleNamespace(st_mode=stat.S_IFREG | 0o644),
    )

    with pytest.raises(PermissionError) as exc_info:
        validate_existing_ca_key_file(key_path, unix=True)

    assert "group/world accessible" in str(exc_info.value)
    assert "mode=644" in str(exc_info.value)


def test_validate_existing_ca_key_file_rejects_symlink(tmp_path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/certs.rs
    # Rust test: validate_existing_ca_key_file_rejects_symlink
    # Contract: Unix managed CA key validation uses symlink metadata and refuses symlink paths.
    if not hasattr(os, "symlink"):
        pytest.skip("symlink creation unavailable on this platform")
    target = tmp_path / "real.key"
    link = tmp_path / "ca.key"
    target.write_text("key", encoding="utf-8")
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(ValueError) as exc_info:
        validate_existing_ca_key_file(link, unix=True)

    assert "symlink" in str(exc_info.value)


def test_validate_existing_ca_key_file_allows_private_permissions(tmp_path, monkeypatch) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/certs.rs
    # Rust test: validate_existing_ca_key_file_allows_private_permissions
    # Contract: Unix managed CA key validation accepts regular files with mode 0600.
    key_path = tmp_path / "ca.key"
    key_path.write_text("key", encoding="utf-8")
    monkeypatch.setattr(
        network_proxy.os,
        "lstat",
        lambda _path: SimpleNamespace(st_mode=stat.S_IFREG | 0o600),
    )

    validate_existing_ca_key_file(key_path, unix=True)


def test_managed_ca_paths_uses_codex_home_proxy_file_names(tmp_path) -> None:
    # Source: rust_source_contract
    # Rust crate: codex-network-proxy
    # Rust module: src/certs.rs
    # Contract: managed_ca_paths joins CODEX_HOME with proxy/ca.pem and proxy/ca.key.
    paths = managed_ca_paths(tmp_path)

    assert paths.cert_path == tmp_path / MANAGED_MITM_CA_DIR / MANAGED_MITM_CA_CERT
    assert paths.key_path == tmp_path / MANAGED_MITM_CA_DIR / MANAGED_MITM_CA_KEY


def test_write_atomic_create_new_writes_file_and_refuses_overwrite(tmp_path) -> None:
    # Source: rust_source_contract
    # Rust crate: codex-network-proxy
    # Rust module: src/certs.rs
    # Contract: write_atomic_create_new writes through a temp path and refuses to overwrite an existing final path.
    target = tmp_path / "ca.key"

    write_atomic_create_new(target, b"secret", 0o600)

    assert target.read_bytes() == b"secret"
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_atomic_create_new(target, b"new-secret", 0o600)
    assert target.read_bytes() == b"secret"
    assert list(tmp_path.glob(".ca.key.tmp.*")) == []
