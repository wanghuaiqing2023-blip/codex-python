"""Prepared parity tests for Rust ``codex-debug-client/src/client.rs``.

Pytest is deferred until the full ``codex-debug-client`` crate is functionally
complete, per the crate-level porting workflow.
"""

from __future__ import annotations

import io
import json

from pycodex.debug_client.client import (
    AppServerClient,
    build_thread_resume_params,
    build_thread_start_params,
    handle_server_request,
    send_jsonrpc_response,
    send_with_stdin,
)
from pycodex.debug_client.output import Output
from pycodex.debug_client.reader import COMMAND_APPROVAL_METHOD, FILE_CHANGE_APPROVAL_METHOD
from pycodex.debug_client.state import PendingRequest


class FakeChild:
    def __init__(self) -> None:
        self.waited = False

    def wait(self) -> int:
        self.waited = True
        return 0


def make_client(stdout_text: str = "", *, filtered_output: bool = False) -> tuple[AppServerClient, io.StringIO, io.StringIO]:
    stdin = io.StringIO()
    out = io.StringIO()
    output = Output.new(None, stdout=out, stderr=io.StringIO(), color=False)
    client = AppServerClient(
        child=FakeChild(),
        stdin=stdin,
        stdout=io.StringIO(stdout_text),
        output=output,
        filtered_output=filtered_output,
    )
    return client, stdin, out


def sent_messages(stdin: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stdin.getvalue().splitlines()]


def test_send_with_stdin_writes_compact_json_line() -> None:
    # Rust source: send_with_stdin serializes one JSON message plus newline.
    stdin = io.StringIO()

    send_with_stdin(stdin, {"method": "initialized"})

    assert stdin.getvalue() == '{"method":"initialized"}\n'


def test_send_jsonrpc_response_writes_result_message() -> None:
    # Rust source: send_jsonrpc_response wraps response as JSONRPCResponse.
    stdin = io.StringIO()

    send_jsonrpc_response(stdin, 7, {"decision": "decline"})

    assert sent_messages(stdin) == [{"id": 7, "result": {"decision": "decline"}}]


def test_build_thread_start_and_resume_params_match_rust_fields() -> None:
    # Rust source: build_thread_start_params and build_thread_resume_params.
    assert build_thread_start_params("on-request", "gpt", "openai", "C:/repo") == {
        "model": "gpt",
        "modelProvider": "openai",
        "cwd": "C:/repo",
        "approvalPolicy": "on-request",
        "experimentalRawEvents": False,
    }
    assert build_thread_resume_params("thr-1", "never", None, None, None) == {
        "threadId": "thr-1",
        "model": None,
        "modelProvider": None,
        "cwd": None,
        "approvalPolicy": "never",
    }


def test_initialize_sends_initialize_then_initialized() -> None:
    # Rust source: initialize waits for InitializeResponse then sends Initialized notification.
    client, stdin, _stdout = make_client('{"id":1,"result":{}}\n')

    client.initialize()

    messages = sent_messages(stdin)
    assert messages[0]["method"] == "initialize"
    assert messages[0]["id"] == 1
    params = messages[0]["params"]
    assert params["clientInfo"]["name"] == "debug-client"
    assert params["clientInfo"]["title"] == "Debug Client"
    assert params["capabilities"]["experimentalApi"] is True
    assert params["capabilities"]["requestAttestation"] is False
    assert messages[1] == {"method": "initialized"}


def test_start_and_resume_thread_read_response_and_remember_thread() -> None:
    # Rust source: start_thread/resume_thread decode thread id and set active thread.
    client, stdin, _stdout = make_client(
        '{"id":1,"result":{"thread":{"id":"thr-start"}}}\n'
        '{"id":2,"result":{"thread":{"id":"thr-resume"}}}\n'
    )

    assert client.start_thread({"approvalPolicy": "never"}) == "thr-start"
    assert client.resume_thread({"threadId": "thr-resume", "approvalPolicy": "never"}) == "thr-resume"

    assert client.thread_id() == "thr-resume"
    assert client.state.known_threads == ["thr-start", "thr-resume"]
    assert [message["method"] for message in sent_messages(stdin)] == ["thread/start", "thread/resume"]


def test_request_thread_methods_track_pending_and_send_requests() -> None:
    # Rust source: request_* methods track PendingRequest before sending async requests.
    client, stdin, _stdout = make_client()

    start_id = client.request_thread_start({"approvalPolicy": "on-request"})
    resume_id = client.request_thread_resume({"threadId": "thr-1"})
    list_id = client.request_thread_list("cursor")

    assert (start_id, resume_id, list_id) == (1, 2, 3)
    assert client.state.pending == {
        "1": PendingRequest.START,
        "2": PendingRequest.RESUME,
        "3": PendingRequest.LIST,
    }
    messages = sent_messages(stdin)
    assert [message["method"] for message in messages] == ["thread/start", "thread/resume", "thread/list"]
    assert messages[2]["params"]["cursor"] == "cursor"
    assert messages[2]["params"]["useStateDbOnly"] is False


def test_send_turn_sends_plain_text_user_input() -> None:
    # Rust source: send_turn sends TurnStartParams with one UserInput::Text and no UI spans.
    client, stdin, _stdout = make_client()

    request_id = client.send_turn("thr-1", "hello")

    assert request_id == 1
    assert sent_messages(stdin) == [
        {
            "method": "turn/start",
            "id": 1,
            "params": {
                "threadId": "thr-1",
                "input": [{"type": "text", "text": "hello", "textElements": []}],
            },
        }
    ]


def test_use_thread_reports_known_and_remembers_unknown() -> None:
    # Rust source: use_thread returns whether the id was already known and always sets active thread.
    client, _stdin, _stdout = make_client()
    client.set_thread_id("thr-1")

    assert client.use_thread("thr-1") is True
    assert client.use_thread("thr-2") is False
    assert client.thread_id() == "thr-2"
    assert client.state.known_threads == ["thr-1", "thr-2"]


def test_read_until_response_logs_json_and_declines_approval_requests() -> None:
    # Rust source: read_until_response logs lines, ignores invalid JSON, declines server approvals.
    client, stdin, stdout = make_client(
        "not json\n"
        '{"method":"item/commandExecution/requestApproval","id":"srv-1","params":{}}\n'
        '{"id":1,"result":{"ok":true}}\n'
    )

    response = client.read_until_response(1)

    assert response == {"id": 1, "result": {"ok": True}}
    assert sent_messages(stdin) == [{"id": "srv-1", "result": {"decision": {"type": "decline"}}}]
    assert stdout.getvalue().splitlines() == [
        "not json",
        '{"method":"item/commandExecution/requestApproval","id":"srv-1","params":{}}',
        '{"id":1,"result":{"ok":true}}',
    ]


def test_handle_server_request_declines_command_and_file_approvals() -> None:
    # Rust source: private client.rs handler declines both approval request kinds.
    stdin = io.StringIO()

    handle_server_request({"method": COMMAND_APPROVAL_METHOD, "id": "cmd"}, stdin)
    handle_server_request({"method": FILE_CHANGE_APPROVAL_METHOD, "id": "file"}, stdin)
    handle_server_request({"method": "unknown", "id": "ignored"}, stdin)

    assert sent_messages(stdin) == [
        {"id": "cmd", "result": {"decision": {"type": "decline"}}},
        {"id": "file", "result": {"decision": "decline"}},
    ]


def test_start_reader_consumes_stdout_once() -> None:
    # Rust source: start_reader takes stdout and rejects a second start.
    client, _stdin, _stdout = make_client("")
    events: list[object] = []

    client.start_reader(events, auto_approve=False, filtered_output=False)

    assert client.stdout is None
    try:
        client.start_reader(events, auto_approve=False, filtered_output=False)
    except RuntimeError as exc:
        assert str(exc) == "reader already started"
    else:  # pragma: no cover - assertion guard.
        raise AssertionError("expected reader already started")


def test_shutdown_drops_stdin_and_waits_for_child() -> None:
    # Rust source: shutdown takes stdin and waits for child.
    client, _stdin, _stdout = make_client()
    child = client.child

    client.shutdown()

    assert client.stdin is None
    assert child.waited is True
