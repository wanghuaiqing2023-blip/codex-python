import asyncio
from dataclasses import dataclass

from pycodex.app_server.message_processor import (
    ConnectionSessionState,
    ExternalAuthRefreshBridge,
    InitializedConnectionSessionState,
    MessageProcessor,
    MessageProcessorArgs,
    ProcessorResult,
)
from pycodex.app_server.outgoing_message import ConnectionRequestId
from pycodex.app_server_protocol import (
    ClientRequest,
    ExperimentalReason,
    JSONRPCError,
    JSONRPCErrorError,
    JSONRPCRequest,
    JSONRPCResponse,
)


class FakeOutgoing:
    def __init__(self) -> None:
        self.events = []

    async def register_request_context(self, context):
        self.events.append(("register", context.request_id))

    async def send_error(self, request_id, error):
        self.events.append(("error", request_id, error))

    async def send_response_as(self, request_id, response):
        self.events.append(("response_as", request_id, response))

    async def notify_client_response(self, request_id, result):
        self.events.append(("client_response", request_id, result))

    async def notify_client_error(self, request_id, error):
        self.events.append(("client_error", request_id, error))

    async def connection_closed(self, connection_id):
        self.events.append(("outgoing_closed", connection_id))


class FakeInitializeProcessor:
    def __init__(self) -> None:
        self.tracked = []

    async def initialize(self, connection_id, request_id, params, session, outbound_initialized):
        session.initialize(
            InitializedConnectionSessionState(
                experimental_api_enabled=bool((params or {}).get("experimentalApi")),
                opted_out_notification_methods=frozenset(),
                app_server_client_name="unit-test",
                client_version="1.0",
                request_attestation=bool((params or {}).get("requestAttestation")),
            )
        )
        return True

    def track_initialized_request(self, connection_id, request_id, request):
        self.tracked.append((connection_id, request_id, request.type))


class FakeThreadProcessor:
    def __init__(self, events) -> None:
        self.events = events

    async def connection_initialized(self, connection_id, capabilities):
        self.events.append(("thread_initialized", connection_id, capabilities))

    async def connection_closed(self, connection_id):
        self.events.append(("thread_closed", connection_id))


class CloseProcessor:
    def __init__(self, events, name) -> None:
        self.events = events
        self.name = name

    async def connection_closed(self, connection_id):
        self.events.append((self.name, connection_id))


def _processor(outgoing, **processors):
    processors.setdefault("initialize_processor", FakeInitializeProcessor())
    processors.setdefault("thread_processor", FakeThreadProcessor(outgoing.events))
    return MessageProcessor(
        MessageProcessorArgs(outgoing=outgoing, processors=processors),
        request_routes={
            "ThreadRead": lambda request_id, params, *_: {"thread": params["threadId"]},
            "ThreadList": lambda *_: ProcessorResult.no_response(),
        },
    )


def test_connection_session_state_matches_once_lock_defaults_and_single_initialize():
    # Rust contract: ConnectionSessionState::new starts uninitialized and
    # initialize(...) succeeds only once because it is backed by OnceLock.
    session = ConnectionSessionState.new()
    assert session.initialized() is False
    assert session.experimental_api_enabled() is False
    assert session.opted_out_notification_methods() == set()
    assert session.app_server_client_name() is None
    assert session.client_version() is None
    assert session.request_attestation() is False

    state = InitializedConnectionSessionState(
        experimental_api_enabled=True,
        opted_out_notification_methods=frozenset({"turn/delta"}),
        app_server_client_name="desktop",
        client_version="2.0",
        request_attestation=True,
    )
    assert session.initialize(state) is True
    assert session.initialize(state) is False
    assert session.initialized() is True
    assert session.experimental_api_enabled() is True
    assert session.opted_out_notification_methods() == {"turn/delta"}
    assert session.app_server_client_name() == "desktop"
    assert session.client_version() == "2.0"
    assert session.request_attestation() is True


def test_process_request_rejects_non_initialize_before_session_initialized():
    # Rust contract: dispatch_initialized_client_request returns
    # invalid_request("Not initialized") for all non-Initialize requests.
    outgoing = FakeOutgoing()
    processor = _processor(outgoing)
    request = JSONRPCRequest(id=7, method="thread/read", params={"threadId": "thread-1"})

    asyncio.run(processor.process_request(42, request, session=ConnectionSessionState.new()))

    event, request_id, error = outgoing.events[-1]
    assert event == "error"
    assert request_id == ConnectionRequestId(42, 7)
    assert error.code == -32600
    assert error.message == "Not initialized"


def test_initialize_request_bypasses_initialized_gate_and_notifies_thread_processor():
    # Rust contract: Initialize is handled before the initialized request gate;
    # when it initializes the connection, thread_processor.connection_initialized
    # receives request_attestation from the session.
    outgoing = FakeOutgoing()
    processor = _processor(outgoing)
    session = ConnectionSessionState.new()
    request = ClientRequest("Initialize", request_id="init-1", params={"requestAttestation": True})

    asyncio.run(processor.process_client_request("conn-1", request, session))

    assert session.initialized() is True
    assert ("thread_initialized", "conn-1", {"request_attestation": True}) in outgoing.events
    assert not [event for event in outgoing.events if event[0] == "error"]


def test_initialized_request_tracks_and_sends_some_response():
    # Rust contract: initialized requests are tracked by initialize_processor,
    # dispatched to the child processor, and Ok(Some(response)) sends response_as.
    outgoing = FakeOutgoing()
    initialize = FakeInitializeProcessor()
    processor = _processor(outgoing, initialize_processor=initialize)
    session = ConnectionSessionState.new()
    session.initialize(InitializedConnectionSessionState(app_server_client_name="client", client_version="1"))
    request = ClientRequest("ThreadRead", request_id=9, params={"threadId": "thread-1"})

    asyncio.run(processor.process_client_request(4, request, session))

    assert initialize.tracked == [(4, request.id(), "ThreadRead")]
    assert outgoing.events[-1] == ("response_as", ConnectionRequestId(4, 9), {"thread": "thread-1"})


def test_initialized_request_with_no_response_does_not_send_response():
    # Rust contract: Ok(None) leaves the request without an outbound response.
    outgoing = FakeOutgoing()
    processor = _processor(outgoing)
    session = ConnectionSessionState.new()
    session.initialize(InitializedConnectionSessionState())

    asyncio.run(processor.process_client_request(4, ClientRequest("ThreadList", request_id=1), session))

    assert [event for event in outgoing.events if event[0] in {"response_as", "error"}] == []


def test_experimental_request_requires_initialized_experimental_capability():
    # Rust contract: experimental requests require experimentalApi capability
    # after the initialized gate and before child dispatch.
    outgoing = FakeOutgoing()
    processor = _processor(outgoing)
    session = ConnectionSessionState.new()
    session.initialize(InitializedConnectionSessionState(experimental_api_enabled=False))
    request = ClientRequest("ThreadRead", request_id=11, params={"field": ExperimentalReason("mock_reason")})

    asyncio.run(processor.process_client_request("conn", request, session))

    event, _, error = outgoing.events[-1]
    assert event == "error"
    assert error.code == -32600
    assert error.message == "mock_reason requires experimentalApi capability"


def test_process_response_and_error_forward_to_outgoing_callbacks():
    # Rust contract: standalone JSON-RPC responses/errors are forwarded to
    # OutgoingMessageSender callback resolution.
    outgoing = FakeOutgoing()
    processor = _processor(outgoing)

    asyncio.run(processor.process_response(JSONRPCResponse(id="srv-1", result={"ok": True})))
    error = JSONRPCError(error=JSONRPCErrorError(code=-1, message="bad"), id="srv-2")
    asyncio.run(processor.process_error(error))

    assert outgoing.events[-2][0] == "client_response"
    assert outgoing.events[-2][2] == {"ok": True}
    assert outgoing.events[-1][0] == "client_error"
    assert outgoing.events[-1][2] == JSONRPCErrorError(code=-1, message="bad")


def test_connection_closed_runs_rust_cleanup_order():
    # Rust contract: connection_closed shuts down rpc_gate, outgoing, fs,
    # command exec, process exec, then thread processor.
    outgoing = FakeOutgoing()
    session = ConnectionSessionState.new()
    processor = _processor(
        outgoing,
        fs_processor=CloseProcessor(outgoing.events, "fs_closed"),
        command_exec_processor=CloseProcessor(outgoing.events, "command_closed"),
        process_exec_processor=CloseProcessor(outgoing.events, "process_closed"),
        thread_processor=FakeThreadProcessor(outgoing.events),
    )

    asyncio.run(processor.connection_closed("conn-7", session))

    assert session.rpc_gate.shutdown_called is True
    assert outgoing.events[-5:] == [
        ("outgoing_closed", "conn-7"),
        ("fs_closed", "conn-7"),
        ("command_closed", "conn-7"),
        ("process_closed", "conn-7"),
        ("thread_closed", "conn-7"),
    ]


@dataclass
class RefreshContext:
    reason: str = "Unauthorized"
    previous_account_id: str | None = "acct-old"


def test_external_auth_refresh_bridge_maps_reason_and_response_payload():
    # Rust contract: ExternalAuthRefreshBridge uses ChatGPT auth mode, maps the
    # Unauthorized reason, sends a refresh server request, and projects returned
    # ChatGPT tokens.
    class Outgoing:
        def __init__(self) -> None:
            self.sent = []

        async def send_request(self, payload):
            self.sent.append(payload)
            fut = asyncio.get_running_loop().create_future()
            fut.set_result(
                {
                    "accessToken": "token",
                    "chatgptAccountId": "acct-new",
                    "chatgptPlanType": "plus",
                }
            )
            return "srv-1", fut

    outgoing = Outgoing()
    bridge = ExternalAuthRefreshBridge(outgoing)
    tokens = asyncio.run(bridge.refresh(RefreshContext()))

    assert bridge.auth_mode() == "Chatgpt"
    assert outgoing.sent == [
        {
            "type": "ChatgptAuthTokensRefresh",
            "params": {"reason": "Unauthorized", "previousAccountId": "acct-old"},
        }
    ]
    assert tokens.access_token == "token"
    assert tokens.chatgpt_account_id == "acct-new"
    assert tokens.chatgpt_plan_type == "plus"
