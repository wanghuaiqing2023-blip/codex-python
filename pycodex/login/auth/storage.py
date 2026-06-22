"""Port of Rust ``codex-login::auth::storage``.

Rust source:
- ``codex/codex-rs/login/src/auth/storage.rs``
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Protocol

from pycodex.keyring_store import CredentialStoreError, DefaultKeyringStore, KeyringStore
from pycodex.login.auth.agent_identity import AgentIdentityAuthRecord
from pycodex.login.token_data import TokenData
from pycodex.protocol.auth import PlanType


KEYRING_SERVICE = "Codex Auth"


@dataclass(frozen=True)
class AuthDotJson:
    auth_mode: str | None = None
    openai_api_key: str | None = None
    tokens: TokenData | None = None
    last_refresh: datetime | str | None = None
    agent_identity: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AuthDotJson":
        tokens = data.get("tokens")
        return cls(
            auth_mode=_optional_str(data.get("auth_mode")),
            openai_api_key=_optional_str(data.get("OPENAI_API_KEY")),
            tokens=TokenData.from_mapping(tokens) if isinstance(tokens, Mapping) else None,
            last_refresh=_optional_datetime_or_str(data.get("last_refresh")),
            agent_identity=_optional_str(data.get("agent_identity")),
        )

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.auth_mode is not None:
            result["auth_mode"] = self.auth_mode
        if self.openai_api_key is not None:
            result["OPENAI_API_KEY"] = self.openai_api_key
        if self.tokens is not None:
            result["tokens"] = self.tokens.to_json_dict()
        if self.last_refresh is not None:
            result["last_refresh"] = _datetime_to_json(self.last_refresh)
        if self.agent_identity is not None:
            result["agent_identity"] = self.agent_identity
        return result


def agent_identity_auth_record_from_agent_identity_jwt(jwt: str) -> AgentIdentityAuthRecord:
    claims = _decode_agent_identity_jwt_payload(jwt)
    return AgentIdentityAuthRecord(
        agent_runtime_id=_expect_str(claims.get("agent_runtime_id")),
        agent_private_key=_expect_str(claims.get("agent_private_key")),
        account_id=_expect_str(claims.get("account_id")),
        chatgpt_user_id=_expect_str(claims.get("chatgpt_user_id")),
        email=_expect_str(claims.get("email")),
        plan_type=PlanType.from_raw_value(_expect_str(claims.get("plan_type"))),
        chatgpt_account_is_fedramp=bool(claims.get("chatgpt_account_is_fedramp")),
    )


def get_auth_file(codex_home: str | Path) -> Path:
    return Path(codex_home) / "auth.json"


def delete_file_if_exists(codex_home: str | Path) -> bool:
    auth_file = get_auth_file(codex_home)
    try:
        auth_file.unlink()
    except FileNotFoundError:
        return False
    return True


class AuthStorageBackend(Protocol):
    def load(self) -> AuthDotJson | None:
        ...

    def save(self, auth: AuthDotJson) -> None:
        ...

    def delete(self) -> bool:
        ...


@dataclass(frozen=True)
class FileAuthStorage:
    codex_home: Path

    def __init__(self, codex_home: str | Path) -> None:
        object.__setattr__(self, "codex_home", Path(codex_home))

    @staticmethod
    def try_read_auth_json(auth_file: str | Path) -> AuthDotJson:
        with Path(auth_file).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, Mapping):
            raise TypeError("auth.json must contain a JSON object")
        return AuthDotJson.from_mapping(data)

    def load(self) -> AuthDotJson | None:
        auth_file = get_auth_file(self.codex_home)
        try:
            return self.try_read_auth_json(auth_file)
        except FileNotFoundError:
            return None

    def save(self, auth: AuthDotJson) -> None:
        auth_file = get_auth_file(self.codex_home)
        auth_file.parent.mkdir(parents=True, exist_ok=True)
        with auth_file.open("w", encoding="utf-8") as handle:
            json.dump(auth.to_json_dict(), handle, indent=2, ensure_ascii=False)
            handle.flush()
        try:
            auth_file.chmod(0o600)
        except OSError:
            pass

    def delete(self) -> bool:
        return delete_file_if_exists(self.codex_home)


def compute_store_key(codex_home: str | Path) -> str:
    path = Path(codex_home)
    try:
        key_path = str(path.resolve(strict=True))
    except OSError:
        key_path = path.as_posix()
    digest = hashlib.sha256(key_path.encode("utf-8")).hexdigest()
    return f"cli|{digest[:16]}"


@dataclass(frozen=True)
class KeyringAuthStorage:
    codex_home: Path
    store: KeyringStore
    fallback: FileAuthStorage

    def __init__(self, codex_home: str | Path, store: KeyringStore | None = None) -> None:
        home = Path(codex_home)
        object.__setattr__(self, "codex_home", home)
        object.__setattr__(self, "store", DefaultKeyringStore() if store is None else store)
        object.__setattr__(self, "fallback", FileAuthStorage(home))

    def load(self) -> AuthDotJson | None:
        try:
            serialized = self.store.load(KEYRING_SERVICE, compute_store_key(self.codex_home))
        except CredentialStoreError as exc:
            raise RuntimeError(f"failed to load CLI auth from keyring: {exc.message()}") from exc
        if serialized is None:
            return None
        try:
            data = json.loads(serialized)
            if not isinstance(data, Mapping):
                raise TypeError("auth payload must be a JSON object")
            return AuthDotJson.from_mapping(data)
        except Exception as exc:
            raise RuntimeError(f"failed to deserialize CLI auth from keyring: {exc}") from exc

    def save(self, auth: AuthDotJson) -> None:
        serialized = json.dumps(auth.to_json_dict(), separators=(",", ":"), ensure_ascii=False)
        try:
            self.store.save(KEYRING_SERVICE, compute_store_key(self.codex_home), serialized)
        except CredentialStoreError as exc:
            raise RuntimeError(f"failed to write OAuth tokens to keyring: {exc.message()}") from exc
        self.fallback.delete()

    def delete(self) -> bool:
        keyring_deleted = self.store.delete(KEYRING_SERVICE, compute_store_key(self.codex_home))
        file_deleted = self.fallback.delete()
        return keyring_deleted or file_deleted


@dataclass(frozen=True)
class AutoAuthStorage:
    keyring: KeyringAuthStorage
    fallback: FileAuthStorage

    def __init__(self, codex_home: str | Path, store: KeyringStore | None = None) -> None:
        object.__setattr__(self, "keyring", KeyringAuthStorage(codex_home, store))
        object.__setattr__(self, "fallback", FileAuthStorage(codex_home))

    def load(self) -> AuthDotJson | None:
        try:
            auth = self.keyring.load()
        except RuntimeError:
            auth = None
        return auth if auth is not None else self.fallback.load()

    def save(self, auth: AuthDotJson) -> None:
        try:
            self.keyring.save(auth)
        except RuntimeError:
            self.fallback.save(auth)

    def delete(self) -> bool:
        return self.keyring.delete()


class EphemeralAuthStorage:
    _store: dict[str, AuthDotJson] = {}
    _lock = RLock()

    def __init__(self, codex_home: str | Path) -> None:
        self.codex_home = Path(codex_home)

    def load(self) -> AuthDotJson | None:
        with self._lock:
            return self._store.get(compute_store_key(self.codex_home))

    def save(self, auth: AuthDotJson) -> None:
        with self._lock:
            self._store[compute_store_key(self.codex_home)] = auth

    def delete(self) -> bool:
        with self._lock:
            return self._store.pop(compute_store_key(self.codex_home), None) is not None


def create_auth_storage(
    codex_home: str | Path,
    mode: str,
    *,
    keyring_store: KeyringStore | None = None,
) -> AuthStorageBackend:
    normalized = str(mode).lower()
    if normalized in {"file", "authcredentialsstoremode.file"}:
        return FileAuthStorage(codex_home)
    if normalized in {"keyring", "authcredentialsstoremode.keyring"}:
        return KeyringAuthStorage(codex_home, keyring_store)
    if normalized in {"auto", "authcredentialsstoremode.auto"}:
        return AutoAuthStorage(codex_home, keyring_store)
    if normalized in {"ephemeral", "authcredentialsstoremode.ephemeral"}:
        return EphemeralAuthStorage(codex_home)
    raise ValueError(f"unsupported auth storage mode: {mode}")


def _decode_agent_identity_jwt_payload(jwt: str) -> dict[str, Any]:
    parts = jwt.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError("invalid agent identity JWT format")
    padding = "=" * (-len(parts[1]) % 4)
    try:
        payload = base64.urlsafe_b64decode((parts[1] + padding).encode("ascii"))
    except Exception as exc:
        raise ValueError("agent identity JWT payload is not valid base64url") from exc
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("agent identity JWT payload is not valid JSON")
    return data


def _expect_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise TypeError("expected optional string")


def _optional_datetime_or_str(value: Any) -> datetime | str | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    raise TypeError("expected optional datetime string")


def _datetime_to_json(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value


__all__ = [
    "KEYRING_SERVICE",
    "AgentIdentityAuthRecord",
    "AuthDotJson",
    "AuthStorageBackend",
    "AutoAuthStorage",
    "EphemeralAuthStorage",
    "FileAuthStorage",
    "KeyringAuthStorage",
    "agent_identity_auth_record_from_agent_identity_jwt",
    "compute_store_key",
    "create_auth_storage",
    "delete_file_if_exists",
    "get_auth_file",
]
