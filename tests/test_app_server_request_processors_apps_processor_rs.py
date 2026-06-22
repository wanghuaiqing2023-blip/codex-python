"""Parity tests for ``codex-app-server/src/request_processors/apps_processor.rs``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from pycodex.app_server.request_processors_apps_processor import (
    AccessibleConnectorsStatus,
    AppsRequestProcessor,
    AppsRequestProcessorError,
    merge_loaded_apps,
    paginate_apps,
    parse_apps_cursor,
    should_send_app_list_updated_notification,
)
from pycodex.app_server_protocol import AppInfo, AppsListParams, AppsListResponse


def app(app_id: str, *, accessible: bool = False, enabled: bool = True) -> AppInfo:
    return AppInfo(id=app_id, name=app_id.title(), is_accessible=accessible, is_enabled=enabled)


@dataclass
class FakeFeatures:
    apps_enabled: bool = True
    assigned: dict[str, bool] = field(default_factory=dict)

    def apps_enabled_for_auth(self, uses_backend: bool) -> bool:
        return self.apps_enabled and uses_backend

    def set_enabled(self, feature: str, enabled: bool) -> None:
        self.assigned[feature] = enabled
        self.apps_enabled = enabled


@dataclass
class FakeAuth:
    backend: bool = True

    def uses_codex_backend(self) -> bool:
        return self.backend


@dataclass
class FakeAuthManager:
    auth_value: FakeAuth | None = field(default_factory=FakeAuth)

    async def auth(self) -> FakeAuth | None:
        return self.auth_value


@dataclass
class FakeConfigManager:
    config: object
    fallback_cwds: list[Path | None] = field(default_factory=list)

    async def load_latest_config(self, fallback_cwd: Path | None) -> object:
        self.fallback_cwds.append(fallback_cwd)
        return self.config


@dataclass
class FakeThread:
    cwd: Path
    apps_enabled: bool = True

    async def config_snapshot(self) -> object:
        return SimpleNamespace(cwd=self.cwd)

    def enabled(self, feature: str) -> bool:
        assert feature == "apps"
        return self.apps_enabled


@dataclass
class FakeThreadManager:
    threads: dict[str, FakeThread] = field(default_factory=dict)

    async def get_thread(self, thread_id: str) -> FakeThread:
        if thread_id not in self.threads:
            raise KeyError(thread_id)
        return self.threads[thread_id]

    def environment_manager(self) -> object:
        return SimpleNamespace(name="env")


@dataclass
class FakeOutgoing:
    results: list[tuple[object, object]] = field(default_factory=list)
    notifications: list[object] = field(default_factory=list)

    async def send_result(self, request_id: object, response: object) -> None:
        self.results.append((request_id, response))

    async def send_server_notification(self, notification: object) -> None:
        self.notifications.append(notification)


@dataclass
class FakeLoader:
    cached_accessible_value: tuple[AppInfo, ...] | None = None
    cached_all_value: tuple[AppInfo, ...] | None = None
    accessible_value: AccessibleConnectorsStatus = field(default_factory=lambda: AccessibleConnectorsStatus(()))
    all_value: tuple[AppInfo, ...] = ()
    load_accessible_calls: list[bool] = field(default_factory=list)

    async def cached_accessible(self, _config: object) -> tuple[AppInfo, ...] | None:
        return self.cached_accessible_value

    async def cached_all(self, _config: object) -> tuple[AppInfo, ...] | None:
        return self.cached_all_value

    async def load_accessible(
        self,
        _config: object,
        force_refetch: bool,
        _environment_manager: object,
    ) -> AccessibleConnectorsStatus:
        self.load_accessible_calls.append(force_refetch)
        return self.accessible_value

    async def load_all(self, _config: object, _force_refetch: bool) -> tuple[AppInfo, ...]:
        return self.all_value


def test_parse_apps_cursor_maps_invalid_values_to_invalid_request() -> None:
    # Rust: apps_list_response rejects non-numeric cursors with invalid_request.
    try:
        parse_apps_cursor("nope")
    except AppsRequestProcessorError as exc:
        assert exc.error.code == -32600
        assert exc.error.message == "invalid cursor: nope"
    else:
        raise AssertionError("expected invalid cursor")


def test_paginate_apps_matches_rust_limit_and_next_cursor() -> None:
    # Rust: paginate_apps clamps limit to at least one and returns end as next cursor.
    response = paginate_apps((app("a"), app("b"), app("c")), start=1, limit=1)

    assert response == AppsListResponse(data=(app("b"),), next_cursor="2")


def test_merge_loaded_apps_marks_accessible_directory_items_and_appends_missing() -> None:
    # Rust: merge_loaded_apps delegates to connector merge with all-loaded state.
    merged = merge_loaded_apps(
        (app("calendar"), app("drive")),
        (app("drive", accessible=True), app("mail", accessible=True)),
    )

    assert [(item.id, item.is_accessible) for item in merged] == [
        ("calendar", False),
        ("drive", True),
        ("mail", True),
    ]


def test_should_send_update_when_accessible_or_fully_loaded() -> None:
    # Rust: notify when any app is accessible, or once both accessible and directory loads finish.
    assert should_send_app_list_updated_notification((app("a", accessible=True),), False, False)
    assert should_send_app_list_updated_notification((app("a"),), True, True)
    assert not should_send_app_list_updated_notification((app("a"),), True, False)


def test_apps_list_returns_empty_when_apps_disabled_for_auth() -> None:
    # Rust: disabled feature/auth gate returns an immediate empty AppsListResponse.
    config = SimpleNamespace(features=FakeFeatures(apps_enabled=False))
    processor = AppsRequestProcessor(
        auth_manager=FakeAuthManager(FakeAuth(True)),
        thread_manager=FakeThreadManager(),
        outgoing=FakeOutgoing(),
        config_manager=FakeConfigManager(config),
        workspace_settings_cache=SimpleNamespace(enabled=True),
        shutdown_token=SimpleNamespace(cancel=lambda: None),
    )

    response = asyncio.run(processor.apps_list("req", {}))

    assert response == AppsListResponse(data=())


def test_apps_list_loads_thread_cwd_and_spawns_background_task(tmp_path: Path) -> None:
    # Rust: thread_id loads the thread, uses its config snapshot cwd as fallback, then spawns and returns None.
    config = SimpleNamespace(features=FakeFeatures(apps_enabled=True))
    config_manager = FakeConfigManager(config)
    scheduled = []
    processor = AppsRequestProcessor(
        auth_manager=FakeAuthManager(FakeAuth(True)),
        thread_manager=FakeThreadManager({"thread-1": FakeThread(tmp_path, apps_enabled=True)}),
        outgoing=FakeOutgoing(),
        config_manager=config_manager,
        workspace_settings_cache=SimpleNamespace(enabled=True),
        shutdown_token=SimpleNamespace(cancel=lambda: None),
        connector_loader=FakeLoader(all_value=(app("calendar"),)),
        task_runner=scheduled.append,
    )

    response = asyncio.run(processor.apps_list("req", {"threadId": "thread-1"}))

    assert response is None
    assert config_manager.fallback_cwds == [tmp_path]
    assert config.features.assigned == {"apps": True}
    assert len(scheduled) == 1
    scheduled[0].close()


def test_apps_list_response_sends_updates_and_returns_paginated_response() -> None:
    # Rust: cached/interim/final app lists may notify, then final response is paginated.
    outgoing = FakeOutgoing()
    loader = FakeLoader(
        cached_all_value=(app("calendar"),),
        accessible_value=AccessibleConnectorsStatus((app("calendar", accessible=True),), codex_apps_ready=True),
        all_value=(app("calendar"), app("drive")),
    )
    processor = AppsRequestProcessor(
        auth_manager=FakeAuthManager(),
        thread_manager=FakeThreadManager(),
        outgoing=outgoing,
        config_manager=FakeConfigManager(SimpleNamespace(features=FakeFeatures())),
        workspace_settings_cache=SimpleNamespace(enabled=True),
        shutdown_token=SimpleNamespace(cancel=lambda: None),
        connector_loader=loader,
    )

    response, ready = asyncio.run(
        processor.apps_list_response(
            outgoing,
            AppsListParams(cursor="0", limit=1),
            SimpleNamespace(features=FakeFeatures()),
            SimpleNamespace(),
        )
    )

    assert ready is True
    assert response == AppsListResponse(data=(app("calendar", accessible=True),), next_cursor="1")
    assert [note.data for note in outgoing.notifications][-1] == (
        app("calendar", accessible=True),
        app("drive"),
    )


def test_apps_list_task_retries_when_codex_apps_not_ready() -> None:
    # Rust: a non-ready accessible load triggers one force_refetch retry after sending the first result.
    outgoing = FakeOutgoing()
    loader = FakeLoader(
        accessible_value=AccessibleConnectorsStatus((app("calendar", accessible=True),), codex_apps_ready=False),
        all_value=(app("calendar"),),
    )
    processor = AppsRequestProcessor(
        auth_manager=FakeAuthManager(),
        thread_manager=FakeThreadManager(),
        outgoing=outgoing,
        config_manager=FakeConfigManager(SimpleNamespace(features=FakeFeatures())),
        workspace_settings_cache=SimpleNamespace(enabled=True),
        shutdown_token=SimpleNamespace(cancel=lambda: None),
        connector_loader=loader,
    )

    asyncio.run(
        processor.apps_list_task(
            outgoing,
            "req",
            AppsListParams(),
            SimpleNamespace(features=FakeFeatures()),
            SimpleNamespace(),
        )
    )

    assert len(outgoing.results) == 1
    assert loader.load_accessible_calls == [False, True]
