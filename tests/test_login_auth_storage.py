from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import pytest

from pycodex.keyring_store import CredentialStoreError, MockKeyringStore
from pycodex.login.auth.storage import (
    KEYRING_SERVICE,
    AuthDotJson,
    AutoAuthStorage,
    EphemeralAuthStorage,
    FileAuthStorage,
    KeyringAuthStorage,
    agent_identity_auth_record_from_agent_identity_jwt,
    compute_store_key,
    create_auth_storage,
    delete_file_if_exists,
    get_auth_file,
)
from pycodex.login.token_data import TokenData
from pycodex.protocol.auth import KnownPlan


def _jwt_with_payload(payload: dict[str, object]) -> str:
    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    return ".".join(
        [
            encode(b'{"alg":"none","typ":"JWT"}'),
            encode(json.dumps(payload).encode("utf-8")),
            encode(b"sig"),
        ]
    )


def _auth_dot_json() -> AuthDotJson:
    jwt = _jwt_with_payload(
        {
            "https://api.openai.com/auth": {
                "chatgpt_plan_type": "pro",
                "chatgpt_user_id": "user-id",
                "chatgpt_account_id": "account-id",
            }
        }
    )
    return AuthDotJson(
        auth_mode="chatgpt",
        openai_api_key="sk-test",
        tokens=TokenData.from_mapping(
            {
                "id_token": jwt,
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "account_id": "account-id",
            }
        ),
        last_refresh=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        agent_identity="agent.jwt.sig",
    )


def test_get_auth_file_and_delete_file_if_exists(tmp_path):
    # Rust crate: codex-login
    # Rust module: src/auth/storage.rs
    # Rust test: file_storage_delete_removes_auth_file
    auth_file = get_auth_file(tmp_path)
    assert auth_file == tmp_path / "auth.json"
    assert delete_file_if_exists(tmp_path) is False
    auth_file.write_text("{}", encoding="utf-8")
    assert delete_file_if_exists(tmp_path) is True
    assert not auth_file.exists()


def test_file_storage_save_load_and_json_shape(tmp_path):
    # Rust test: file_storage_save_persists_auth_dot_json
    storage = FileAuthStorage(tmp_path)
    auth = _auth_dot_json()

    storage.save(auth)

    data = json.loads((tmp_path / "auth.json").read_text(encoding="utf-8"))
    assert data["auth_mode"] == "chatgpt"
    assert data["OPENAI_API_KEY"] == "sk-test"
    assert data["tokens"]["access_token"] == "access-token"
    assert data["last_refresh"] == "2026-01-02T03:04:05Z"
    assert storage.load() == auth


def test_file_storage_load_missing_returns_none(tmp_path):
    # Rust test: FileAuthStorage::load NotFound branch
    assert FileAuthStorage(tmp_path).load() is None


def test_file_storage_loads_agent_identity_jwt_as_record():
    # Rust tests:
    # - file_storage_round_trips_agent_identity_auth
    # - file_storage_loads_agent_identity_as_jwt
    jwt = _jwt_with_payload(
        {
            "agent_runtime_id": "agent-runtime-id",
            "agent_private_key": "private-key",
            "account_id": "account-id",
            "chatgpt_user_id": "user-id",
            "email": "user@example.com",
            "plan_type": "hc",
            "chatgpt_account_is_fedramp": False,
        }
    )

    record = agent_identity_auth_record_from_agent_identity_jwt(jwt)

    assert record.agent_runtime_id == "agent-runtime-id"
    assert record.agent_private_key == "private-key"
    assert record.account_id == "account-id"
    assert record.chatgpt_user_id == "user-id"
    assert record.email == "user@example.com"
    assert record.plan_type.known is KnownPlan.ENTERPRISE
    assert record.chatgpt_account_is_fedramp is False


def test_ephemeral_storage_save_load_delete_is_in_memory_only(tmp_path):
    # Rust test: ephemeral_storage_save_load_delete_is_in_memory_only
    storage = EphemeralAuthStorage(tmp_path)
    auth = _auth_dot_json()

    storage.save(auth)

    assert storage.load() == auth
    assert not (tmp_path / "auth.json").exists()
    assert storage.delete() is True
    assert storage.load() is None


def test_keyring_auth_storage_compute_store_key_for_home_directory():
    # Rust test: keyring_auth_storage_compute_store_key_for_home_directory
    assert compute_store_key("~/.codex") == "cli|940db7b1d0e4eb40"


def test_keyring_auth_storage_load_returns_deserialized_auth(tmp_path):
    # Rust test: keyring_auth_storage_load_returns_deserialized_auth
    store = MockKeyringStore()
    auth = _auth_dot_json()
    account = compute_store_key(tmp_path)
    store.save(KEYRING_SERVICE, account, json.dumps(auth.to_json_dict()))

    assert KeyringAuthStorage(tmp_path, store).load() == auth


def test_keyring_auth_storage_save_persists_and_removes_fallback_file(tmp_path):
    # Rust test: keyring_auth_storage_save_persists_and_removes_fallback_file
    store = MockKeyringStore()
    fallback = FileAuthStorage(tmp_path)
    fallback.save(_auth_dot_json())

    KeyringAuthStorage(tmp_path, store).save(_auth_dot_json())

    assert store.saved_value(compute_store_key(tmp_path)) is not None
    assert not (tmp_path / "auth.json").exists()


def test_keyring_auth_storage_delete_removes_keyring_and_file(tmp_path):
    # Rust test: keyring_auth_storage_delete_removes_keyring_and_file
    store = MockKeyringStore()
    account = compute_store_key(tmp_path)
    store.save(KEYRING_SERVICE, account, "{}")
    (tmp_path / "auth.json").write_text("{}", encoding="utf-8")

    assert KeyringAuthStorage(tmp_path, store).delete() is True
    assert not store.contains(account)
    assert not (tmp_path / "auth.json").exists()


def test_auto_auth_storage_load_prefers_keyring_value(tmp_path):
    # Rust test: auto_auth_storage_load_prefers_keyring_value
    store = MockKeyringStore()
    keyring_auth = _auth_dot_json()
    file_auth = AuthDotJson(openai_api_key="file-key")
    FileAuthStorage(tmp_path).save(file_auth)
    store.save(KEYRING_SERVICE, compute_store_key(tmp_path), json.dumps(keyring_auth.to_json_dict()))

    assert AutoAuthStorage(tmp_path, store).load() == keyring_auth


def test_auto_auth_storage_load_uses_file_when_keyring_empty(tmp_path):
    # Rust test: auto_auth_storage_load_uses_file_when_keyring_empty
    auth = _auth_dot_json()
    FileAuthStorage(tmp_path).save(auth)
    assert AutoAuthStorage(tmp_path, MockKeyringStore()).load() == auth


def test_auto_auth_storage_load_falls_back_when_keyring_errors(tmp_path):
    # Rust test: auto_auth_storage_load_falls_back_when_keyring_errors
    store = MockKeyringStore()
    store.set_error(compute_store_key(tmp_path), "boom")
    auth = _auth_dot_json()
    FileAuthStorage(tmp_path).save(auth)

    assert AutoAuthStorage(tmp_path, store).load() == auth


def test_auto_auth_storage_save_prefers_keyring(tmp_path):
    # Rust test: auto_auth_storage_save_prefers_keyring
    store = MockKeyringStore()
    auth = _auth_dot_json()

    AutoAuthStorage(tmp_path, store).save(auth)

    assert store.saved_value(compute_store_key(tmp_path)) is not None
    assert not (tmp_path / "auth.json").exists()


def test_auto_auth_storage_save_falls_back_when_keyring_errors(tmp_path):
    # Rust test: auto_auth_storage_save_falls_back_when_keyring_errors
    store = MockKeyringStore()
    store.set_error(compute_store_key(tmp_path), "boom")
    auth = _auth_dot_json()

    AutoAuthStorage(tmp_path, store).save(auth)

    assert FileAuthStorage(tmp_path).load() == auth


def test_create_auth_storage_selects_backends(tmp_path):
    # Rust contract: create_auth_storage dispatches AuthCredentialsStoreMode.
    assert isinstance(create_auth_storage(tmp_path, "file"), FileAuthStorage)
    assert isinstance(create_auth_storage(tmp_path, "keyring", keyring_store=MockKeyringStore()), KeyringAuthStorage)
    assert isinstance(create_auth_storage(tmp_path, "auto", keyring_store=MockKeyringStore()), AutoAuthStorage)
    assert isinstance(create_auth_storage(tmp_path, "ephemeral"), EphemeralAuthStorage)
    with pytest.raises(ValueError):
        create_auth_storage(tmp_path, "unknown")


def test_keyring_auth_storage_load_wraps_keyring_errors(tmp_path):
    # Rust contract: keyring load errors include the keyring message.
    store = MockKeyringStore()
    store.set_error(compute_store_key(tmp_path), "backend down")

    with pytest.raises(RuntimeError, match="failed to load CLI auth from keyring: backend down"):
        KeyringAuthStorage(tmp_path, store).load()


def test_keyring_auth_storage_load_wraps_deserialize_errors(tmp_path):
    # Rust contract: invalid keyring JSON is reported as deserialize failure.
    store = MockKeyringStore()
    store.save(KEYRING_SERVICE, compute_store_key(tmp_path), "[not-object]")

    with pytest.raises(RuntimeError, match="failed to deserialize CLI auth from keyring"):
        KeyringAuthStorage(tmp_path, store).load()


def test_keyring_auth_storage_save_wraps_keyring_errors(tmp_path):
    # Rust contract: keyring save errors include the keyring message.
    store = MockKeyringStore()
    store.set_error(compute_store_key(tmp_path), CredentialStoreError("backend down"))

    with pytest.raises(RuntimeError, match="failed to write OAuth tokens to keyring: backend down"):
        KeyringAuthStorage(tmp_path, store).save(_auth_dot_json())
