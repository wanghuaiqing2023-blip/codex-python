"""Rust-derived tests for codex-exec-server/src/environment.rs."""

from __future__ import annotations

import pytest

from pycodex.exec_server import (
    LOCAL_ENVIRONMENT_ID,
    REMOTE_ENVIRONMENT_ID,
    Environment,
    EnvironmentDefault,
    EnvironmentManager,
    EnvironmentProviderSnapshot,
    ExecServerError,
    ExecServerRuntimePaths,
    LocalFileSystem,
)


def _runtime_paths(tmp_path) -> ExecServerRuntimePaths:
    return ExecServerRuntimePaths.new(tmp_path / "codex", None)


def test_create_local_environment_does_not_connect(tmp_path) -> None:
    # Rust: codex-exec-server/src/environment.rs test
    # `create_local_environment_does_not_connect`.
    # Contract: local Environment construction records no exec-server URL and
    # does not create a remote transport.
    environment = Environment.create(None, _runtime_paths(tmp_path))

    assert environment.exec_server_url() is None
    assert environment.is_remote() is False
    assert environment.local_runtime_paths == _runtime_paths(tmp_path)


def test_environment_manager_normalizes_empty_url(tmp_path) -> None:
    # Rust: environment.rs test `environment_manager_normalizes_empty_url`.
    # Contract: an empty legacy URL selects the local default environment and
    # caches the same local environment object for default/local lookup.
    manager = EnvironmentManager.create_for_tests("", _runtime_paths(tmp_path))

    environment = manager.default_environment()
    assert manager.default_environment_id() == LOCAL_ENVIRONMENT_ID
    assert environment is manager.get_environment(LOCAL_ENVIRONMENT_ID)
    assert environment is manager.try_local_environment()
    assert manager.get_environment(REMOTE_ENVIRONMENT_ID) is None
    assert environment is not None
    assert environment.is_remote() is False


def test_disabled_environment_manager_has_no_default_or_local_environment() -> None:
    # Rust: environment.rs test
    # `disabled_environment_manager_has_no_default_or_local_environment`.
    # Contract: the explicit empty manager exposes no default, local, or remote
    # environment.
    manager = EnvironmentManager.without_environments()

    assert manager.default_environment() is None
    assert manager.default_environment_id() is None
    assert manager.try_local_environment() is None
    assert manager.get_environment(LOCAL_ENVIRONMENT_ID) is None
    assert manager.get_environment(REMOTE_ENVIRONMENT_ID) is None


def test_environment_manager_reports_remote_url(tmp_path) -> None:
    # Rust: environment.rs test `environment_manager_reports_remote_url`.
    # Contract: a websocket URL creates the remote default and omits the local
    # environment in the legacy provider path.
    manager = EnvironmentManager.create_for_tests("ws://127.0.0.1:8765", _runtime_paths(tmp_path))

    environment = manager.default_environment()
    assert manager.default_environment_id() == REMOTE_ENVIRONMENT_ID
    assert environment is manager.get_environment(REMOTE_ENVIRONMENT_ID)
    assert environment is not None
    assert environment.is_remote() is True
    assert environment.exec_server_url() == "ws://127.0.0.1:8765"
    assert manager.get_environment(LOCAL_ENVIRONMENT_ID) is None
    assert manager.try_local_environment() is None


def test_environment_manager_builds_from_snapshot_and_orders_default_first(tmp_path) -> None:
    # Rust: environment.rs tests `environment_manager_builds_from_snapshot`
    # and `environment_manager_uses_explicit_provider_default`.
    # Contract: provider snapshots create named environments, include local
    # when requested, and return default_environment_ids with default first.
    remote = Environment.create_for_tests("ws://127.0.0.1:8765")
    manager = EnvironmentManager.from_snapshot(
        EnvironmentProviderSnapshot(
            environments=[("devbox", remote)],
            default=EnvironmentDefault.environment_id_value("devbox"),
            include_local=True,
        ),
        _runtime_paths(tmp_path),
    )

    assert manager.default_environment_id() == "devbox"
    assert manager.default_environment() is remote
    assert manager.get_environment("devbox") is remote
    assert manager.get_environment(LOCAL_ENVIRONMENT_ID) is manager.try_local_environment()
    assert manager.default_environment_ids() == ["devbox", LOCAL_ENVIRONMENT_ID]


def test_environment_manager_disables_provider_default(tmp_path) -> None:
    # Rust: environment.rs test `environment_manager_disables_provider_default`.
    # Contract: a disabled provider default keeps included local available but
    # leaves default_environment unset.
    manager = EnvironmentManager.from_snapshot(
        EnvironmentProviderSnapshot(
            environments=[("devbox", Environment.create_for_tests("ws://127.0.0.1:8765"))],
            default=EnvironmentDefault.disabled(),
            include_local=True,
        ),
        _runtime_paths(tmp_path),
    )

    assert manager.default_environment_id() is None
    assert manager.default_environment() is None
    assert manager.try_local_environment() is manager.get_environment(LOCAL_ENVIRONMENT_ID)


def test_environment_manager_rejects_invalid_snapshot_defaults_and_ids(tmp_path) -> None:
    # Rust: environment.rs tests for empty id, provider-supplied local id,
    # duplicate id, and unknown provider default.
    runtime_paths = _runtime_paths(tmp_path)
    cases = [
        (
            EnvironmentProviderSnapshot(
                environments=[("", Environment.default_for_tests())],
                default=EnvironmentDefault.disabled(),
                include_local=False,
            ),
            "exec-server protocol error: environment id cannot be empty",
        ),
        (
            EnvironmentProviderSnapshot(
                environments=[(LOCAL_ENVIRONMENT_ID, Environment.default_for_tests())],
                default=EnvironmentDefault.disabled(),
                include_local=False,
            ),
            "exec-server protocol error: environment id `local` is reserved for EnvironmentManager",
        ),
        (
            EnvironmentProviderSnapshot(
                environments=[("devbox", Environment.default_for_tests()), ("devbox", Environment.default_for_tests())],
                default=EnvironmentDefault.disabled(),
                include_local=False,
            ),
            "exec-server protocol error: environment id `devbox` is duplicated",
        ),
        (
            EnvironmentProviderSnapshot(
                environments=[("devbox", Environment.default_for_tests())],
                default=EnvironmentDefault.environment_id_value("missing"),
                include_local=True,
            ),
            "exec-server protocol error: default environment `missing` is not configured",
        ),
    ]

    for snapshot, expected in cases:
        with pytest.raises(ExecServerError) as exc_info:
            EnvironmentManager.from_snapshot(snapshot, runtime_paths)
        assert str(exc_info.value) == expected


def test_environment_manager_omits_default_provider_local_lookup_when_default_disabled(tmp_path) -> None:
    # Rust: environment.rs test
    # `environment_manager_omits_default_provider_local_lookup_when_default_disabled`.
    # Contract: legacy URL `none` disables both default and local lookup.
    manager = EnvironmentManager.create_for_tests("none", _runtime_paths(tmp_path))

    assert manager.default_environment() is None
    assert manager.default_environment_id() is None
    assert manager.get_environment(LOCAL_ENVIRONMENT_ID) is None
    assert manager.get_environment(REMOTE_ENVIRONMENT_ID) is None
    assert manager.try_local_environment() is None


def test_environment_manager_carries_local_runtime_paths(tmp_path) -> None:
    # Rust: environment.rs test `environment_manager_carries_local_runtime_paths`.
    # Contract: local environments retain the runtime paths used to construct
    # sandbox-capable filesystem helpers.
    runtime_paths = _runtime_paths(tmp_path)
    manager = EnvironmentManager.create_for_tests(None, runtime_paths)
    environment = manager.try_local_environment()

    assert environment is not None
    assert environment.local_runtime_paths == runtime_paths
    assert isinstance(environment.get_filesystem(), LocalFileSystem)


def test_environment_manager_upserts_named_remote_environment() -> None:
    # Rust: environment.rs test `environment_manager_upserts_named_remote_environment`.
    # Contract: upsert adds or replaces named remote environments without
    # changing the manager default.
    manager = EnvironmentManager.without_environments()

    manager.upsert_environment("executor-a", " ws://127.0.0.1:8765 ")
    first = manager.get_environment("executor-a")
    assert first is not None
    assert first.is_remote() is True
    assert first.exec_server_url() == "ws://127.0.0.1:8765"
    assert manager.default_environment_id() is None

    manager.upsert_environment("executor-a", "ws://127.0.0.1:9876")
    second = manager.get_environment("executor-a")
    assert second is not None
    assert second.is_remote() is True
    assert second.exec_server_url() == "ws://127.0.0.1:9876"
    assert second is not first


def test_environment_manager_rejects_invalid_upsert_environment() -> None:
    # Rust: environment.rs tests `environment_manager_rejects_empty_remote_environment_url`
    # plus the disabled remote URL branch in `upsert_environment`.
    manager = EnvironmentManager.without_environments()

    with pytest.raises(ExecServerError) as empty_id:
        manager.upsert_environment("", "ws://127.0.0.1:8765")
    assert str(empty_id.value) == "exec-server protocol error: environment id cannot be empty"

    with pytest.raises(ExecServerError) as empty_url:
        manager.upsert_environment("executor-a", "")
    assert str(empty_url.value) == "exec-server protocol error: remote environment requires an exec-server url"

    with pytest.raises(ExecServerError) as disabled_url:
        manager.upsert_environment("executor-a", "none")
    assert str(disabled_url.value) == (
        "exec-server protocol error: remote environment cannot use disabled exec-server url"
    )
