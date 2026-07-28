"""Port of Rust ``codex_keyring_store::tests``."""

from __future__ import annotations

from threading import RLock

from . import CredentialStoreError


class KeyringNoEntryError(Exception):
    """Portable representation of ``keyring::Error::NoEntry``."""


class _MockCredential:
    def __init__(self) -> None:
        self._secret: str | None = None
        self._error: BaseException | str | None = None
        self._lock = RLock()

    def get_password(self) -> str:
        with self._lock:
            self._raise_pending_error()
            if self._secret is None:
                raise KeyringNoEntryError
            return self._secret

    def set_password(self, value: str) -> None:
        with self._lock:
            self._raise_pending_error()
            self._secret = value

    def delete_credential(self) -> None:
        with self._lock:
            self._raise_pending_error()
            if self._secret is None:
                raise KeyringNoEntryError
            self._secret = None

    def set_error(self, error: BaseException | str) -> None:
        with self._lock:
            self._error = error

    def _raise_pending_error(self) -> None:
        error = self._error
        self._error = None
        if error is not None:
            if isinstance(error, BaseException):
                raise error
            raise RuntimeError(error)


class MockKeyringStore:
    """Account-scoped mock matching Rust ``tests::MockKeyringStore``."""

    def __init__(self) -> None:
        self._credentials: dict[str, _MockCredential] = {}
        self._lock = RLock()

    def credential(self, account: str) -> _MockCredential:
        with self._lock:
            credential = self._credentials.get(account)
            if credential is None:
                credential = _MockCredential()
                self._credentials[account] = credential
            return credential

    def saved_value(self, account: str) -> str | None:
        with self._lock:
            credential = self._credentials.get(account)
        if credential is None:
            return None
        try:
            return credential.get_password()
        except Exception:
            return None

    def set_error(self, account: str, error: BaseException | str) -> None:
        self.credential(account).set_error(error)

    def contains(self, account: str) -> bool:
        with self._lock:
            return account in self._credentials

    def load(self, service: str, account: str) -> str | None:
        del service
        with self._lock:
            credential = self._credentials.get(account)
        if credential is None:
            return None
        try:
            return credential.get_password()
        except KeyringNoEntryError:
            return None
        except Exception as error:
            raise CredentialStoreError.new(error) from error

    def save(self, service: str, account: str, value: str) -> None:
        del service
        try:
            self.credential(account).set_password(value)
        except Exception as error:
            raise CredentialStoreError.new(error) from error

    def delete(self, service: str, account: str) -> bool:
        del service
        with self._lock:
            credential = self._credentials.get(account)
        if credential is None:
            return False
        try:
            credential.delete_credential()
            removed = True
        except KeyringNoEntryError:
            removed = False
        except Exception as error:
            raise CredentialStoreError.new(error) from error
        with self._lock:
            if self._credentials.get(account) is credential:
                del self._credentials[account]
        return removed


__all__ = ["KeyringNoEntryError", "MockKeyringStore"]
