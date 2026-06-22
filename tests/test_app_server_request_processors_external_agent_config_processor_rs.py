from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from pycodex.app_server.error_code import INVALID_PARAMS_ERROR_CODE
from pycodex.app_server.request_processors_external_agent_config_processor import (
    ExternalAgentConfigDetectOptions,
    ExternalAgentConfigRequestProcessor,
    ExternalAgentConfigRequestProcessorError,
    PendingSessionImport,
    migration_items_need_runtime_refresh,
    session_not_detected_error,
)
from pycodex.app_server_protocol import (
    ExternalAgentConfigImportParams,
    ExternalAgentConfigMigrationItem,
    ExternalAgentConfigMigrationItemType,
    MigrationDetails,
    PluginsMigration,
    SessionMigration,
)


def _item(item_type: ExternalAgentConfigMigrationItemType, details: MigrationDetails | None = None) -> ExternalAgentConfigMigrationItem:
    return ExternalAgentConfigMigrationItem(item_type=item_type, description=item_type.value, details=details)


def test_migration_items_that_update_runtime_sources_trigger_refresh() -> None:
    # Rust source: app-server/src/request_processors/external_agent_config_processor_tests.rs.
    refresh = {
        ExternalAgentConfigMigrationItemType.CONFIG,
        ExternalAgentConfigMigrationItemType.SKILLS,
        ExternalAgentConfigMigrationItemType.MCP_SERVER_CONFIG,
        ExternalAgentConfigMigrationItemType.HOOKS,
        ExternalAgentConfigMigrationItemType.COMMANDS,
        ExternalAgentConfigMigrationItemType.PLUGINS,
    }
    for item_type in ExternalAgentConfigMigrationItemType:
        assert migration_items_need_runtime_refresh([_item(item_type)]) is (item_type in refresh)


def test_session_not_detected_error_maps_invalid_params() -> None:
    error = session_not_detected_error(Path("session.jsonl"))
    assert error.code == INVALID_PARAMS_ERROR_CODE
    assert error.message == "external agent session was not detected for import: session.jsonl"


async def _async_test_detect_maps_core_items_and_details_to_protocol() -> None:
    # Rust source: detect maps core external_agent_config migration details into protocol items.
    service = FakeMigrationService(
        detected=[
            SimpleNamespace(
                item_type="plugins",
                description="plugins",
                cwd=Path("project"),
                details=SimpleNamespace(
                    plugins=[SimpleNamespace(marketplace_name="market", plugin_names=["alpha", "beta"])],
                ),
            ),
            SimpleNamespace(
                item_type="sessions",
                description="sessions",
                details=SimpleNamespace(
                    sessions=[SimpleNamespace(path=Path("session.jsonl"), cwd=Path("project"), title="Demo")],
                ),
            ),
            SimpleNamespace(
                item_type="mcp_server_config",
                description="names",
                details=SimpleNamespace(
                    mcp_servers=[SimpleNamespace(name="server")],
                    hooks=[SimpleNamespace(name="hook")],
                    subagents=[SimpleNamespace(name="agent")],
                    commands=[SimpleNamespace(name="cmd")],
                ),
            ),
        ]
    )
    processor = _processor(service=service)

    response = await processor.detect({"includeHome": True, "cwds": ["project"]})

    assert service.detect_options == ExternalAgentConfigDetectOptions(True, (Path("project"),))
    assert [item.item_type for item in response.items] == [
        ExternalAgentConfigMigrationItemType.PLUGINS,
        ExternalAgentConfigMigrationItemType.SESSIONS,
        ExternalAgentConfigMigrationItemType.MCP_SERVER_CONFIG,
    ]
    assert response.items[0].cwd == Path("project")
    assert response.items[0].details.plugins == (PluginsMigration("market", ("alpha", "beta")),)
    assert response.items[1].details.sessions == (SessionMigration(Path("session.jsonl"), Path("project"), "Demo"),)
    assert response.items[2].details.mcp_servers[0].name == "server"
    assert response.items[2].details.hooks[0].name == "hook"
    assert response.items[2].details.subagents[0].name == "agent"
    assert response.items[2].details.commands[0].name == "cmd"


async def _async_test_import_no_items_sends_response_only() -> None:
    # Rust source: import returns after response when no migration items are requested.
    outgoing = FakeOutgoing()
    processor = _processor(service=FakeMigrationService(), outgoing=outgoing)

    await processor.import_("request-1", {"migrationItems": []})

    assert outgoing.responses == [("request-1", "ExternalAgentConfigImportResponse")]
    assert outgoing.notifications == []


async def _async_test_import_sends_response_refresh_and_completed_notification_without_background() -> None:
    # Rust source: runtime-refresh items call config mutation before response, then completed when no imports remain.
    outgoing = FakeOutgoing()
    config_processor = FakeConfigProcessor()
    processor = _processor(service=FakeMigrationService(), outgoing=outgoing, config_processor=config_processor)

    await processor.import_("request-2", ExternalAgentConfigImportParams((_item(ExternalAgentConfigMigrationItemType.CONFIG),)))

    assert config_processor.mutations == 1
    assert outgoing.responses == [("request-2", "ExternalAgentConfigImportResponse")]
    assert [notification.type for notification in outgoing.notifications] == ["ExternalAgentConfigImportCompleted"]


async def _async_test_validate_pending_session_imports_dedupes_by_detected_source() -> None:
    # Rust source: validate_pending_session_imports canonicalizes and dedupes detected sessions.
    session_a = SessionMigration(Path("one.jsonl"), Path("project"), "One")
    session_b = SessionMigration(Path("two.jsonl"), Path("project"), "Two")
    service = FakeMigrationService(session_sources={session_a.path: Path("canonical/session"), session_b.path: Path("canonical/session")})
    processor = _processor(service=service)

    validated = await processor.validate_pending_session_imports(
        ExternalAgentConfigImportParams(
            (
                _item(ExternalAgentConfigMigrationItemType.SESSIONS, MigrationDetails(sessions=(session_a, session_b))),
            )
        )
    )

    assert validated == [session_a]


async def _async_test_validate_pending_session_imports_rejects_undetected_session() -> None:
    session = SessionMigration(Path("missing.jsonl"), Path("project"), None)
    processor = _processor(service=FakeMigrationService(session_sources={}))

    try:
        await processor.validate_pending_session_imports(
            ExternalAgentConfigImportParams(
                (_item(ExternalAgentConfigMigrationItemType.SESSIONS, MigrationDetails(sessions=(session,))),)
            )
        )
    except ExternalAgentConfigRequestProcessorError as exc:
        assert exc.error.code == INVALID_PARAMS_ERROR_CODE
        assert exc.error.message == "external agent session was not detected for import: missing.jsonl"
    else:
        raise AssertionError("expected ExternalAgentConfigRequestProcessorError")


async def _async_test_import_schedules_background_sessions_plugins_and_clears_caches() -> None:
    # Rust source: import sends the RPC response first, then background imports sessions/plugins and notifies completion.
    session = SessionMigration(Path("session.jsonl"), Path("project"), "Thread")
    pending_plugin = SimpleNamespace(cwd=Path("project"), details=PluginsMigration("market", ("plugin",)))
    service = FakeMigrationService(
        session_sources={session.path: session.path},
        pending_plugins=[pending_plugin],
    )
    outgoing = FakeOutgoing()
    thread_manager = FakeThreadManager()
    scheduled = []
    processor = _processor(
        service=service,
        outgoing=outgoing,
        thread_manager=thread_manager,
        task_runner=scheduled.append,
        session_import_preparer=lambda sessions: [PendingSessionImport(Path("detected/session.jsonl"), sessions[0])],
    )

    await processor.import_(
        "request-3",
        ExternalAgentConfigImportParams(
            (
                _item(ExternalAgentConfigMigrationItemType.PLUGINS),
                _item(ExternalAgentConfigMigrationItemType.SESSIONS, MigrationDetails(sessions=(session,))),
            )
        ),
    )

    assert outgoing.responses == [("request-3", "ExternalAgentConfigImportResponse")]
    assert outgoing.notifications == []
    assert len(scheduled) == 1

    await scheduled[0]

    assert thread_manager.imported_sessions == [(session, "thread-1")]
    assert service.recorded_sessions == [(Path("detected/session.jsonl"), "thread-1")]
    assert service.plugin_imports == [(Path("project"), pending_plugin.details)]
    assert thread_manager.plugins_manager.cleared == 1
    assert thread_manager.skills_manager.cleared == 1
    assert [notification.type for notification in outgoing.notifications] == ["ExternalAgentConfigImportCompleted"]


def test_detect_maps_core_items_and_details_to_protocol() -> None:
    asyncio.run(_async_test_detect_maps_core_items_and_details_to_protocol())


def test_import_no_items_sends_response_only() -> None:
    asyncio.run(_async_test_import_no_items_sends_response_only())


def test_import_sends_response_refresh_and_completed_notification_without_background() -> None:
    asyncio.run(_async_test_import_sends_response_refresh_and_completed_notification_without_background())


def test_validate_pending_session_imports_dedupes_by_detected_source() -> None:
    asyncio.run(_async_test_validate_pending_session_imports_dedupes_by_detected_source())


def test_validate_pending_session_imports_rejects_undetected_session() -> None:
    asyncio.run(_async_test_validate_pending_session_imports_rejects_undetected_session())


def test_import_schedules_background_sessions_plugins_and_clears_caches() -> None:
    asyncio.run(_async_test_import_schedules_background_sessions_plugins_and_clears_caches())


class FakeOutgoing:
    def __init__(self) -> None:
        self.responses = []
        self.notifications = []

    async def send_response(self, request_id, response) -> None:
        self.responses.append((request_id, type(response).__name__))

    async def send_server_notification(self, notification) -> None:
        self.notifications.append(notification)


class FakeMigrationService:
    def __init__(self, detected=(), session_sources=None, pending_plugins=()) -> None:
        self.detected = tuple(detected)
        self.session_sources = dict(session_sources or {})
        self.pending_plugins = tuple(pending_plugins)
        self.detect_options = None
        self.imported_items = []
        self.plugin_imports = []
        self.recorded_sessions = []

    async def detect(self, options):
        self.detect_options = options
        return self.detected

    async def external_agent_session_source_path(self, path):
        return self.session_sources.get(Path(path))

    async def import_external_agent_config(self, items):
        self.imported_items.append(tuple(items))
        return self.pending_plugins

    async def import_plugins(self, cwd, details):
        self.plugin_imports.append((cwd, details))

    async def record_imported_session(self, source_path, imported_thread_id):
        self.recorded_sessions.append((source_path, imported_thread_id))


class FakeConfigProcessor:
    def __init__(self) -> None:
        self.mutations = 0

    async def handle_config_mutation(self) -> None:
        self.mutations += 1


class FakeCacheManager:
    def __init__(self) -> None:
        self.cleared = 0

    async def clear_cache(self) -> None:
        self.cleared += 1


class FakeThreadManager:
    def __init__(self) -> None:
        self.plugins_manager = FakeCacheManager()
        self.skills_manager = FakeCacheManager()
        self.imported_sessions = []

    async def import_external_agent_session(self, session, _config_manager, _arg0_paths):
        thread_id = f"thread-{len(self.imported_sessions) + 1}"
        self.imported_sessions.append((session, thread_id))
        return thread_id


def _processor(**overrides):
    return ExternalAgentConfigRequestProcessor(
        outgoing=overrides.get("outgoing", FakeOutgoing()),
        codex_home=Path("codex-home"),
        thread_manager=overrides.get("thread_manager", FakeThreadManager()),
        config_manager=object(),
        config_processor=overrides.get("config_processor", FakeConfigProcessor()),
        arg0_paths=object(),
        migration_service=overrides.get("service", FakeMigrationService()),
        task_runner=overrides.get("task_runner"),
        session_import_preparer=overrides.get("session_import_preparer"),
    )
