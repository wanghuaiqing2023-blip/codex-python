from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pycodex.app_server_test_client import (
    AppServerTestClientError,
    BackgroundAppServer,
    CodexClient,
    CommandApprovalBehavior,
    ConnectWs,
    DefaultClientRunner,
    DynamicToolSpec,
    JSONRPCRequest,
    MemoryTransport,
    SpawnCodex,
    StdioTransport,
    TestClientTracing,
    WebSocketTransport,
    NO_TRIGGER_CMD_APPROVAL_PROMPT,
    ON_REQUEST_APPROVAL_POLICY,
    TRIGGER_CMD_APPROVAL_PROMPT,
    TRIGGER_ZSH_FORK_MULTI_CMD_APPROVAL_PROMPT,
    danger_full_access_sandbox_policy,
    current_span_w3c_trace_context,
    live_elicitation_timeout_pause,
    ensure_dynamic_tools_unused,
    item_started_before_helper_done_is_unexpected,
    get_account_rate_limits,
    model_list,
    model_list_params,
    no_trigger_cmd_approval,
    parse_dynamic_tools_arg,
    print_multiline_with_prefix,
    print_trace_summary,
    read_only_sandbox_policy,
    resume_message_v2,
    resolve_endpoint,
    resolve_shared_websocket_url,
    run,
    serve,
    serve_command_line,
    send_follow_up_v2,
    send_message_v2,
    send_message_v2_with_policies,
    shell_quote,
    kill_listeners_on_same_port,
    test_login,
    thread_decrement_elicitation,
    thread_elicitation_params,
    thread_increment_elicitation,
    thread_list,
    thread_list_params,
    thread_resume_follow,
    thread_start_params,
    text_user_input,
    trace_url_from_context,
    trace_summary_capture,
    trigger_cmd_approval,
    trigger_zsh_fork_multi_cmd_approval,
    turn_start_params,
    watch,
    with_client,
)


class Runner:
    def __init__(self) -> None:
        self.calls = []

    def __getattr__(self, name):
        async def _method(**kwargs):
            self.calls.append((name, kwargs))
            return name

        return _method

    async def send_message_v2_endpoint(self, **kwargs):
        self.calls.append(("send_message_v2_endpoint", kwargs))
        return "sent"

    async def model_list(self, **kwargs):
        self.calls.append(("model_list", kwargs))
        return "models"

    async def watch(self, **kwargs):
        self.calls.append(("watch", kwargs))
        return "watch"


class FakeClient:
    def __init__(self) -> None:
        self.calls = []
        self.turn_index = 0
        self.command_approval_behavior = (CommandApprovalBehavior.ALWAYS_ACCEPT, None)
        self.command_approval_count = 0
        self.command_approval_item_ids = []
        self.command_execution_statuses = []
        self.command_execution_outputs = []
        self.helper_done_seen = False
        self.unexpected_items_before_helper_done = []
        self.turn_completed_before_helper_done = False
        self.last_turn_error_message = None
        self.last_turn_status = None
        self.stream_result = None
        self.output = []

    def initialize(self):
        self.calls.append(("initialize", None))
        return {"ok": True}

    def initialize_with_experimental_api(self, experimental_api):
        self.calls.append(("initialize_with_experimental_api", experimental_api))
        return {"experimentalApi": experimental_api}

    def thread_start(self, params):
        self.calls.append(("thread_start", params))
        return {"thread": {"id": "thread-1"}}

    def thread_resume(self, params):
        self.calls.append(("thread_resume", params))
        return {"thread": {"id": params["threadId"]}}

    def turn_start(self, params):
        self.turn_index += 1
        self.calls.append(("turn_start", params))
        return {"turn": {"id": f"turn-{self.turn_index}"}}

    def stream_turn(self, thread_id, turn_id):
        self.calls.append(("stream_turn", {"threadId": thread_id, "turnId": turn_id}))
        if self.stream_result is not None:
            approvals, item_ids, statuses, turn_status = self.stream_result
            self.command_approval_count = approvals
            self.command_approval_item_ids[:] = item_ids
            self.command_execution_statuses[:] = statuses
            self.last_turn_status = turn_status

    def emit_line(self, payload=""):
        self.output.append(payload + "\n")

    def login_account_chatgpt(self):
        self.calls.append(("login_account_chatgpt", None))
        return {"type": "chatgpt", "loginId": "login-1", "authUrl": "https://login"}

    def login_account_chatgpt_device_code(self):
        self.calls.append(("login_account_chatgpt_device_code", None))
        return {"type": "chatgptDeviceCode", "loginId": "login-device"}

    def wait_for_account_login_completion(self, login_id):
        self.calls.append(("wait_for_account_login_completion", login_id))
        return {"loginId": login_id, "error": None}

    def get_account_rate_limits(self):
        self.calls.append(("get_account_rate_limits", None))
        return {"primary": None}

    def model_list(self, params):
        self.calls.append(("model_list", params))
        return {"models": []}

    def thread_list(self, params):
        self.calls.append(("thread_list", params))
        return {"threads": []}

    def stream_notifications_forever(self, max_notifications=None):
        self.calls.append(("stream_notifications_forever", max_notifications))
        return max_notifications

    def thread_increment_elicitation(self, params):
        self.calls.append(("thread_increment_elicitation", params))
        return {"incremented": True}

    def thread_decrement_elicitation(self, params):
        self.calls.append(("thread_decrement_elicitation", params))
        return {"decremented": True}


class FakePipe:
    def __init__(self, initial: str = "") -> None:
        self.initial = initial
        self.written = []
        self.closed = False

    def write(self, payload: str) -> None:
        self.written.append(payload)

    def flush(self) -> None:
        self.written.append("<flush>")

    def readline(self) -> str:
        value = self.initial
        self.initial = ""
        return value

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(self, stdout_text: str = "") -> None:
        self.stdin = FakePipe()
        self.stdout = FakePipe(stdout_text)
        self.terminated = False
        self.waited = False
        self.pid = 4242

    def poll(self):
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self):
        self.waited = True
        return 0


def test_lib_rs_resolve_endpoint_contract() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    assert resolve_endpoint(None, None) == ConnectWs("ws://127.0.0.1:4222")
    assert resolve_endpoint("codex", None) == SpawnCodex(__import__("pathlib").Path("codex"))
    assert resolve_endpoint(None, "ws://host") == ConnectWs("ws://host")
    with pytest.raises(AppServerTestClientError, match="mutually exclusive"):
        resolve_endpoint("codex", "ws://host")


def test_lib_rs_shared_websocket_url_and_shell_quote() -> None:
    assert resolve_shared_websocket_url(None, None, "cmd") == "ws://127.0.0.1:4222"
    assert resolve_shared_websocket_url(None, "ws://x", "cmd") == "ws://x"
    with pytest.raises(AppServerTestClientError, match="requires --url"):
        resolve_shared_websocket_url("codex", None, "thread-increment-elicitation")
    assert shell_quote("a'b") == "'a'\\''b'"


def test_lib_rs_serve_command_line_and_port_cleanup_are_rust_shaped() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, serve helpers.
    assert serve_command_line(
        "codex bin", ["model='gpt-5'"], "ws://127.0.0.1:4222"
    ) == (
        "tail -f /dev/null | RUST_BACKTRACE=full RUST_LOG=warn,codex_=trace "
        "'codex bin' --config 'model='\\''gpt-5'\\''' app-server --listen "
        "'ws://127.0.0.1:4222'"
    )

    calls = []

    class Result:
        def __init__(self, returncode, stdout=""):
            self.returncode = returncode
            self.stdout = stdout

    results = iter([Result(0, "111\nbad\n222\n"), Result(0, "222\n")])

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "lsof":
            return next(results)
        return Result(0)

    slept = []
    result = kill_listeners_on_same_port("ws://127.0.0.1:4222", run=fake_run, sleep=slept.append)

    assert result == {"port": 4222, "terminated": ["111", "222"], "forceKilled": ["222"]}
    assert calls[0][0] == ["lsof", "-nP", "-tiTCP:4222", "-sTCP:LISTEN"]
    assert calls[1][0] == ["kill", "111"]
    assert calls[2][0] == ["kill", "222"]
    assert slept == [0.3]
    assert calls[-1][0] == ["kill", "-9", "222"]


def test_lib_rs_serve_starts_nohup_launcher_with_log_path(tmp_path) -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, serve.
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    result = serve(
        Path("codex"),
        ["model=gpt-5"],
        listen="ws://127.0.0.1:4555",
        popen=fake_popen,
        runtime_dir=tmp_path,
    )

    assert captured["args"][:3] == ["nohup", "sh", "-c"]
    assert "RUST_BACKTRACE=full RUST_LOG=warn,codex_=trace" in captured["args"][3]
    assert captured["kwargs"]["stdin"] is not None
    assert result["listen"] == "ws://127.0.0.1:4555"
    assert result["pid"] == 4242
    assert result["log"] == str(tmp_path / "app-server.log")


def test_lib_rs_dynamic_tool_parsing(tmp_path) -> None:
    one = parse_dynamic_tools_arg('{"name":"demo","description":"Demo","inputSchema":{"type":"object"}}')
    assert one == [DynamicToolSpec(name="demo", description="Demo", inputSchema={"type": "object"})]

    path = tmp_path / "tools.json"
    path.write_text(json.dumps([{"name": "a"}, {"name": "b"}]))
    assert [tool.name for tool in parse_dynamic_tools_arg(f"@{path}")] == ["a", "b"]
    assert parse_dynamic_tools_arg(None) is None

    with pytest.raises(AppServerTestClientError, match="object or array"):
        parse_dynamic_tools_arg('"bad"')
    with pytest.raises(AppServerTestClientError, match="dynamic tools"):
        ensure_dynamic_tools_unused([DynamicToolSpec(name="demo")], "watch")


def test_lib_rs_stdio_transport_spawn_matches_rust_command_shape(monkeypatch) -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, CodexClient::spawn_stdio.
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess(stdout_text='{"jsonrpc":"2.0"}\n')

    monkeypatch.setattr("pycodex.app_server_test_client.subprocess.Popen", fake_popen)
    transport = StdioTransport.spawn(Path("bin") / "codex", ["model=gpt-5"])

    assert captured["args"] == [str(Path("bin") / "codex"), "--config", "model=gpt-5", "app-server"]
    assert captured["kwargs"]["stdin"] is not None
    assert captured["kwargs"]["stdout"] is not None
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["env"]["PATH"].split(os.pathsep)[0] == "bin"

    transport.write_payload('{"id":"1"}')
    assert transport.stdin.written == ['{"id":"1"}\n', "<flush>"]
    assert transport.read_payload() == '{"jsonrpc":"2.0"}'
    with pytest.raises(AppServerTestClientError, match="closed stdout"):
        transport.read_payload()


def test_lib_rs_background_app_server_spawn_reserves_port_and_cleans_up(monkeypatch) -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, BackgroundAppServer::spawn.
    captured = {}
    process = FakeProcess()

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return process

    server = BackgroundAppServer.spawn(Path("bin") / "codex", ["model=gpt-5"], popen=fake_popen)

    assert captured["args"][:4] == [str(Path("bin") / "codex"), "--config", "model=gpt-5", "app-server"]
    assert captured["args"][4] == "--listen"
    assert captured["args"][5].startswith("ws://127.0.0.1:")
    assert server.url == captured["args"][5]
    assert captured["kwargs"]["stdin"] is not None
    assert captured["kwargs"]["stdout"] is not None
    assert captured["kwargs"]["env"]["PATH"].split(os.pathsep)[0] == "bin"

    server.close()
    assert process.terminated is True
    assert process.waited is True


def test_lib_rs_codex_client_connect_uses_stdio_and_allows_injected_transport(monkeypatch) -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, CodexClient::connect.
    spawned = FakeProcess()

    def fake_popen(_args, **_kwargs):
        return spawned

    monkeypatch.setattr("pycodex.app_server_test_client.subprocess.Popen", fake_popen)
    client = CodexClient.connect(SpawnCodex(Path("codex")), ["profile=dev"])
    assert isinstance(client.transport, StdioTransport)

    injected = MemoryTransport()
    assert CodexClient.connect(ConnectWs("ws://x"), transport=injected).transport is injected


def test_lib_rs_codex_client_connect_uses_real_websocket_transport(monkeypatch) -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, ConnectWs.
    class FakeWebSocket:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.incoming = ['{"id":"1","result":{"ok":true}}']
            self.closed = False

        def send_text(self, payload: str) -> None:
            self.sent.append(payload)

        def recv_text(self) -> str:
            return self.incoming.pop(0)

        def close(self) -> None:
            self.closed = True

    captured: dict[str, str] = {}
    fake_websocket = FakeWebSocket()

    def fake_connect(url: str):
        captured["url"] = url
        return fake_websocket

    monkeypatch.setattr("pycodex.app_server_test_client.StdlibWebSocket.connect", fake_connect)
    client = CodexClient.connect(ConnectWs("ws://127.0.0.1:4222"))

    assert isinstance(client.transport, WebSocketTransport)
    assert captured["url"] == "ws://127.0.0.1:4222"
    client.write_payload("hello")
    assert fake_websocket.sent == ["hello"]
    assert client.read_payload() == '{"id":"1","result":{"ok":true}}'
    client.transport.close()
    assert fake_websocket.closed is True


def test_lib_rs_trace_and_helper_order_helpers() -> None:
    assert trace_url_from_context({"traceparent": "00-" + "a" * 32 + "-bbbb-01"}) == (
        "go/trace/" + "a" * 32
    )
    assert trace_url_from_context({"traceparent": "bad"}) is None
    assert current_span_w3c_trace_context(
        {"TRACEPARENT": "00-" + "c" * 32 + "-dddd-01", "TRACESTATE": "state"}
    ) == {"traceparent": "00-" + "c" * 32 + "-dddd-01", "tracestate": "state"}
    assert trace_summary_capture(False, {"traceparent": "00-" + "a" * 32 + "-bbbb-01"}) is None
    assert trace_summary_capture(True, {"traceparent": "00-" + "b" * 32 + "-cccc-01"}) == {
        "url": "go/trace/" + "b" * 32
    }
    assert "go/trace/abc" in print_trace_summary({"url": "go/trace/abc"})
    assert "Not enabled" in print_trace_summary(None)
    assert print_multiline_with_prefix("> ", "one\ntwo") == "> one\n> two\n"
    assert print_multiline_with_prefix("> ", "") == ""
    assert item_started_before_helper_done_is_unexpected(
        {"type": "assistant_message"}, command_item_started=True, helper_done_seen=False
    )
    assert not item_started_before_helper_done_is_unexpected(
        {"type": "user_message"}, command_item_started=True, helper_done_seen=False
    )


def test_lib_rs_test_client_tracing_initializes_provider_and_subscriber() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, TestClientTracing.
    calls = []
    subscriber_calls = []

    def provider_builder(config, *, version, service_name, analytics_enabled):
        calls.append((config, version, service_name, analytics_enabled))
        return {"tracerProvider": object()}

    tracing = TestClientTracing.initialize(
        ["otel.tracing=true"],
        config_loader=lambda overrides: {"overrides": overrides},
        provider_builder=provider_builder,
        subscriber_init=subscriber_calls.append,
        version="1.2.3",
    )

    assert tracing.traces_enabled is True
    assert calls == [
        ({"overrides": ["otel.tracing=true"]}, "1.2.3", "codex-app-server-test-client", True)
    ]
    assert subscriber_calls == [tracing.otel_provider]


def test_lib_rs_with_client_wraps_live_client_and_prints_trace_summary() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, with_client.
    output = []
    events = []
    client = object()

    def tracing_factory(overrides):
        events.append(("tracing", overrides))
        return TestClientTracing(otel_provider={"tracerProvider": object()}, traces_enabled=True)

    def client_factory(endpoint, overrides):
        events.append(("client", endpoint, overrides))
        return client

    result = with_client(
        "model-list",
        ConnectWs("ws://127.0.0.1:4222"),
        ["model=gpt-5"],
        lambda live_client: ("ok", live_client),
        client_factory=client_factory,
        tracing_factory=tracing_factory,
        trace_context_factory=lambda: {"traceparent": "00-" + "d" * 32 + "-eeee-01"},
        output=output,
    )

    assert result == ("ok", client)
    assert events == [
        ("tracing", ["model=gpt-5"]),
        ("client", ConnectWs("ws://127.0.0.1:4222"), ["model=gpt-5"]),
    ]
    assert output == ["\n[Datadog trace]\ngo/trace/" + "d" * 32 + "\n"]


@pytest.mark.asyncio
async def test_lib_rs_public_send_message_v2_facade() -> None:
    runner = Runner()
    result = await send_message_v2("codex", ["model=gpt-5"], "hello", None, runner=runner)

    assert result == "sent"
    call, kwargs = runner.calls[-1]
    assert call == "send_message_v2_endpoint"
    assert kwargs["endpoint"] == SpawnCodex(__import__("pathlib").Path("codex"))
    assert kwargs["config_overrides"] == ["model=gpt-5"]
    assert kwargs["user_message"] == "hello"
    assert kwargs["experimental_api"] is True


@pytest.mark.asyncio
async def test_lib_rs_public_send_message_v2_uses_default_runner(monkeypatch) -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, send_message_v2.
    clients: list[FakeClient] = []
    endpoints = []

    def fake_connect(endpoint, config_overrides):
        endpoints.append((endpoint, config_overrides))
        client = FakeClient()
        clients.append(client)
        return client

    monkeypatch.setattr("pycodex.app_server_test_client.CodexClient.connect", fake_connect)

    result = await send_message_v2("codex", ["model=gpt-5"], "hello", None)

    assert endpoints == [(SpawnCodex(Path("codex")), ["model=gpt-5"])]
    assert result["turn"] == {"turn": {"id": "turn-1"}}
    assert [call for call, _ in clients[0].calls] == [
        "initialize_with_experimental_api",
        "thread_start",
        "turn_start",
        "stream_turn",
    ]


@pytest.mark.asyncio
async def test_lib_rs_default_runner_dispatches_to_live_client_helpers() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, default command runner.
    clients: list[FakeClient] = []
    endpoints = []

    def fake_connect(endpoint, config_overrides):
        endpoints.append((endpoint, config_overrides))
        client = FakeClient()
        clients.append(client)
        return client

    runner = DefaultClientRunner(client_factory=fake_connect)
    result = await runner.trigger_cmd_approval(
        endpoint=ConnectWs("ws://127.0.0.1:4222"),
        config_overrides=["model=gpt-5"],
        user_message="approve",
        dynamic_tools=None,
    )

    assert endpoints == [(ConnectWs("ws://127.0.0.1:4222"), ["model=gpt-5"])]
    assert result["thread"] == {"thread": {"id": "thread-1"}}
    turn_call = clients[0].calls[2][1]
    assert turn_call["approvalPolicy"] == ON_REQUEST_APPROVAL_POLICY
    assert turn_call["input"][0]["text"] == "approve"


@pytest.mark.asyncio
async def test_lib_rs_run_uses_default_runner_without_injected_runner(monkeypatch) -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, run.
    clients: list[FakeClient] = []
    endpoints = []

    def fake_connect(endpoint, config_overrides):
        endpoints.append((endpoint, config_overrides))
        client = FakeClient()
        clients.append(client)
        return client

    monkeypatch.setattr("pycodex.app_server_test_client.CodexClient.connect", fake_connect)

    result = await run(["--codex-bin", "codex", "-c", "model=gpt-5", "send-message", "hello"])

    assert endpoints == [(SpawnCodex(Path("codex")), ["model=gpt-5"])]
    assert result["turn"] == {"turn": {"id": "turn-1"}}
    assert clients[0].calls[0] == ("initialize_with_experimental_api", False)


def test_lib_rs_send_message_v2_with_policies_drives_thread_turn_protocol() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    client = FakeClient()

    result = send_message_v2_with_policies(
        client,
        "hello",
        experimental_api=True,
        approval_policy=ON_REQUEST_APPROVAL_POLICY,
        sandbox_policy=read_only_sandbox_policy(network_access=False),
        dynamic_tools=[DynamicToolSpec(name="demo")],
    )

    assert result["thread"] == {"thread": {"id": "thread-1"}}
    assert [call for call, _ in client.calls] == [
        "initialize_with_experimental_api",
        "thread_start",
        "turn_start",
        "stream_turn",
    ]
    assert client.calls[0] == ("initialize_with_experimental_api", True)
    assert client.calls[1][1]["dynamicTools"] == [{"name": "demo"}]
    assert client.calls[2][1] == {
        "threadId": "thread-1",
        "input": [{"type": "text", "text": "hello", "text_elements": []}],
        "cwd": None,
        "approvalPolicy": "on-request",
        "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
        "model": None,
        "serviceTier": None,
        "effort": None,
        "summary": None,
        "personality": None,
        "outputSchema": None,
    }
    assert client.calls[3] == ("stream_turn", {"threadId": "thread-1", "turnId": "turn-1"})


def test_lib_rs_trigger_cmd_approval_uses_rust_default_policy_prompt() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    client = FakeClient()

    trigger_cmd_approval(client)

    turn_params = client.calls[2][1]
    assert turn_params["input"] == [{"type": "text", "text": TRIGGER_CMD_APPROVAL_PROMPT, "text_elements": []}]
    assert turn_params["approvalPolicy"] == "on-request"
    assert turn_params["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}


def test_lib_rs_no_trigger_cmd_and_follow_up_v2_drive_expected_turns() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    no_trigger_client = FakeClient()
    no_trigger_cmd_approval(no_trigger_client)
    assert no_trigger_client.calls[2][1]["input"] == [
        {"type": "text", "text": NO_TRIGGER_CMD_APPROVAL_PROMPT, "text_elements": []}
    ]
    assert no_trigger_client.calls[2][1]["approvalPolicy"] is None
    assert no_trigger_client.calls[2][1]["sandboxPolicy"] is None

    follow_client = FakeClient()
    send_follow_up_v2(follow_client, "first", "second")
    assert [call for call, _ in follow_client.calls] == [
        "initialize",
        "thread_start",
        "turn_start",
        "stream_turn",
        "turn_start",
        "stream_turn",
    ]
    assert follow_client.calls[2][1]["input"] == [
        {"type": "text", "text": "first", "text_elements": []}
    ]
    assert follow_client.calls[4][1]["input"] == [
        {"type": "text", "text": "second", "text_elements": []}
    ]


def test_lib_rs_resume_message_v2_uses_resume_thread_and_rejects_dynamic_tools() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    client = FakeClient()

    resume_message_v2(client, "thread-existing", "hello")

    assert [call for call, _ in client.calls] == [
        "initialize",
        "thread_resume",
        "turn_start",
        "stream_turn",
    ]
    assert client.calls[1][1] == {"threadId": "thread-existing"}
    assert client.calls[2][1]["threadId"] == "thread-existing"
    assert client.calls[2][1]["input"] == [
        {"type": "text", "text": "hello", "text_elements": []}
    ]

    with pytest.raises(AppServerTestClientError, match="dynamic tools"):
        resume_message_v2(FakeClient(), "thread-existing", "hello", dynamic_tools=[{"name": "demo"}])


def test_lib_rs_trigger_zsh_multi_approval_all_accept_contract() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    client = FakeClient()
    client.stream_result = (2, ["item-1", "item-1"], ["completed"], "completed")

    result = trigger_zsh_fork_multi_cmd_approval(client, min_approvals=2)

    assert result["approvals"] == 2
    assert result["approvalsPerItem"] == {"item-1": 2}
    assert client.command_approval_behavior == (CommandApprovalBehavior.ALWAYS_ACCEPT, None)
    assert client.calls[2][1]["input"] == [
        {
            "type": "text",
            "text": TRIGGER_ZSH_FORK_MULTI_CMD_APPROVAL_PROMPT,
            "text_elements": [],
        }
    ]
    assert client.calls[2][1]["approvalPolicy"] == "on-request"
    assert client.calls[2][1]["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}


def test_lib_rs_trigger_zsh_multi_approval_abort_on_contract() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    client = FakeClient()
    client.stream_result = (2, ["item-1", "item-1"], ["failed"], "failed")

    result = trigger_zsh_fork_multi_cmd_approval(
        client, "custom", min_approvals=2, abort_on=2, dynamic_tools=[{"name": "demo"}]
    )

    assert result["commandStatuses"] == ["failed"]
    assert result["turnStatus"] == "failed"
    assert client.command_approval_behavior == (CommandApprovalBehavior.ABORT_ON, 2)
    assert client.calls[1][1]["dynamicTools"] == [{"name": "demo"}]
    assert client.calls[2][1]["input"] == [{"type": "text", "text": "custom", "text_elements": []}]

    with pytest.raises(AppServerTestClientError, match="--abort-on must be >= 1"):
        trigger_zsh_fork_multi_cmd_approval(FakeClient(), abort_on=0)

    completed_after_abort = FakeClient()
    completed_after_abort.stream_result = (2, ["item-1", "item-1"], ["completed"], "completed")
    with pytest.raises(AppServerTestClientError, match="expected non-completed"):
        trigger_zsh_fork_multi_cmd_approval(completed_after_abort, min_approvals=2, abort_on=1)


def test_lib_rs_trigger_zsh_multi_approval_rejects_insufficient_approvals() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    too_few = FakeClient()
    too_few.stream_result = (1, ["item-1"], ["completed"], "completed")
    with pytest.raises(AppServerTestClientError, match="expected at least 2 command approvals"):
        trigger_zsh_fork_multi_cmd_approval(too_few, min_approvals=2)

    split_items = FakeClient()
    split_items.stream_result = (2, ["item-1", "item-2"], ["completed"], "completed")
    with pytest.raises(AppServerTestClientError, match="approvals for one command item"):
        trigger_zsh_fork_multi_cmd_approval(split_items, min_approvals=2)


def test_lib_rs_login_and_list_helpers_drive_client_methods() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    login_client = FakeClient()
    assert test_login(login_client)["completion"] == {"loginId": "login-1", "error": None}
    assert [call for call, _ in login_client.calls] == [
        "initialize",
        "login_account_chatgpt",
        "wait_for_account_login_completion",
    ]

    device_client = FakeClient()
    assert test_login(device_client, device_code=True)["completion"] == {
        "loginId": "login-device",
        "error": None,
    }
    assert [call for call, _ in device_client.calls] == [
        "initialize",
        "login_account_chatgpt_device_code",
        "wait_for_account_login_completion",
    ]

    rate_client = FakeClient()
    assert get_account_rate_limits(rate_client)["rateLimits"] == {"primary": None}
    assert [call for call, _ in rate_client.calls] == ["initialize", "get_account_rate_limits"]

    model_client = FakeClient()
    assert model_list(model_client)["models"] == {"models": []}
    assert model_client.calls[1] == (
        "model_list",
        {"cursor": None, "limit": None, "includeHidden": None},
    )

    thread_client = FakeClient()
    assert thread_list(thread_client, limit=3)["threads"] == {"threads": []}
    assert thread_client.calls[1][0] == "thread_list"
    assert thread_client.calls[1][1]["limit"] == 3
    assert thread_client.calls[1][1]["useStateDbOnly"] is False


def test_lib_rs_watch_and_thread_resume_follow_stream_notifications() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    watch_client = FakeClient()
    assert watch(watch_client, max_notifications=2)["streamed"] == 2
    assert watch_client.calls == [
        ("initialize", None),
        ("stream_notifications_forever", 2),
    ]

    resume_client = FakeClient()
    assert thread_resume_follow(resume_client, "thread-existing", max_notifications=1) == {
        "initialize": {"ok": True},
        "thread": {"thread": {"id": "thread-existing"}},
        "streamed": 1,
    }
    assert resume_client.calls == [
        ("initialize", None),
        ("thread_resume", {"threadId": "thread-existing"}),
        ("stream_notifications_forever", 1),
    ]


def test_lib_rs_thread_elicitation_helpers_use_protocol_params() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    assert thread_elicitation_params("thread-1") == {"threadId": "thread-1"}

    increment_client = FakeClient()
    assert thread_increment_elicitation(increment_client, "thread-1") == {
        "threadId": "thread-1",
        "response": {"incremented": True},
    }
    assert increment_client.calls == [
        ("thread_increment_elicitation", {"threadId": "thread-1"}),
    ]

    decrement_client = FakeClient()
    assert thread_decrement_elicitation(decrement_client, "thread-1") == {
        "threadId": "thread-1",
        "response": {"decremented": True},
    }
    assert decrement_client.calls == [
        ("thread_decrement_elicitation", {"threadId": "thread-1"}),
    ]


def test_lib_rs_live_elicitation_timeout_pause_success(tmp_path) -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    script = tmp_path / "hold.sh"
    script.write_text("#!/bin/sh\n")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    client = FakeClient()

    def stream_turn(thread_id, turn_id):
        client.calls.append(("stream_turn", {"threadId": thread_id, "turnId": turn_id}))
        client.command_execution_outputs[:] = ["[elicitation-hold] start\n[elicitation-hold] done\n"]
        client.command_execution_statuses[:] = ["completed"]
        client.helper_done_seen = True
        client.last_turn_status = "completed"

    client.stream_turn = stream_turn
    calls = []

    def fake_connect(endpoint, config_overrides):
        calls.append((endpoint, config_overrides))
        return client

    ticks = iter([100.0, 116.0])
    result = live_elicitation_timeout_pause(
        codex_bin=None,
        url="ws://127.0.0.1:4222",
        config_overrides=["model=gpt-5"],
        model="gpt-5",
        workspace=workspace,
        script=script,
        hold_seconds=15,
        client_factory=fake_connect,
        monotonic=lambda: next(ticks),
        platform_name="posix",
        current_exe=Path("/tmp/codex-app-server-test-client"),
    )

    assert calls == [(ConnectWs("ws://127.0.0.1:4222"), [])]
    assert result["threadId"] == "thread-1"
    assert result["turnId"] == "turn-1"
    assert result["elapsed"] == 16.0
    assert result["commandStatuses"] == ["completed"]
    assert client.calls[1] == (
        "thread_start",
        {
            "model": "gpt-5",
            "modelProvider": None,
            "cwd": None,
            "approvalPolicy": None,
            "sandbox": None,
            "dynamicTools": None,
            "mockExperimentalField": None,
            "experimentalRawEvents": None,
        },
    )
    turn_params = client.calls[2][1]
    assert turn_params["approvalPolicy"] == "never"
    assert turn_params["sandboxPolicy"] == {"type": "dangerFullAccess"}
    assert turn_params["effort"] == "high"
    assert turn_params["cwd"] == str(workspace.resolve())
    assert "APP_SERVER_URL='ws://127.0.0.1:4222'" in turn_params["input"][0]["text"]
    assert ("thread_decrement_elicitation", {"threadId": "thread-1"}) in client.calls


def test_lib_rs_live_elicitation_timeout_pause_validates_inputs(tmp_path) -> None:
    script = tmp_path / "hold.sh"
    script.write_text("#!/bin/sh\n")

    with pytest.raises(AppServerTestClientError, match="POSIX shell"):
        live_elicitation_timeout_pause(
            codex_bin=None,
            url=None,
            config_overrides=[],
            model="gpt-5",
            workspace=tmp_path,
            script=script,
            hold_seconds=15,
            platform_name="nt",
        )

    with pytest.raises(AppServerTestClientError, match="greater than 10"):
        live_elicitation_timeout_pause(
            codex_bin=None,
            url=None,
            config_overrides=[],
            model="gpt-5",
            workspace=tmp_path,
            script=script,
            hold_seconds=10,
            platform_name="posix",
        )


def test_lib_rs_live_elicitation_timeout_pause_cleanup_runs_on_validation_error(tmp_path) -> None:
    script = tmp_path / "hold.sh"
    script.write_text("#!/bin/sh\n")
    client = FakeClient()

    def stream_turn(thread_id, turn_id):
        client.calls.append(("stream_turn", {"threadId": thread_id, "turnId": turn_id}))
        client.command_execution_outputs[:] = ["[elicitation-hold] start\n"]
        client.command_execution_statuses[:] = ["completed"]
        client.helper_done_seen = False
        client.last_turn_status = "completed"

    client.stream_turn = stream_turn

    with pytest.raises(AppServerTestClientError, match="completion marker"):
        live_elicitation_timeout_pause(
            codex_bin=None,
            url="ws://127.0.0.1:4222",
            config_overrides=[],
            model="gpt-5",
            workspace=tmp_path,
            script=script,
            hold_seconds=15,
            client_factory=lambda _endpoint, _config: client,
            monotonic=lambda: 20.0,
            platform_name="posix",
            current_exe=Path("/tmp/codex-app-server-test-client"),
        )

    assert ("thread_decrement_elicitation", {"threadId": "thread-1"}) in client.calls


@pytest.mark.asyncio
async def test_lib_rs_run_dispatches_small_command_subset() -> None:
    runner = Runner()

    assert await run(["--url", "ws://x", "model-list"], runner=runner) == "models"
    assert runner.calls[-1][1]["endpoint"] == ConnectWs("ws://x")

    result = await run(
        [
            "--codex-bin",
            "codex",
            "--dynamic-tools",
            '{"name":"demo"}',
            "send-message-v2",
            "--experimental-api",
            "hello",
        ],
        runner=runner,
    )
    assert result == "sent"
    assert runner.calls[-1][1]["dynamic_tools"] == [DynamicToolSpec(name="demo")]

    with pytest.raises(AppServerTestClientError, match="requires --experimental-api"):
        await run(["--dynamic-tools", '{"name":"demo"}', "send-message-v2", "hello"], runner=runner)


@pytest.mark.asyncio
async def test_lib_rs_run_dispatches_full_cli_command_inventory() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, CliCommand dispatch.
    commands = [
        (["serve"], "serve", {"codex_bin": __import__("pathlib").Path("codex"), "listen": "ws://127.0.0.1:4222", "kill": False}),
        (["serve", "--listen", "ws://0.0.0.0:4555", "--kill"], "serve", {"listen": "ws://0.0.0.0:4555", "kill": True}),
        (["send-message", "hello"], "send_message", {"user_message": "hello"}),
        (["resume-message-v2", "thread-1", "hello"], "resume_message_v2", {"thread_id": "thread-1", "user_message": "hello"}),
        (["thread-resume", "thread-1"], "thread_resume_follow", {"thread_id": "thread-1"}),
        (["watch"], "watch", {}),
        (["trigger-cmd-approval"], "trigger_cmd_approval", {"user_message": None}),
        (["trigger-cmd-approval", "prompt"], "trigger_cmd_approval", {"user_message": "prompt"}),
        (["trigger-patch-approval"], "trigger_patch_approval", {"user_message": None}),
        (["no-trigger-cmd-approval"], "no_trigger_cmd_approval", {}),
        (["send-follow-up-v2", "first", "second"], "send_follow_up_v2", {"first_message": "first", "follow_up_message": "second"}),
        (
            ["trigger-zsh-fork-multi-cmd-approval", "prompt", "--min-approvals", "3", "--abort-on", "2"],
            "trigger_zsh_fork_multi_cmd_approval",
            {"user_message": "prompt", "min_approvals": 3, "abort_on": 2},
        ),
        (["test-login", "--device-code"], "test_login", {"device_code": True}),
        (["get-account-rate-limits"], "get_account_rate_limits", {}),
        (["model-list"], "model_list", {}),
        (["thread-list", "--limit", "7"], "thread_list", {"limit": 7}),
        (["thread-increment-elicitation", "thread-1"], "thread_increment_elicitation", {"url": "ws://127.0.0.1:4222", "thread_id": "thread-1"}),
        (["thread-decrement-elicitation", "thread-1"], "thread_decrement_elicitation", {"url": "ws://127.0.0.1:4222", "thread_id": "thread-1"}),
        (
            ["live-elicitation-timeout-pause", "--model", "gpt-x", "--workspace", ".", "--script", "hold.sh", "--hold-seconds", "20"],
            "live_elicitation_timeout_pause",
            {"model": "gpt-x", "workspace": __import__("pathlib").Path("."), "script": __import__("pathlib").Path("hold.sh"), "hold_seconds": 20},
        ),
    ]

    for argv, expected_method, expected_subset in commands:
        runner = Runner()
        expected_return = "models" if expected_method == "model_list" else expected_method
        assert await run(argv, runner=runner) == expected_return
        method, kwargs = runner.calls[-1]
        assert method == expected_method
        for key, value in expected_subset.items():
            assert kwargs[key] == value


@pytest.mark.asyncio
async def test_lib_rs_run_dynamic_tools_follow_rust_command_gates() -> None:
    runner = Runner()

    result = await run(
        ["--dynamic-tools", '{"name":"demo"}', "trigger-cmd-approval", "prompt"],
        runner=runner,
    )
    assert result == "trigger_cmd_approval"
    assert runner.calls[-1][1]["dynamic_tools"] == [DynamicToolSpec(name="demo")]

    result = await run(
        ["--dynamic-tools", '{"name":"demo"}', "resume-message-v2", "thread-1", "prompt"],
        runner=runner,
    )
    assert result == "resume_message_v2"
    assert runner.calls[-1][1]["dynamic_tools"] == [DynamicToolSpec(name="demo")]

    with pytest.raises(AppServerTestClientError, match="dynamic tools"):
        await run(["--dynamic-tools", '{"name":"demo"}', "send-message", "prompt"], runner=runner)

    with pytest.raises(AppServerTestClientError, match="requires --url"):
        await run(
            ["--codex-bin", "codex", "thread-increment-elicitation", "thread-1"],
            runner=runner,
        )


def test_lib_rs_codex_client_waits_for_response_and_caches_notifications() -> None:
    transport = MemoryTransport(
        [
            {"jsonrpc": "2.0", "method": "thread/started", "params": {"id": "thread"}},
            {"jsonrpc": "2.0", "id": "req-1", "result": {"ok": True}},
        ]
    )
    client = CodexClient(transport)

    result = client.send_request(JSONRPCRequest("req-1", "model/list"), "req-1", "model/list")

    assert result == {"ok": True}
    assert json.loads(transport.written[0]) == {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "model/list",
    }
    notification = client.next_notification()
    assert notification.method == "thread/started"
    assert notification.params == {"id": "thread"}


def test_lib_rs_codex_client_handles_server_approval_requests() -> None:
    transport = MemoryTransport(
        [
            {
                "jsonrpc": "2.0",
                "id": "approval-1",
                "method": "commandExecution/requestApproval",
                "params": {"itemId": "item-1"},
            },
            {"jsonrpc": "2.0", "id": "req-1", "result": {"done": True}},
        ]
    )
    client = CodexClient(transport)
    client.command_approval_behavior = (CommandApprovalBehavior.ABORT_ON, 1)

    assert client.send_request(JSONRPCRequest("req-1", "turn/start"), "req-1", "turn/start") == {
        "done": True
    }

    approval_response = json.loads(transport.written[1])
    assert approval_response == {
        "jsonrpc": "2.0",
        "id": "approval-1",
        "result": {"decision": "cancel"},
    }
    assert client.command_approval_count == 1
    assert client.command_approval_item_ids == ["item-1"]


def test_lib_rs_codex_client_initialize_and_helper_output_tracking() -> None:
    transport = MemoryTransport([{"jsonrpc": "2.0", "id": "init", "result": {"initialized": True}}])
    client = CodexClient(transport)
    client.request_id = lambda: "init"  # type: ignore[method-assign]

    assert client.initialize_with_experimental_api(False) == {"initialized": True}

    initialize_request = json.loads(transport.written[0])
    assert initialize_request["method"] == "initialize"
    assert initialize_request["params"]["capabilities"]["experimentalApi"] is False
    assert initialize_request["params"]["capabilities"]["optOutNotificationMethods"]
    assert json.loads(transport.written[1]) == {"jsonrpc": "2.0", "method": "initialized"}

    client.note_helper_output("[elicitation-hold] start\n")
    assert client.helper_done_seen is False
    client.note_helper_output("[elicitation-hold] done\n")
    assert client.helper_done_seen is True


def test_lib_rs_codex_client_account_login_requests_use_real_methods() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, login_account_* helpers.
    transport = MemoryTransport(
        [
            {"jsonrpc": "2.0", "id": "login-1", "result": {"type": "chatgpt", "loginId": "id-1"}},
            {
                "jsonrpc": "2.0",
                "id": "login-2",
                "result": {"type": "chatgptDeviceCode", "loginId": "id-2"},
            },
        ]
    )
    client = CodexClient(transport)
    ids = iter(["login-1", "login-2"])
    client.request_id = lambda: next(ids)  # type: ignore[method-assign]

    assert client.login_account_chatgpt() == {"type": "chatgpt", "loginId": "id-1"}
    assert client.login_account_chatgpt_device_code() == {
        "type": "chatgptDeviceCode",
        "loginId": "id-2",
    }

    first = json.loads(transport.written[0])
    assert first["method"] == "account/login/start"
    assert first["params"] == {"type": "chatgpt", "codexStreamlinedLogin": False}
    second = json.loads(transport.written[1])
    assert second["method"] == "account/login/start"
    assert second["params"] == {"type": "chatgptDeviceCode"}


def test_lib_rs_codex_client_waits_for_matching_account_login_completion() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    expected = {"loginId": "wanted", "success": True, "error": None}
    transport = MemoryTransport(
        [
            {
                "jsonrpc": "2.0",
                "method": "account/login/completed",
                "params": {"loginId": "other", "success": False, "error": "ignored"},
            },
            {"jsonrpc": "2.0", "method": "account/rateLimits/updated", "params": {"primary": None}},
            {"jsonrpc": "2.0", "method": "account/login/completed", "params": expected},
        ]
    )
    client = CodexClient(transport)

    assert client.wait_for_account_login_completion("wanted") == expected


def test_lib_rs_codex_client_model_and_thread_list_default_params_are_protocol_shaped() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    transport = MemoryTransport(
        [
            {"jsonrpc": "2.0", "id": "model", "result": {"models": []}},
            {"jsonrpc": "2.0", "id": "threads", "result": {"threads": []}},
        ]
    )
    client = CodexClient(transport)
    ids = iter(["model", "threads"])
    client.request_id = lambda: next(ids)  # type: ignore[method-assign]

    assert model_list_params() == {"cursor": None, "limit": None, "includeHidden": None}
    assert thread_list_params(limit=7)["useStateDbOnly"] is False

    assert client.model_list() == {"models": []}
    assert client.thread_list(limit=7) == {"threads": []}

    model_request = json.loads(transport.written[0])
    assert model_request["method"] == "model/list"
    assert model_request["params"] == {"cursor": None, "limit": None, "includeHidden": None}
    thread_request = json.loads(transport.written[1])
    assert thread_request["method"] == "thread/list"
    assert thread_request["params"] == {
        "cursor": None,
        "limit": 7,
        "sortKey": None,
        "sortDirection": None,
        "modelProviders": None,
        "sourceKinds": None,
        "archived": None,
        "cwd": None,
        "useStateDbOnly": False,
        "searchTerm": None,
    }


def test_lib_rs_thread_and_turn_start_params_are_protocol_shaped() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    dynamic_tool = DynamicToolSpec(
        name="demo", description="Demo", inputSchema={"type": "object", "properties": {}}
    )
    sandbox = read_only_sandbox_policy(network_access=False)

    assert text_user_input("hello") == {"type": "text", "text": "hello", "text_elements": []}
    assert sandbox == {"type": "readOnly", "networkAccess": False}
    assert danger_full_access_sandbox_policy() == {"type": "dangerFullAccess"}

    assert thread_start_params(dynamic_tools=[dynamic_tool], model_provider="openai") == {
        "model": None,
        "modelProvider": "openai",
        "cwd": None,
        "approvalPolicy": None,
        "sandbox": None,
        "dynamicTools": [
            {
                "name": "demo",
                "description": "Demo",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ],
        "mockExperimentalField": None,
        "experimentalRawEvents": None,
    }
    assert turn_start_params(
        "thread-1", "hello", approval_policy="on-request", sandbox_policy=sandbox
    ) == {
        "threadId": "thread-1",
        "input": [{"type": "text", "text": "hello", "text_elements": []}],
        "cwd": None,
        "approvalPolicy": "on-request",
        "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
        "model": None,
        "serviceTier": None,
        "effort": None,
        "summary": None,
        "personality": None,
        "outputSchema": None,
    }


def test_lib_rs_codex_client_thread_and_turn_start_use_protocol_builders() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs.
    transport = MemoryTransport(
        [
            {"jsonrpc": "2.0", "id": "thread", "result": {"thread": {"id": "thread-1"}}},
            {"jsonrpc": "2.0", "id": "turn", "result": {"turn": {"id": "turn-1"}}},
        ]
    )
    client = CodexClient(transport)
    ids = iter(["thread", "turn"])
    client.request_id = lambda: next(ids)  # type: ignore[method-assign]

    assert client.thread_start(thread_start_params(dynamic_tools=[{"name": "demo"}])) == {
        "thread": {"id": "thread-1"}
    }
    assert client.turn_start(
        turn_start_params(
            "thread-1",
            "hello",
            approval_policy="on-request",
            sandbox_policy=read_only_sandbox_policy(network_access=False),
        )
    ) == {"turn": {"id": "turn-1"}}

    thread_request = json.loads(transport.written[0])
    assert thread_request["method"] == "thread/start"
    assert thread_request["params"]["dynamicTools"] == [{"name": "demo"}]
    turn_request = json.loads(transport.written[1])
    assert turn_request["method"] == "turn/start"
    assert turn_request["params"]["threadId"] == "thread-1"
    assert turn_request["params"]["input"] == [
        {"type": "text", "text": "hello", "text_elements": []}
    ]
    assert turn_request["params"]["approvalPolicy"] == "on-request"
    assert turn_request["params"]["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}


def test_lib_rs_codex_client_stream_turn_tracks_command_completion() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, CodexClient::stream_turn.
    transport = MemoryTransport(
        [
            {
                "jsonrpc": "2.0",
                "method": "thread/started",
                "params": {"thread": {"id": "thread-1"}},
            },
            {
                "jsonrpc": "2.0",
                "method": "turn/started",
                "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "running"}},
            },
            {
                "jsonrpc": "2.0",
                "method": "item/started",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {"type": "commandExecution", "id": "cmd-1"},
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "item/commandExecution/outputDelta",
                "params": {"threadId": "thread-1", "turnId": "turn-1", "itemId": "cmd-1", "delta": "a"},
            },
            {
                "jsonrpc": "2.0",
                "method": "item/completed",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {
                        "type": "commandExecution",
                        "id": "cmd-1",
                        "status": "completed",
                        "aggregatedOutput": "[elicitation-hold] done\n",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "completed", "error": None},
                },
            },
        ]
    )
    output: list[str] = []
    client = CodexClient(transport, output=output.append)

    client.stream_turn("thread-1", "turn-1")

    assert "".join(output) == (
        "< thread/started notification: {'id': 'thread-1'}\n"
        "< turn/started notification: 'running'\n"
        "\n< item started: {'type': 'commandExecution', 'id': 'cmd-1'}\n"
        "a"
        "< item completed: {'type': 'commandExecution', 'id': 'cmd-1', 'status': 'completed', "
        "'aggregatedOutput': '[elicitation-hold] done\\n'}\n"
        "\n< turn/completed notification: 'completed'\n"
    )
    assert client.command_item_started is True
    assert client.command_execution_statuses == ["completed"]
    assert client.command_execution_outputs == ["[elicitation-hold] done\n"]
    assert client.command_output_stream == "a[elicitation-hold] done\n"
    assert client.helper_done_seen is True
    assert client.last_turn_status == "completed"
    assert client.last_turn_error_message is None
    assert client.turn_completed_before_helper_done is False
    assert client.unexpected_items_before_helper_done == []


def test_lib_rs_codex_client_stream_turn_flags_items_before_helper_done() -> None:
    # Rust crate: codex-app-server-test-client, module: src/lib.rs, live elicitation guard.
    assistant_item = {"type": "agentMessage", "id": "agent-1"}
    transport = MemoryTransport(
        [
            {
                "jsonrpc": "2.0",
                "method": "item/started",
                "params": {"item": {"type": "commandExecution", "id": "cmd-1"}},
            },
            {"jsonrpc": "2.0", "method": "item/started", "params": {"item": assistant_item}},
            {
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "turn": {
                        "id": "turn-1",
                        "status": "failed",
                        "error": {"message": "helper still running"},
                    }
                },
            },
        ]
    )
    output: list[str] = []
    client = CodexClient(transport, output=output.append)

    client.stream_turn("thread-1", "turn-1")

    assert "[turn error] helper still running\n" in "".join(output)
    assert client.unexpected_items_before_helper_done == [assistant_item]
    assert client.turn_completed_before_helper_done is True
    assert client.last_turn_status == "failed"
    assert client.last_turn_error_message == "helper still running"


def test_lib_rs_codex_client_stream_notifications_forever_can_be_bounded() -> None:
    transport = MemoryTransport(
        [
            {"jsonrpc": "2.0", "method": "warning", "params": {"message": "one"}},
            {"jsonrpc": "2.0", "method": "warning", "params": {"message": "two"}},
        ]
    )
    client = CodexClient(transport)

    assert client.stream_notifications_forever(max_notifications=2) == 2
