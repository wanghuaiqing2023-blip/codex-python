"""Port of Rust ``codex-keyring-store``.

Rust source:
- ``codex/codex-rs/keyring-store/src/lib.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CredentialStoreError(Exception):
    def __init__(self, error: BaseException | str) -> None:
        self.error = error
        super().__init__(str(error))

    @classmethod
    def new(cls, error: BaseException | str) -> "CredentialStoreError":
        return cls(error)

    def message(self) -> str:
        return str(self.error)

    def into_error(self) -> BaseException | str:
        return self.error


class KeyringStore(Protocol):
    def load(self, service: str, account: str) -> str | None:
        ...

    def save(self, service: str, account: str, value: str) -> None:
        ...

    def delete(self, service: str, account: str) -> bool:
        ...


@dataclass(frozen=True)
class DefaultKeyringStore:
    """System keyring-backed credential store."""

    def load(self, service: str, account: str) -> str | None:
        keyring = _import_keyring()
        try:
            return keyring.get_password(service, account)
        except Exception as exc:
            if _is_no_entry_error(exc):
                return None
            raise CredentialStoreError.new(exc) from exc

    def save(self, service: str, account: str, value: str) -> None:
        keyring = _import_keyring()
        try:
            keyring.set_password(service, account, value)
        except Exception as exc:
            raise CredentialStoreError.new(exc) from exc

    def delete(self, service: str, account: str) -> bool:
        keyring = _import_keyring()
        try:
            keyring.delete_password(service, account)
            return True
        except Exception as exc:
            if _is_no_entry_error(exc):
                return False
            raise CredentialStoreError.new(exc) from exc


def _import_keyring():
    try:
        import keyring  # type: ignore[import-not-found]
    except Exception as exc:
        raise CredentialStoreError.new("Python keyring backend is not available") from exc
    return keyring


def _is_no_entry_error(error: BaseException | str) -> bool:
    if isinstance(error, str):
        return error.lower() in {"noentry", "no entry", "no_entry"}
    name = error.__class__.__name__.lower()
    return "notfound" in name or "noentry" in name or "passworddeleteerror" in name


__all__ = [
    "CredentialStoreError",
    "DefaultKeyringStore",
    "KeyringStore",
]
