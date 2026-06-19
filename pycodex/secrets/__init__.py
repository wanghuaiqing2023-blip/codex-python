"""Python port surface for Rust ``codex-secrets/src/lib.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from pathlib import Path
from typing import Protocol

from pycodex.git_utils import get_git_repo_root

from .sanitizer import redact_secrets

KEYRING_SERVICE = "codex"


class SecretsLocalBackendPendingError(NotImplementedError):
    """Raised when the pending ``codex-secrets/src/local.rs`` backend is needed."""


@dataclass(frozen=True, order=True)
class SecretName:
    value: str

    def __post_init__(self) -> None:
        trimmed = str(self.value).strip()
        if not trimmed:
            raise ValueError("secret name must not be empty")
        if not all(ch.isascii() and (ch.isupper() or ch.isdigit() or ch == "_") for ch in trimmed):
            raise ValueError("secret name must contain only A-Z, 0-9, or _")
        object.__setattr__(self, "value", trimmed)

    @classmethod
    def new(cls, raw: str) -> "SecretName":
        return cls(raw)

    def as_str(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class SecretScope:
    kind: str
    environment_id: str | None = None

    @classmethod
    def global_scope(cls) -> "SecretScope":
        return cls("global")

    @classmethod
    def environment(cls, environment_id: str) -> "SecretScope":
        trimmed = str(environment_id).strip()
        if not trimmed:
            raise ValueError("environment id must not be empty")
        return cls("environment", trimmed)

    def canonical_key(self, name: SecretName) -> str:
        if self.kind == "global":
            return f"global/{name.as_str()}"
        if self.kind == "environment" and self.environment_id is not None:
            return f"env/{self.environment_id}/{name.as_str()}"
        raise ValueError(f"unknown secret scope kind: {self.kind}")


SecretScope.Global = SecretScope.global_scope()  # type: ignore[attr-defined]


@dataclass(frozen=True)
class SecretListEntry:
    scope: SecretScope
    name: SecretName


class SecretsBackendKind(str, Enum):
    LOCAL = "local"

    @classmethod
    def default(cls) -> "SecretsBackendKind":
        return cls.LOCAL


class SecretsBackend(Protocol):
    def set(self, scope: SecretScope, name: SecretName, value: str) -> None: ...

    def get(self, scope: SecretScope, name: SecretName) -> str | None: ...

    def delete(self, scope: SecretScope, name: SecretName) -> bool: ...

    def list(self, scope_filter: SecretScope | None = None) -> list[SecretListEntry]: ...


class SecretsManager:
    def __init__(self, backend: SecretsBackend) -> None:
        self.backend = backend

    @classmethod
    def new(cls, codex_home: Path | str, backend_kind: SecretsBackendKind = SecretsBackendKind.LOCAL) -> "SecretsManager":
        return cls(_new_local_backend(Path(codex_home), backend_kind, keyring_store=None))

    @classmethod
    def new_with_keyring_store(
        cls,
        codex_home: Path | str,
        backend_kind: SecretsBackendKind,
        keyring_store: object,
    ) -> "SecretsManager":
        return cls(_new_local_backend(Path(codex_home), backend_kind, keyring_store=keyring_store))

    def set(self, scope: SecretScope, name: SecretName, value: str) -> None:
        self.backend.set(scope, name, value)

    def get(self, scope: SecretScope, name: SecretName) -> str | None:
        return self.backend.get(scope, name)

    def delete(self, scope: SecretScope, name: SecretName) -> bool:
        return self.backend.delete(scope, name)

    def list(self, scope_filter: SecretScope | None = None) -> list[SecretListEntry]:
        return self.backend.list(scope_filter)


def environment_id_from_cwd(cwd: Path | str) -> str:
    cwd_path = Path(cwd)
    repo_root = get_git_repo_root(cwd_path)
    if repo_root is not None:
        name = repo_root.name.strip()
        if name:
            return name
    canonical = _canonical_string(cwd_path)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"cwd-{digest[:12]}"


def compute_keyring_account(codex_home: Path | str) -> str:
    canonical = _canonical_string(Path(codex_home))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"secrets|{digest[:16]}"


def keyring_service() -> str:
    return KEYRING_SERVICE


def _canonical_string(path: Path) -> str:
    try:
        return str(path.resolve(strict=True))
    except OSError:
        return str(path)


def _new_local_backend(
    codex_home: Path,
    backend_kind: SecretsBackendKind,
    *,
    keyring_store: object | None,
) -> SecretsBackend:
    kind = SecretsBackendKind(backend_kind)
    if kind is SecretsBackendKind.LOCAL:
        try:
            from .local import LocalSecretsBackend
        except ModuleNotFoundError as exc:
            raise SecretsLocalBackendPendingError(
                "codex-secrets/src/local.rs is not ported yet"
            ) from exc
        if keyring_store is None:
            return LocalSecretsBackend.new(codex_home)
        return LocalSecretsBackend.new(codex_home, keyring_store)
    raise ValueError(f"unsupported secrets backend kind: {backend_kind}")


__all__ = [
    "KEYRING_SERVICE",
    "SecretListEntry",
    "SecretName",
    "SecretScope",
    "SecretsBackend",
    "SecretsBackendKind",
    "SecretsLocalBackendPendingError",
    "SecretsManager",
    "compute_keyring_account",
    "environment_id_from_cwd",
    "keyring_service",
    "redact_secrets",
]

try:
    from .local import LocalSecretsBackend
except ModuleNotFoundError:
    pass
else:
    __all__.append("LocalSecretsBackend")
