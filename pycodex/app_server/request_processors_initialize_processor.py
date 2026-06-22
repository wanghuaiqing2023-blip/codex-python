"""Initialize request processor projection.

Ported from ``codex-app-server/src/request_processors/initialize_processor.rs``.
The Rust module owns initialize-time session state, client metadata side
effects, analytics tracking, initialize response construction, and queued
config-warning notifications. Python keeps those boundaries injectable so the
module can be verified without starting real transports.
"""

from __future__ import annotations

import inspect
import os
import platform
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server.error_code import invalid_request
from pycodex.app_server_protocol import (
    ConfigWarningNotification,
    InitializeParams,
    InitializeResponse,
    JSONRPCErrorError,
    ServerNotification,
)
from pycodex.login.auth import default_client

JsonValue = Any

NON_ORIGINATING_CLIENT_NAMES = frozenset({"codex_app_server_daemon", "codex-backend"})


@dataclass(frozen=True)
class InitializedConnectionSessionState:
    experimental_api_enabled: bool
    opted_out_notification_methods: frozenset[str]
    app_server_client_name: str
    client_version: str
    request_attestation: bool


@dataclass(frozen=True)
class ConnectionRequestId:
    connection_id: Any
    request_id: Any


class InitializeRequestProcessorError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


class InitializeRequestProcessor:
    def __init__(
        self,
        outgoing: Any,
        analytics_events_client: Any,
        config: Any,
        config_warnings: Iterable[ConfigWarningNotification | Mapping[str, JsonValue]],
        rpc_transport: Any,
        *,
        originator_setter: Any = default_client.set_default_originator,
        user_agent_suffix_setter: Any = default_client.set_user_agent_suffix,
        user_agent_getter: Any = default_client.get_codex_user_agent,
        residency_setter: Any = default_client.set_default_client_residency_requirement,
        platform_family: str | None = None,
        platform_os: str | None = None,
    ) -> None:
        self.outgoing = outgoing
        self.analytics_events_client = analytics_events_client
        self.analytics = analytics_events_client
        self.config = config
        self.config_warnings = tuple(_config_warning(warning) for warning in config_warnings)
        self.rpc_transport = rpc_transport
        self._originator_setter = originator_setter
        self._user_agent_suffix_setter = user_agent_suffix_setter
        self._user_agent_getter = user_agent_getter
        self._residency_setter = residency_setter
        self._platform_family = platform_family
        self._platform_os = platform_os

    @classmethod
    def new(
        cls,
        outgoing: Any,
        analytics_events_client: Any,
        config: Any,
        config_warnings: Iterable[ConfigWarningNotification | Mapping[str, JsonValue]],
        rpc_transport: Any,
    ) -> "InitializeRequestProcessor":
        return cls(outgoing, analytics_events_client, config, config_warnings, rpc_transport)

    async def initialize(
        self,
        connection_id: Any,
        request_id: Any,
        params: InitializeParams | Mapping[str, JsonValue],
        session: Any,
        outbound_initialized: Any | None = None,
    ) -> bool:
        if _session_initialized(session):
            raise InitializeRequestProcessorError(invalid_request("Already initialized"))

        parsed = _initialize_params(params)
        capabilities = parsed.capabilities
        experimental_api_enabled = False if capabilities is None else capabilities.experimental_api
        request_attestation = False if capabilities is None else capabilities.request_attestation
        opt_out_methods = () if capabilities is None or capabilities.opt_out_notification_methods is None else capabilities.opt_out_notification_methods

        name = parsed.client_info.name
        version = parsed.client_info.version
        if not _valid_header_value(name):
            raise InitializeRequestProcessorError(
                invalid_request(f"Invalid clientInfo.name: '{name}'. Must be a valid HTTP header value.")
            )

        state = InitializedConnectionSessionState(
            experimental_api_enabled=experimental_api_enabled,
            opted_out_notification_methods=frozenset(opt_out_methods),
            app_server_client_name=name,
            client_version=version,
            request_attestation=request_attestation,
        )
        if not _session_initialize(session, state):
            raise InitializeRequestProcessorError(invalid_request("Already initialized"))

        mutates_global_identity = name not in NON_ORIGINATING_CLIENT_NAMES
        if mutates_global_identity:
            try:
                self._originator_setter(name)
            except Exception:
                pass

        self.track_initialize(connection_id, parsed, name)
        self._residency_setter(_residency_value(getattr(self.config, "enforce_residency", None)))
        if mutates_global_identity:
            self._user_agent_suffix_setter(f"{name}; {version}")

        response = InitializeResponse(
            user_agent=self._user_agent_getter(),
            codex_home=Path(getattr(self.config, "codex_home")),
            platform_family=self._platform_family or os.name,
            platform_os=self._platform_os or platform.system().lower(),
        )
        await _maybe_await(
            self.outgoing.send_response(
                ConnectionRequestId(connection_id=connection_id, request_id=request_id),
                response,
            )
        )

        if outbound_initialized is not None:
            _store_true(outbound_initialized)
            return True
        return False

    async def send_initialize_notifications_to_connection(self, connection_id: Any) -> None:
        for notification in self.config_warnings:
            await _maybe_await(
                self.outgoing.send_server_notification_to_connections(
                    [connection_id],
                    ServerNotification("ConfigWarning", notification),
                )
            )

    async def send_initialize_notifications(self) -> None:
        for notification in self.config_warnings:
            await _maybe_await(
                self.outgoing.send_server_notification(ServerNotification("ConfigWarning", notification))
            )

    def track_initialized_request(self, connection_id: Any, request_id: Any, request: Any) -> None:
        self.analytics_events_client.track_request(_connection_id_value(connection_id), request_id, request)

    def track_initialize(self, connection_id: Any, params: InitializeParams, originator: str) -> None:
        self.analytics_events_client.track_initialize(
            _connection_id_value(connection_id),
            params,
            originator,
            self.rpc_transport,
        )


def _initialize_params(value: InitializeParams | Mapping[str, JsonValue]) -> InitializeParams:
    return value if isinstance(value, InitializeParams) else InitializeParams.from_mapping(value)


def _config_warning(value: ConfigWarningNotification | Mapping[str, JsonValue]) -> ConfigWarningNotification:
    if isinstance(value, ConfigWarningNotification):
        return value
    return ConfigWarningNotification.from_mapping(value)


def _session_initialized(session: Any) -> bool:
    initialized = getattr(session, "initialized", None)
    return bool(initialized() if callable(initialized) else getattr(session, "is_initialized", False))


def _session_initialize(session: Any, state: InitializedConnectionSessionState) -> bool:
    initialize = getattr(session, "initialize")
    result = initialize(state)
    return False if result is False else True


def _valid_header_value(value: str) -> bool:
    return all(ch == "\t" or " " <= ch <= "~" for ch in value)


def _residency_value(value: Any) -> Any:
    method = getattr(value, "value", None)
    return method() if callable(method) else getattr(value, "value", value)


def _store_true(value: Any) -> None:
    store = getattr(value, "store", None)
    if callable(store):
        try:
            store(True)
        except TypeError:
            store(True, None)
        return
    set_method = getattr(value, "set", None)
    if callable(set_method):
        set_method()
        return
    if isinstance(value, list):
        value[:] = [True]
        return
    setattr(value, "value", True)


def _connection_id_value(value: Any) -> Any:
    return getattr(value, "value", getattr(value, "0", value))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "ConnectionRequestId",
    "InitializeRequestProcessor",
    "InitializeRequestProcessorError",
    "InitializedConnectionSessionState",
    "NON_ORIGINATING_CLIENT_NAMES",
]
