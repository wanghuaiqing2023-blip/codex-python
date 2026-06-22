"""External-agent config processor ported from ``app-server/src/request_processors/external_agent_config_processor.rs``."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_params
from pycodex.app_server_protocol import (
    CommandMigration,
    ExternalAgentConfigDetectParams,
    ExternalAgentConfigDetectResponse,
    ExternalAgentConfigImportCompletedNotification,
    ExternalAgentConfigImportParams,
    ExternalAgentConfigImportResponse,
    ExternalAgentConfigMigrationItem,
    ExternalAgentConfigMigrationItemType,
    HookMigration,
    JSONRPCErrorError,
    McpServerMigration,
    MigrationDetails,
    PluginsMigration,
    ServerNotification,
    SessionMigration,
    SubagentMigration,
)

JsonValue = Any
TaskRunner = Callable[[Any], Any]


@dataclass(frozen=True)
class ExternalAgentConfigDetectOptions:
    include_home: bool
    cwds: tuple[Path, ...] | None = None


@dataclass(frozen=True)
class CoreExternalAgentConfigMigrationItem:
    item_type: ExternalAgentConfigMigrationItemType
    description: str
    cwd: Path | None = None
    details: MigrationDetails | None = None


@dataclass(frozen=True)
class PendingSessionImport:
    source_path: Path
    session: SessionMigration


@dataclass
class ExternalAgentConfigRequestProcessorError(Exception):
    error: JSONRPCErrorError

    def __post_init__(self) -> None:
        Exception.__init__(self, self.error.message)


@dataclass
class ExternalAgentConfigRequestProcessor:
    outgoing: Any
    codex_home: Path
    thread_manager: Any
    config_manager: Any
    config_processor: Any
    arg0_paths: Any
    migration_service: Any | None = None
    task_runner: TaskRunner | None = None
    session_import_preparer: Callable[[Sequence[SessionMigration]], Any] | None = None
    session_import_lock: asyncio.Lock | None = None

    def __post_init__(self) -> None:
        self.codex_home = Path(self.codex_home)
        if self.migration_service is None:
            self.migration_service = NullExternalAgentConfigService(self.codex_home)
        if self.session_import_lock is None:
            self.session_import_lock = asyncio.Lock()

    @classmethod
    def new(
        cls,
        outgoing: Any,
        codex_home: Path | str,
        thread_manager: Any,
        config_manager: Any,
        config_processor: Any,
        arg0_paths: Any,
    ) -> "ExternalAgentConfigRequestProcessor":
        return cls(outgoing, Path(codex_home), thread_manager, config_manager, config_processor, arg0_paths)

    async def detect(
        self,
        params: ExternalAgentConfigDetectParams | Mapping[str, JsonValue] | None = None,
    ) -> ExternalAgentConfigDetectResponse:
        parsed = params if isinstance(params, ExternalAgentConfigDetectParams) else ExternalAgentConfigDetectParams.from_mapping(params)
        options = ExternalAgentConfigDetectOptions(include_home=parsed.include_home, cwds=parsed.cwds)
        try:
            items = await _maybe_await(_call_or_get(self.migration_service, "detect", options))
        except Exception as exc:
            raise ExternalAgentConfigRequestProcessorError(internal_error(str(exc))) from exc
        return ExternalAgentConfigDetectResponse(items=tuple(map_core_migration_item_to_protocol(item) for item in (items or ())))

    async def import_(
        self,
        request_id: Any,
        params: ExternalAgentConfigImportParams | Mapping[str, JsonValue],
    ) -> None:
        parsed = params if isinstance(params, ExternalAgentConfigImportParams) else ExternalAgentConfigImportParams.from_mapping(params)
        needs_runtime_refresh = migration_items_need_runtime_refresh(parsed.migration_items)
        has_migration_items = bool(parsed.migration_items)
        has_plugin_imports = any(_migration_item_type(item.item_type) == ExternalAgentConfigMigrationItemType.PLUGINS for item in parsed.migration_items)
        pending_session_imports = await self.validate_pending_session_imports(parsed)
        pending_plugin_imports = await self.import_external_agent_config(parsed)

        if needs_runtime_refresh:
            await _maybe_await(_call_or_get(self.config_processor, "handle_config_mutation"))

        await _send_response(self.outgoing, request_id, ExternalAgentConfigImportResponse())
        if not has_migration_items:
            return

        if not pending_session_imports and not pending_plugin_imports:
            await _send_completed_notification(self.outgoing)
            return

        coroutine = self.complete_background_imports(pending_session_imports, pending_plugin_imports, has_plugin_imports)
        if self.task_runner is not None:
            self.task_runner(coroutine)
        else:
            asyncio.create_task(coroutine)

    async def validate_pending_session_imports(self, params: ExternalAgentConfigImportParams) -> list[SessionMigration]:
        sessions = [
            session
            for item in params.migration_items
            if _migration_item_type(item.item_type) == ExternalAgentConfigMigrationItemType.SESSIONS
            for session in _details(item).sessions
        ]
        validated: list[SessionMigration] = []
        seen: set[Path] = set()
        for session in sessions:
            try:
                source_path = await _maybe_await(
                    _call_or_get(self.migration_service, "external_agent_session_source_path", session.path)
                )
            except Exception as exc:
                raise ExternalAgentConfigRequestProcessorError(internal_error(str(exc))) from exc
            if source_path is None:
                raise ExternalAgentConfigRequestProcessorError(session_not_detected_error(session.path))
            source_path = Path(source_path)
            if source_path not in seen:
                seen.add(source_path)
                validated.append(session)
        return validated

    async def import_external_agent_config(self, params: ExternalAgentConfigImportParams) -> tuple[Any, ...]:
        items = tuple(map_protocol_migration_item_to_core(item) for item in params.migration_items)
        importer = _callable(self.migration_service, "import_external_agent_config")
        if importer is None:
            importer = _callable(self.migration_service, "import_items")
        if importer is None:
            importer = _callable(self.migration_service, "import")
        try:
            result = () if importer is None else await _maybe_await(importer(items))
        except Exception as exc:
            raise ExternalAgentConfigRequestProcessorError(internal_error(str(exc))) from exc
        return tuple(result or ())

    async def complete_background_imports(
        self,
        pending_session_imports: Sequence[SessionMigration],
        pending_plugin_imports: Sequence[Any],
        has_plugin_imports: bool,
    ) -> None:
        if pending_session_imports:
            try:
                async with self.session_import_lock:
                    prepared = await self.prepare_validated_session_imports(pending_session_imports)
                    for pending_session in prepared:
                        imported_thread_id = await self.import_external_agent_session(pending_session.session)
                        await self.record_imported_session(pending_session.source_path, imported_thread_id)
            except Exception:
                pass

        for pending_plugin_import in pending_plugin_imports:
            try:
                await self.complete_pending_plugin_import(pending_plugin_import)
            except Exception:
                pass

        if has_plugin_imports:
            await _clear_manager_cache(_call_or_get(self.thread_manager, "plugins_manager"))
            await _clear_manager_cache(_call_or_get(self.thread_manager, "skills_manager"))

        await _send_completed_notification(self.outgoing)

    async def prepare_validated_session_imports(self, sessions: Sequence[SessionMigration]) -> tuple[PendingSessionImport, ...]:
        if self.session_import_preparer is not None:
            prepared = await _maybe_await(self.session_import_preparer(sessions))
            return tuple(prepared or ())
        return tuple(PendingSessionImport(source_path=session.path, session=session) for session in sessions)

    async def import_external_agent_session(self, session: SessionMigration) -> Any:
        importer = _callable(self.thread_manager, "import_external_agent_session")
        if importer is None:
            raise RuntimeError("external agent session import requires a thread_manager.import_external_agent_session hook")
        return await _maybe_await(importer(session, self.config_manager, self.arg0_paths))

    async def record_imported_session(self, source_path: Path, imported_thread_id: Any) -> None:
        recorder = _callable(self.migration_service, "record_imported_session")
        if recorder is not None:
            await _maybe_await(recorder(source_path, imported_thread_id))

    async def complete_pending_plugin_import(self, pending_plugin_import: Any) -> None:
        importer = _callable(self.migration_service, "import_plugins")
        if importer is None:
            return
        cwd = _get(pending_plugin_import, "cwd")
        details = _get(pending_plugin_import, "details")
        try:
            await _maybe_await(importer(None if cwd is None else Path(cwd), details))
        except Exception as exc:
            raise ExternalAgentConfigRequestProcessorError(internal_error(str(exc))) from exc


def migration_items_need_runtime_refresh(items: Sequence[ExternalAgentConfigMigrationItem]) -> bool:
    refresh_types = {
        ExternalAgentConfigMigrationItemType.CONFIG,
        ExternalAgentConfigMigrationItemType.SKILLS,
        ExternalAgentConfigMigrationItemType.MCP_SERVER_CONFIG,
        ExternalAgentConfigMigrationItemType.HOOKS,
        ExternalAgentConfigMigrationItemType.COMMANDS,
        ExternalAgentConfigMigrationItemType.PLUGINS,
    }
    return any(_migration_item_type(item.item_type) in refresh_types for item in items)


def session_not_detected_error(path: Path | str) -> JSONRPCErrorError:
    return invalid_params(f"external agent session was not detected for import: {Path(path)}")


def map_core_migration_item_to_protocol(item: Any) -> ExternalAgentConfigMigrationItem:
    return ExternalAgentConfigMigrationItem(
        item_type=_migration_item_type(_get(item, "item_type")),
        description=str(_get(item, "description", "")),
        cwd=_path_or_none(_get(item, "cwd")),
        details=_details_from_core(_get(item, "details")),
    )


def map_protocol_migration_item_to_core(item: ExternalAgentConfigMigrationItem) -> CoreExternalAgentConfigMigrationItem:
    return CoreExternalAgentConfigMigrationItem(
        item_type=_migration_item_type(item.item_type),
        description=item.description,
        cwd=None if item.cwd is None else Path(item.cwd),
        details=_details(item),
    )


class NullExternalAgentConfigService:
    def __init__(self, codex_home: Path) -> None:
        self.codex_home = Path(codex_home)

    def detect(self, _options: ExternalAgentConfigDetectOptions) -> tuple[CoreExternalAgentConfigMigrationItem, ...]:
        return ()

    def import_external_agent_config(self, _items: Sequence[CoreExternalAgentConfigMigrationItem]) -> tuple[Any, ...]:
        return ()

    def external_agent_session_source_path(self, path: Path) -> Path | None:
        return Path(path) if Path(path).exists() else None


def _migration_item_type(value: Any) -> ExternalAgentConfigMigrationItemType:
    raw = getattr(value, "value", value)
    if isinstance(raw, ExternalAgentConfigMigrationItemType):
        return raw
    aliases = {
        "agents_md": "AGENTS_MD",
        "config": "CONFIG",
        "skills": "SKILLS",
        "plugins": "PLUGINS",
        "mcp_server_config": "MCP_SERVER_CONFIG",
        "mcpserverconfig": "MCP_SERVER_CONFIG",
        "subagents": "SUBAGENTS",
        "hooks": "HOOKS",
        "commands": "COMMANDS",
        "sessions": "SESSIONS",
    }
    raw_text = str(raw)
    key = raw_text.replace("-", "_")
    key = aliases.get(key.lower(), key.upper())
    return ExternalAgentConfigMigrationItemType.parse(key)


def _details(item: ExternalAgentConfigMigrationItem) -> MigrationDetails:
    details = item.details
    if isinstance(details, MigrationDetails):
        return details
    if isinstance(details, Mapping):
        return MigrationDetails.from_mapping(details)
    return MigrationDetails()


def _details_from_core(details: Any) -> MigrationDetails | None:
    if details is None:
        return None
    if isinstance(details, MigrationDetails):
        return details
    if isinstance(details, Mapping):
        return MigrationDetails.from_mapping(details)
    return MigrationDetails(
        plugins=tuple(_plugin_migration(item) for item in _sequence(_get(details, "plugins"))),
        sessions=tuple(_session_migration(item) for item in _sequence(_get(details, "sessions"))),
        mcp_servers=tuple(McpServerMigration(name=str(_get(item, "name"))) for item in _sequence(_get(details, "mcp_servers"))),
        hooks=tuple(HookMigration(name=str(_get(item, "name"))) for item in _sequence(_get(details, "hooks"))),
        subagents=tuple(SubagentMigration(name=str(_get(item, "name"))) for item in _sequence(_get(details, "subagents"))),
        commands=tuple(CommandMigration(name=str(_get(item, "name"))) for item in _sequence(_get(details, "commands"))),
    )


def _plugin_migration(value: Any) -> PluginsMigration:
    if isinstance(value, PluginsMigration):
        return value
    if isinstance(value, Mapping):
        return PluginsMigration.from_mapping(value)
    return PluginsMigration(
        marketplace_name=str(_get(value, "marketplace_name")),
        plugin_names=tuple(str(item) for item in _sequence(_get(value, "plugin_names"))),
    )


def _session_migration(value: Any) -> SessionMigration:
    if isinstance(value, SessionMigration):
        return value
    if isinstance(value, Mapping):
        return SessionMigration.from_mapping(value)
    return SessionMigration(path=Path(_get(value, "path")), cwd=Path(_get(value, "cwd")), title=_get(value, "title"))


async def _send_response(outgoing: Any, request_id: Any, response: Any) -> None:
    sender = _callable(outgoing, "send_response")
    if sender is None:
        sender = _callable(outgoing, "send_response_as")
    if sender is not None:
        await _maybe_await(sender(request_id, response))


async def _send_completed_notification(outgoing: Any) -> None:
    notification = ServerNotification("ExternalAgentConfigImportCompleted", ExternalAgentConfigImportCompletedNotification())
    sender = _callable(outgoing, "send_server_notification")
    if sender is not None:
        await _maybe_await(sender(notification))
        return
    sender = _callable(outgoing, "send_notification")
    if sender is not None:
        await _maybe_await(sender("externalAgentConfig/import/completed", ExternalAgentConfigImportCompletedNotification()))


async def _clear_manager_cache(manager: Any) -> None:
    if manager is None:
        return
    clearer = _callable(manager, "clear_cache")
    if clearer is None:
        clearer = _callable(manager, "clear")
    if clearer is not None:
        await _maybe_await(clearer())


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _callable(obj: Any, name: str) -> Callable[..., Any] | None:
    candidate = getattr(obj, name, None)
    return candidate if callable(candidate) else None


def _call_or_get(obj: Any, name: str, *args: Any) -> Any:
    value = _get(obj, name)
    if callable(value):
        return value(*args)
    return value


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _path_or_none(value: Any) -> Path | None:
    return None if value is None else Path(value)


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


__all__ = [
    "CoreExternalAgentConfigMigrationItem",
    "ExternalAgentConfigDetectOptions",
    "ExternalAgentConfigRequestProcessor",
    "ExternalAgentConfigRequestProcessorError",
    "NullExternalAgentConfigService",
    "PendingSessionImport",
    "map_core_migration_item_to_protocol",
    "map_protocol_migration_item_to_core",
    "migration_items_need_runtime_refresh",
    "session_not_detected_error",
]


setattr(ExternalAgentConfigRequestProcessor, "import", ExternalAgentConfigRequestProcessor.import_)
