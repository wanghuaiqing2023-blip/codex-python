from __future__ import annotations

import asyncio
from pathlib import Path

from pycodex.app_server.request_processors_initialize_processor import (
    ConnectionRequestId,
    InitializeRequestProcessor,
    InitializeRequestProcessorError,
    InitializedConnectionSessionState,
)
from pycodex.app_server.error_code import INVALID_REQUEST_ERROR_CODE
from pycodex.app_server_protocol import ClientInfo, ConfigWarningNotification, InitializeCapabilities, InitializeParams


def test_initialize_rejects_already_initialized_session_before_side_effects() -> None:
    processor = make_processor()
    session = FakeSession(initialized=True)

    error = catch_error(lambda: asyncio.run(processor.initialize("conn-1", "req-1", params(), session)))

    assert error.code == INVALID_REQUEST_ERROR_CODE
    assert error.message == "Already initialized"
    assert processor.outgoing.responses == []
    assert processor.analytics.initializes == []


def test_initialize_rejects_invalid_client_name_before_session_commit() -> None:
    processor = make_processor()
    session = FakeSession()

    error = catch_error(lambda: asyncio.run(processor.initialize("conn-1", "req-1", params(name="bad\rname"), session)))

    assert error.code == INVALID_REQUEST_ERROR_CODE
    assert "Invalid clientInfo.name" in error.message
    assert session.state is None


def test_initialize_commits_session_tracks_analytics_and_sends_response() -> None:
    processor = make_processor()
    session = FakeSession()
    outbound = []

    outbound_ready = asyncio.run(
        processor.initialize(
            "conn-1",
            "req-1",
            params(
                capabilities=InitializeCapabilities(
                    experimental_api=True,
                    request_attestation=True,
                    opt_out_notification_methods=("thread/statusChanged",),
                )
            ),
            session,
            outbound,
        )
    )

    assert outbound_ready is True
    assert outbound == [True]
    assert session.state == InitializedConnectionSessionState(
        experimental_api_enabled=True,
        opted_out_notification_methods=frozenset({"thread/statusChanged"}),
        app_server_client_name="codex_vscode",
        client_version="1.2.3",
        request_attestation=True,
    )
    assert processor.originators == ["codex_vscode"]
    assert processor.user_agent_suffixes == ["codex_vscode; 1.2.3"]
    assert processor.residencies == ["eu"]
    assert processor.analytics.initializes == [("conn-1", "codex_vscode", "websocket")]
    request_id, response = processor.outgoing.responses[0]
    assert request_id == ConnectionRequestId("conn-1", "req-1")
    assert response.user_agent == "CodexTest/1"
    assert response.codex_home == Path("C:/codex-home")
    assert response.platform_family == "windows"
    assert response.platform_os == "windows"


def test_initialize_skips_global_identity_for_non_originating_clients() -> None:
    processor = make_processor()
    session = FakeSession()

    outbound_ready = asyncio.run(processor.initialize("conn-1", "req-1", params(name="codex-backend"), session))

    assert outbound_ready is False
    assert processor.originators == []
    assert processor.user_agent_suffixes == []
    assert processor.analytics.initializes == [("conn-1", "codex-backend", "websocket")]


def test_initialize_session_race_returns_already_initialized() -> None:
    processor = make_processor()
    session = FakeSession(reject_initialize=True)

    error = catch_error(lambda: asyncio.run(processor.initialize("conn-1", "req-1", params(), session)))

    assert error.message == "Already initialized"
    assert processor.outgoing.responses == []


def test_initialize_notifications_are_sent_to_connection_or_broadcast() -> None:
    warning = ConfigWarningNotification(summary="careful", details=None)
    processor = make_processor(config_warnings=[warning])

    asyncio.run(processor.send_initialize_notifications_to_connection("conn-1"))
    asyncio.run(processor.send_initialize_notifications())

    assert processor.outgoing.connection_notifications == [(["conn-1"], "ConfigWarning", warning)]
    assert processor.outgoing.notifications == [("ConfigWarning", warning)]


def test_track_initialized_request_forwards_request_id_and_payload() -> None:
    processor = make_processor()
    request = {"type": "GetAccount"}

    processor.track_initialized_request("conn-1", "req-1", request)

    assert processor.analytics.requests == [("conn-1", "req-1", request)]


def catch_error(fn):
    try:
        fn()
    except InitializeRequestProcessorError as exc:
        return exc.error
    raise AssertionError("expected InitializeRequestProcessorError")


def params(name="codex_vscode", capabilities=None):
    return InitializeParams(ClientInfo(name=name, title="Codex", version="1.2.3"), capabilities)


def make_processor(config_warnings=()):
    outgoing = FakeOutgoing()
    analytics = FakeAnalytics()
    config = Config()
    processor = InitializeRequestProcessor(
        outgoing,
        analytics,
        config,
        config_warnings,
        "websocket",
        originator_setter=lambda value: processor.originators.append(value),
        user_agent_suffix_setter=lambda value: processor.user_agent_suffixes.append(value),
        user_agent_getter=lambda: "CodexTest/1",
        residency_setter=lambda value: processor.residencies.append(value),
        platform_family="windows",
        platform_os="windows",
    )
    processor.originators = []
    processor.user_agent_suffixes = []
    processor.residencies = []
    return processor


class Config:
    codex_home = Path("C:/codex-home")
    enforce_residency = "eu"


class FakeSession:
    def __init__(self, initialized=False, reject_initialize=False):
        self._initialized = initialized
        self.reject_initialize = reject_initialize
        self.state = None

    def initialized(self):
        return self._initialized

    def initialize(self, state):
        if self.reject_initialize:
            return False
        self.state = state
        self._initialized = True
        return True


class FakeOutgoing:
    def __init__(self):
        self.responses = []
        self.connection_notifications = []
        self.notifications = []

    async def send_response(self, request_id, response):
        self.responses.append((request_id, response))

    async def send_server_notification_to_connections(self, connections, notification):
        self.connection_notifications.append((list(connections), notification.type, notification.payload))

    async def send_server_notification(self, notification):
        self.notifications.append((notification.type, notification.payload))


class FakeAnalytics:
    def __init__(self):
        self.initializes = []
        self.requests = []

    def track_initialize(self, connection_id, _params, originator, rpc_transport):
        self.initializes.append((connection_id, originator, rpc_transport))

    def track_request(self, connection_id, request_id, request):
        self.requests.append((connection_id, request_id, request))
