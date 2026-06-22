from __future__ import annotations

import pytest

from pycodex.keyring_store import (
    CredentialStoreError,
    KeyringNoEntryError,
    MockKeyringStore,
)


def test_credential_store_error_wraps_underlying_error() -> None:
    # Rust crate/module: codex-keyring-store src/lib.rs. Behavior contract:
    # CredentialStoreError::new stores the backend error, displays it, exposes
    # message(), and can return it through into_error().
    cause = RuntimeError("backend unavailable")
    error = CredentialStoreError.new(cause)

    assert str(error) == "backend unavailable"
    assert error.message() == "backend unavailable"
    assert error.into_error() is cause


def test_mock_keyring_store_save_load_delete_cycle() -> None:
    # Rust crate/module: codex-keyring-store src/lib.rs public tests module.
    # Behavior contract: MockKeyringStore supports account-scoped
    # save/load/saved_value/contains/delete behavior.
    store = MockKeyringStore()

    assert store.load("service", "alice") is None
    assert store.delete("service", "alice") is False
    assert store.contains("alice") is False

    store.save("service", "alice", "token")

    assert store.contains("alice") is True
    assert store.load("service", "alice") == "token"
    assert store.saved_value("alice") == "token"
    assert store.delete("service", "alice") is True
    assert store.contains("alice") is False
    assert store.saved_value("alice") is None


def test_mock_keyring_store_load_no_entry_error_returns_none() -> None:
    # Rust crate/module: codex-keyring-store src/lib.rs public tests module.
    # Behavior contract: MockKeyringStore::load maps KeyringError::NoEntry to
    # Ok(None), matching DefaultKeyringStore.
    store = MockKeyringStore()
    store.save("service", "alice", "token")
    store.set_error("alice", KeyringNoEntryError())

    assert store.load("service", "alice") is None


def test_mock_keyring_store_delete_no_entry_removes_cached_credential() -> None:
    # Rust crate/module: codex-keyring-store src/lib.rs public tests module.
    # Behavior contract: delete maps KeyringError::NoEntry to Ok(false) and then
    # removes the cached mock credential from the helper map.
    store = MockKeyringStore()
    store.save("service", "alice", "token")
    store.set_error("alice", KeyringNoEntryError())

    assert store.delete("service", "alice") is False
    assert store.contains("alice") is False


def test_mock_keyring_store_wraps_injected_backend_errors() -> None:
    # Rust crate/module: codex-keyring-store src/lib.rs public tests module.
    # Behavior contract: injected non-NoEntry backend errors are wrapped as
    # CredentialStoreError.
    store = MockKeyringStore()
    store.set_error("alice", RuntimeError("backend failed"))

    with pytest.raises(CredentialStoreError) as excinfo:
        store.load("service", "alice")

    assert str(excinfo.value) == "backend failed"
    assert isinstance(excinfo.value.into_error(), RuntimeError)
