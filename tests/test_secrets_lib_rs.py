"""Prepared parity tests for Rust ``codex-secrets/src/lib.rs``.

Pytest is deferred until the full ``codex-secrets`` crate is functionally
complete, per the crate-level porting workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path

import pytest

from pycodex.secrets import (
    SecretListEntry,
    SecretName,
    SecretScope,
    SecretsBackendKind,
    SecretsManager,
    compute_keyring_account,
    environment_id_from_cwd,
    keyring_service,
)


def test_secret_name_new_trims_and_validates_allowed_characters() -> None:
    # Rust source: SecretName::new trims and permits only A-Z, 0-9, or _.
    assert SecretName.new("  GITHUB_TOKEN_1 ").as_str() == "GITHUB_TOKEN_1"
    with pytest.raises(ValueError, match="must not be empty"):
        SecretName.new(" ")
    with pytest.raises(ValueError, match="A-Z, 0-9, or _"):
        SecretName.new("github-token")


def test_secret_scope_environment_and_canonical_keys() -> None:
    # Rust source: SecretScope::canonical_key formats stable map identifiers.
    name = SecretName.new("API_KEY")

    assert SecretScope.Global.canonical_key(name) == "global/API_KEY"
    assert SecretScope.environment(" prod ").canonical_key(name) == "env/prod/API_KEY"
    with pytest.raises(ValueError, match="environment id must not be empty"):
        SecretScope.environment(" ")


def test_environment_id_fallback_has_cwd_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust source: environment_id_fallback_has_cwd_prefix.
    monkeypatch.setattr("pycodex.secrets.get_git_repo_root", lambda _cwd: None)
    canonical = str(tmp_path.resolve())
    expected = "cwd-" + hashlib.sha256(canonical.encode()).hexdigest()[:12]

    assert environment_id_from_cwd(tmp_path) == expected


def test_environment_id_uses_git_repo_basename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust source: environment_id_from_cwd prefers a non-empty git repo root basename.
    repo = tmp_path / "repo-name"
    repo.mkdir()
    monkeypatch.setattr("pycodex.secrets.get_git_repo_root", lambda _cwd: repo)

    assert environment_id_from_cwd(tmp_path / "repo-name" / "subdir") == "repo-name"


def test_compute_keyring_account_uses_codex_service_hash(tmp_path: Path) -> None:
    # Rust source: compute_keyring_account hashes canonical codex_home and keyring_service returns "codex".
    canonical = str(tmp_path.resolve())
    expected = "secrets|" + hashlib.sha256(canonical.encode()).hexdigest()[:16]

    assert compute_keyring_account(tmp_path) == expected
    assert keyring_service() == "codex"


def test_secrets_manager_delegates_to_backend() -> None:
    # Rust source: SecretsManager methods delegate to the selected backend.
    scope = SecretScope.Global
    name = SecretName.new("GITHUB_TOKEN")
    backend = FakeBackend()
    manager = SecretsManager(backend)

    manager.set(scope, name, "token-1")

    assert manager.get(scope, name) == "token-1"
    assert manager.list(None) == [SecretListEntry(scope, name)]
    assert manager.delete(scope, name) is True
    assert manager.get(scope, name) is None


def test_local_backend_constructor_returns_manager_after_local_rs_port(tmp_path: Path) -> None:
    # Rust source: SecretsManager::new constructs a LocalSecretsBackend for the local backend kind.
    manager = SecretsManager.new(tmp_path, SecretsBackendKind.LOCAL)

    assert isinstance(manager, SecretsManager)


@dataclass
class FakeBackend:
    values: dict[str, str] = field(default_factory=dict)

    def set(self, scope: SecretScope, name: SecretName, value: str) -> None:
        self.values[scope.canonical_key(name)] = value

    def get(self, scope: SecretScope, name: SecretName) -> str | None:
        return self.values.get(scope.canonical_key(name))

    def delete(self, scope: SecretScope, name: SecretName) -> bool:
        return self.values.pop(scope.canonical_key(name), None) is not None

    def list(self, scope_filter: SecretScope | None = None) -> list[SecretListEntry]:
        entries: list[SecretListEntry] = []
        for key in self.values:
            if key.startswith("global/"):
                entry = SecretListEntry(SecretScope.Global, SecretName.new(key.removeprefix("global/")))
            else:
                _prefix, env_id, name = key.split("/", 2)
                entry = SecretListEntry(SecretScope.environment(env_id), SecretName.new(name))
            if scope_filter is None or entry.scope == scope_filter:
                entries.append(entry)
        return entries
