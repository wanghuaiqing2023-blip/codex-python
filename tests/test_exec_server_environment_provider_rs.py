from __future__ import annotations

from pycodex.exec_server import (
    LOCAL_ENVIRONMENT_ID,
    REMOTE_ENVIRONMENT_ID,
    DefaultEnvironmentProvider,
    EnvironmentDefault,
    normalize_exec_server_url,
)


def test_default_provider_requests_local_environment_when_url_is_missing() -> None:
    # Rust crate/module/test:
    # codex-exec-server/src/environment_provider.rs
    # default_provider_requests_local_environment_when_url_is_missing.
    snapshot = DefaultEnvironmentProvider.new(None).snapshot()
    environments = dict(snapshot.environments)

    assert snapshot.include_local is True
    assert LOCAL_ENVIRONMENT_ID not in environments
    assert REMOTE_ENVIRONMENT_ID not in environments
    assert snapshot.default == EnvironmentDefault.environment_id_value(LOCAL_ENVIRONMENT_ID)


def test_default_provider_requests_local_environment_when_url_is_empty() -> None:
    # Rust test: default_provider_requests_local_environment_when_url_is_empty.
    snapshot = DefaultEnvironmentProvider.new("").snapshot()
    environments = dict(snapshot.environments)

    assert snapshot.include_local is True
    assert LOCAL_ENVIRONMENT_ID not in environments
    assert REMOTE_ENVIRONMENT_ID not in environments
    assert snapshot.default == EnvironmentDefault.environment_id_value(LOCAL_ENVIRONMENT_ID)


def test_default_provider_omits_local_environment_for_none_value() -> None:
    # Rust test: default_provider_omits_local_environment_for_none_value.
    snapshot = DefaultEnvironmentProvider.new("none").snapshot()
    environments = dict(snapshot.environments)

    assert snapshot.include_local is False
    assert LOCAL_ENVIRONMENT_ID not in environments
    assert REMOTE_ENVIRONMENT_ID not in environments
    assert snapshot.default == EnvironmentDefault.disabled()


def test_default_provider_adds_remote_environment_for_websocket_url() -> None:
    # Rust test: default_provider_adds_remote_environment_for_websocket_url.
    snapshot = DefaultEnvironmentProvider.new("ws://127.0.0.1:8765").snapshot()
    environments = dict(snapshot.environments)

    assert snapshot.include_local is False
    assert LOCAL_ENVIRONMENT_ID not in environments
    remote_environment = environments[REMOTE_ENVIRONMENT_ID]
    assert remote_environment.is_remote() is True
    assert remote_environment.exec_server_url() == "ws://127.0.0.1:8765"
    assert snapshot.default == EnvironmentDefault.environment_id_value(REMOTE_ENVIRONMENT_ID)


def test_default_provider_normalizes_exec_server_url() -> None:
    # Rust test: default_provider_normalizes_exec_server_url.
    snapshot = DefaultEnvironmentProvider.new(" ws://127.0.0.1:8765 ").snapshot()
    environments = dict(snapshot.environments)

    assert environments[REMOTE_ENVIRONMENT_ID].exec_server_url() == "ws://127.0.0.1:8765"


def test_normalize_exec_server_url_matches_rust_helper() -> None:
    # Rust helper: normalize_exec_server_url.
    assert normalize_exec_server_url(None) == (None, False)
    assert normalize_exec_server_url(" ") == (None, False)
    assert normalize_exec_server_url("NoNe") == (None, True)
    assert normalize_exec_server_url(" ws://127.0.0.1:9 ") == ("ws://127.0.0.1:9", False)
