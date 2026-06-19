"""Local secrets backend for Rust ``codex-secrets/src/local.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from typing import Mapping

from pycodex.keyring_store import CredentialStoreError, DefaultKeyringStore, KeyringStore

from . import (
    SecretListEntry,
    SecretName,
    SecretScope,
    compute_keyring_account,
    keyring_service,
)

SECRETS_VERSION = 1
LOCAL_SECRETS_FILENAME = "local.age"
_FORMAT_PREFIX = b"pycodex-secrets-v1\n"


@dataclass(frozen=True)
class SecretsFile:
    version: int = SECRETS_VERSION
    secrets: dict[str, str] = field(default_factory=dict)

    @classmethod
    def new_empty(cls) -> "SecretsFile":
        return cls(version=SECRETS_VERSION, secrets={})

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "SecretsFile":
        version = int(value.get("version") or 0)
        secrets_raw = value.get("secrets") or {}
        if not isinstance(secrets_raw, Mapping):
            raise ValueError("secrets must be an object")
        secrets = {str(key): str(secret) for key, secret in secrets_raw.items()}
        if version == 0:
            version = SECRETS_VERSION
        if version > SECRETS_VERSION:
            raise ValueError(
                f"secrets file version {version} is newer than supported version {SECRETS_VERSION}"
            )
        return cls(version=version, secrets=dict(sorted(secrets.items())))

    def to_mapping(self) -> dict[str, object]:
        return {"version": int(self.version), "secrets": dict(sorted(self.secrets.items()))}


class LocalSecretsBackend:
    def __init__(self, codex_home: Path | str, keyring_store: KeyringStore | None = None) -> None:
        self.codex_home = Path(codex_home)
        self.keyring_store = keyring_store if keyring_store is not None else DefaultKeyringStore()

    @classmethod
    def new(cls, codex_home: Path | str, keyring_store: KeyringStore | None = None) -> "LocalSecretsBackend":
        return cls(codex_home, keyring_store)

    def set(self, scope: SecretScope, name: SecretName, value: str) -> None:
        if not value:
            raise ValueError("secret value must not be empty")
        canonical_key = scope.canonical_key(name)
        secrets_file = self.load_file()
        secrets_file.secrets[canonical_key] = str(value)
        self.save_file(secrets_file)

    def get(self, scope: SecretScope, name: SecretName) -> str | None:
        canonical_key = scope.canonical_key(name)
        return self.load_file().secrets.get(canonical_key)

    def delete(self, scope: SecretScope, name: SecretName) -> bool:
        canonical_key = scope.canonical_key(name)
        secrets_file = self.load_file()
        removed = canonical_key in secrets_file.secrets
        if removed:
            del secrets_file.secrets[canonical_key]
            self.save_file(secrets_file)
        return removed

    def list(self, scope_filter: SecretScope | None = None) -> list[SecretListEntry]:
        entries: list[SecretListEntry] = []
        for canonical_key in self.load_file().secrets:
            entry = parse_canonical_key(canonical_key)
            if entry is None:
                continue
            if scope_filter is not None and entry.scope != scope_filter:
                continue
            entries.append(entry)
        return entries

    def secrets_dir(self) -> Path:
        return self.codex_home / "secrets"

    def secrets_path(self) -> Path:
        return self.secrets_dir() / LOCAL_SECRETS_FILENAME

    def load_file(self) -> SecretsFile:
        path = self.secrets_path()
        if not path.exists():
            return SecretsFile.new_empty()
        try:
            ciphertext = path.read_bytes()
        except OSError as exc:
            raise OSError(f"failed to read secrets file at {path}") from exc
        passphrase = self.load_or_create_passphrase()
        plaintext = decrypt_with_passphrase(ciphertext, passphrase)
        try:
            parsed = json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"failed to deserialize decrypted secrets file at {path}") from exc
        return SecretsFile.from_mapping(parsed)

    def save_file(self, secrets_file: SecretsFile) -> None:
        directory = self.secrets_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(f"failed to create secrets dir {directory}") from exc
        passphrase = self.load_or_create_passphrase()
        plaintext = json.dumps(secrets_file.to_mapping(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ciphertext = encrypt_with_passphrase(plaintext, passphrase)
        write_file_atomically(self.secrets_path(), ciphertext)

    def load_or_create_passphrase(self) -> str:
        account = compute_keyring_account(self.codex_home)
        try:
            loaded = self.keyring_store.load(keyring_service(), account)
        except CredentialStoreError as exc:
            raise RuntimeError(f"failed to load secrets key from keyring for {account}: {exc.message()}") from exc
        except Exception as exc:
            raise RuntimeError(f"failed to load secrets key from keyring for {account}: {exc}") from exc
        if loaded is not None:
            return loaded
        generated = generate_passphrase()
        try:
            self.keyring_store.save(keyring_service(), account, generated)
        except CredentialStoreError as exc:
            raise RuntimeError(f"failed to persist secrets key in keyring: {exc.message()}") from exc
        except Exception as exc:
            raise RuntimeError(f"failed to persist secrets key in keyring: {exc}") from exc
        return generated


def write_file_atomically(path: Path | str, contents: bytes) -> None:
    target = Path(path)
    directory = target.parent
    if not str(directory):
        raise ValueError(f"failed to compute parent directory for secrets file at {target}")
    directory.mkdir(parents=True, exist_ok=True)
    nonce = time.time_ns()
    tmp_path = directory / f".{LOCAL_SECRETS_FILENAME}.tmp-{os.getpid()}-{nonce}"
    try:
        with tmp_path.open("xb") as tmp_file:
            tmp_file.write(contents)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, target)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def generate_passphrase() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def encrypt_with_passphrase(plaintext: bytes, passphrase: str) -> bytes:
    key = _derive_key(passphrase)
    nonce = os.urandom(16)
    keystream = _keystream(key, nonce, len(plaintext))
    ciphertext = bytes(byte ^ mask for byte, mask in zip(plaintext, keystream))
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    payload = {
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    return _FORMAT_PREFIX + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def decrypt_with_passphrase(ciphertext: bytes, passphrase: str) -> bytes:
    if not ciphertext.startswith(_FORMAT_PREFIX):
        raise ValueError("failed to decrypt secrets file")
    key = _derive_key(passphrase)
    try:
        payload = json.loads(ciphertext[len(_FORMAT_PREFIX) :].decode("utf-8"))
        nonce = base64.b64decode(payload["nonce"])
        tag = base64.b64decode(payload["tag"])
        encrypted = base64.b64decode(payload["ciphertext"])
    except Exception as exc:
        raise ValueError("failed to decrypt secrets file") from exc
    expected = hmac.new(key, nonce + encrypted, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("failed to decrypt secrets file")
    keystream = _keystream(key, nonce, len(encrypted))
    return bytes(byte ^ mask for byte, mask in zip(encrypted, keystream))


def parse_canonical_key(canonical_key: str) -> SecretListEntry | None:
    parts = canonical_key.split("/")
    if len(parts) == 2 and parts[0] == "global":
        try:
            return SecretListEntry(SecretScope.Global, SecretName.new(parts[1]))
        except ValueError:
            return None
    if len(parts) == 3 and parts[0] == "env":
        try:
            return SecretListEntry(SecretScope.environment(parts[1]), SecretName.new(parts[2]))
        except ValueError:
            return None
    return None


def _derive_key(passphrase: str) -> bytes:
    return hashlib.sha256(passphrase.encode("utf-8")).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        blocks.append(hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest())
        counter += 1
    return b"".join(blocks)[:length]


__all__ = [
    "LOCAL_SECRETS_FILENAME",
    "SECRETS_VERSION",
    "LocalSecretsBackend",
    "SecretsFile",
    "decrypt_with_passphrase",
    "encrypt_with_passphrase",
    "generate_passphrase",
    "parse_canonical_key",
    "write_file_atomically",
]
