"""Parity tests for Rust ``codex-secrets/src/local.rs``."""

from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.keyring_store import MockKeyringStore
from pycodex.secrets import (
    SecretListEntry,
    SecretName,
    SecretScope,
    SecretsBackendKind,
    SecretsManager,
    compute_keyring_account,
)
from pycodex.secrets.local import (
    LOCAL_SECRETS_FILENAME,
    SECRETS_VERSION,
    LocalSecretsBackend,
    SecretsFile,
    decrypt_with_passphrase,
    encrypt_with_passphrase,
    generate_passphrase,
    parse_canonical_key,
)


def test_load_file_rejects_newer_schema_versions(tmp_path: Path) -> None:
    # Rust source: local.rs load_file_rejects_newer_schema_versions.
    keyring = MockKeyringStore()
    backend = LocalSecretsBackend.new(tmp_path, keyring)
    backend.save_file(SecretsFile(version=SECRETS_VERSION + 1, secrets={}))

    with pytest.raises(ValueError, match="newer than supported version"):
        backend.load_file()


def test_set_fails_when_keyring_is_unavailable(tmp_path: Path) -> None:
    # Rust source: local.rs set_fails_when_keyring_is_unavailable.
    keyring = MockKeyringStore()
    account = compute_keyring_account(tmp_path)
    keyring.set_error(account, "load")
    backend = LocalSecretsBackend.new(tmp_path, keyring)

    with pytest.raises(RuntimeError, match="failed to load secrets key from keyring"):
        backend.set(SecretScope.Global, SecretName.new("TEST_SECRET"), "secret-value")


def test_save_file_does_not_leave_temp_files(tmp_path: Path) -> None:
    # Rust source: local.rs save_file_does_not_leave_temp_files.
    backend = LocalSecretsBackend.new(tmp_path, MockKeyringStore())
    scope = SecretScope.Global
    name = SecretName.new("TEST_SECRET")

    backend.set(scope, name, "one")
    backend.set(scope, name, "two")

    filenames = sorted(path.name for path in backend.secrets_dir().iterdir())
    assert filenames == [LOCAL_SECRETS_FILENAME]
    assert backend.get(scope, name) == "two"


def test_local_backend_round_trips_and_filters_scopes(tmp_path: Path) -> None:
    # Rust source: LocalSecretsBackend set/get/delete/list plus scope_filter behavior.
    backend = LocalSecretsBackend.new(tmp_path, MockKeyringStore())
    global_name = SecretName.new("GLOBAL_TOKEN")
    env_scope = SecretScope.environment("env-1")
    env_name = SecretName.new("ENV_TOKEN")

    backend.set(SecretScope.Global, global_name, "global-value")
    backend.set(env_scope, env_name, "env-value")

    assert backend.get(SecretScope.Global, global_name) == "global-value"
    assert backend.get(env_scope, env_name) == "env-value"
    assert backend.list(SecretScope.Global) == [SecretListEntry(SecretScope.Global, global_name)]
    assert backend.list(env_scope) == [SecretListEntry(env_scope, env_name)]
    assert backend.delete(SecretScope.Global, global_name) is True
    assert backend.delete(SecretScope.Global, global_name) is False
    assert backend.get(SecretScope.Global, global_name) is None


def test_manager_round_trips_local_backend(tmp_path: Path) -> None:
    # Rust source: lib.rs manager_round_trips_local_backend depends on LocalSecretsBackend.
    keyring = MockKeyringStore()
    manager = SecretsManager.new_with_keyring_store(tmp_path, SecretsBackendKind.LOCAL, keyring)
    scope = SecretScope.Global
    name = SecretName.new("GITHUB_TOKEN")

    manager.set(scope, name, "token-1")

    assert manager.get(scope, name) == "token-1"
    assert manager.list(None) == [SecretListEntry(scope, name)]
    assert manager.delete(scope, name) is True
    assert manager.get(scope, name) is None


def test_parse_canonical_key_rejects_invalid_shapes() -> None:
    # Rust source: parse_canonical_key returns None for invalid canonical keys.
    assert parse_canonical_key("global/API_KEY") == SecretListEntry(SecretScope.Global, SecretName.new("API_KEY"))
    assert parse_canonical_key("env/prod/API_KEY") == SecretListEntry(
        SecretScope.environment("prod"), SecretName.new("API_KEY")
    )
    assert parse_canonical_key("global/lowercase") is None
    assert parse_canonical_key("env/prod/API_KEY/extra") is None
    assert parse_canonical_key("unknown/API_KEY") is None


def test_encrypt_with_passphrase_detects_wrong_passphrase() -> None:
    # Rust source: decrypt_with_passphrase maps decryption failure to an error.
    plaintext = b'{"version":1,"secrets":{}}'
    ciphertext = encrypt_with_passphrase(plaintext, generate_passphrase())

    with pytest.raises(ValueError, match="failed to decrypt secrets file"):
        decrypt_with_passphrase(ciphertext, generate_passphrase())
