from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from tests.support.core_test_support import (
    assert_regex_match,
    format_with_current_shell,
    test_absolute_path,
)
from tests.support.core_test_support.context_snapshot import (
    ContextSnapshotOptions,
    ContextSnapshotRenderMode,
    format_request_input_snapshot,
)
from tests.support.core_test_support.apps_test_server import AppsTestServer
from tests.support.core_test_support.hooks import (
    trusted_config_layer_stack,
)
from tests.support.core_test_support.process import (
    process_is_alive,
    wait_for_pid_file,
    wait_for_process_exit,
)
from tests.support.core_test_support.responses import (
    ev_assistant_message,
    ev_completed,
    ev_function_call,
    sse,
)
from tests.support.core_test_support.streaming_sse import (
    StreamingSseChunk,
    start_streaming_sse_server,
)
from tests.support.core_test_support.test_codex import test_codex
from tests.support.core_test_support.test_codex_exec import test_codex_exec
from tests.support.core_test_support.tracing import install_test_tracing
from tests.support.core_test_support.zsh_fork import (
    restrictive_workspace_write_profile,
    zsh_fork_runtime,
)


def test_lib_path_shell_and_regex_helpers_match_core_test_support_contract() -> None:
    # Rust: core/tests/common/lib.rs
    assert assert_regex_match(r"answer=(\d+)", "answer=42").group(1) == "42"
    assert test_absolute_path("/tmp/example").is_absolute()
    args = format_with_current_shell("echo core-test-support")
    assert args
    assert "echo core-test-support" in args[-1]


def test_response_helpers_emit_rust_responses_api_shapes() -> None:
    # Rust: core/tests/common/responses.rs
    completed = ev_completed("response-1")
    message = ev_assistant_message("message-1", "hello")
    function_call = ev_function_call("call-1", "lookup", '{"q":"codex"}')

    assert completed["type"] == "response.completed"
    assert completed["response"]["id"] == "response-1"
    assert message["type"] == "response.output_item.done"
    assert message["item"]["content"][0]["text"] == "hello"
    assert function_call["item"]["call_id"] == "call-1"
    assert "data: " + json.dumps(completed, separators=(",", ":")) in sse([completed])


def test_context_snapshot_renders_request_input_without_mutating_payload() -> None:
    # Rust: core/tests/common/context_snapshot.rs
    payload = {
        "model": "gpt-test",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ],
    }
    rendered = format_request_input_snapshot(
        payload,
        ContextSnapshotOptions(render_mode=ContextSnapshotRenderMode.FULL_TEXT),
    )

    assert rendered == "00:message/user:hello"
    assert payload["input"][0]["content"][0]["text"] == "hello"


@pytest.mark.asyncio
async def test_process_helpers_observe_real_child_lifecycle(tmp_path: Path) -> None:
    # Rust: core/tests/common/process.rs
    pid_file = tmp_path / "child.pid"
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import os,pathlib,time;"
                f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()), encoding='utf-8');"
                "time.sleep(0.2)"
            ),
        ]
    )
    try:
        pid = await wait_for_pid_file(pid_file)
        assert int(pid) == child.pid
        assert process_is_alive(pid)
        await wait_for_process_exit(pid, timeout=5.0)
        assert not process_is_alive(pid)
    finally:
        if child.poll() is None:
            child.kill()
        await asyncio.to_thread(child.wait)


def test_codex_exec_builder_invokes_real_cli_version(tmp_path: Path) -> None:
    # Rust: core/tests/common/test_codex_exec.rs
    builder = test_codex_exec(cwd=tmp_path)
    completed = builder.run("--version", timeout=30)

    assert completed.returncode == 0
    assert "codex" in completed.stdout.lower()


@pytest.mark.asyncio
async def test_streaming_sse_server_records_real_http_request() -> None:
    # Rust: core/tests/common/streaming_sse.rs
    server = await start_streaming_sse_server(
        [
            StreamingSseChunk.text("event: response.created\n\n"),
            StreamingSseChunk.text("event: response.completed\n\n", delay=0.01),
        ]
    )
    try:
        request = urllib.request.Request(
            server.uri(),
            data=b'{"input":"hello"}',
            method="POST",
        )
        response_body = await asyncio.to_thread(
            lambda: urllib.request.urlopen(request, timeout=5).read().decode()
        )
        await server.wait_for_request_count(1)
    finally:
        await server.shutdown()

    assert "response.created" in response_body
    assert await server.requests() == [b'{"input":"hello"}']


@pytest.mark.asyncio
async def test_apps_test_server_serves_real_initialize_and_records_tool_call() -> None:
    # Rust: core/tests/common/apps_test_server.rs
    server = await AppsTestServer.mount()
    call_id = "call-apps-1"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "calendar_create_event",
            "_meta": {"_codex_apps": {"call_id": call_id}},
        },
    }
    try:
        request = urllib.request.Request(
            server.chatgpt_base_url + "/api/codex/apps",
            data=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        response = await asyncio.to_thread(
            lambda: json.load(urllib.request.urlopen(request, timeout=5))
        )
        recorded = await server.recorded_apps_tool_call_by_call_id(call_id)
    finally:
        await server.shutdown()

    assert response["result"]["content"][0]["text"] == "ok"
    assert recorded["params"]["name"] == "calendar_create_event"


def test_hook_trust_and_tracing_helpers_keep_module_owned_state() -> None:
    # Rust: core/tests/common/hooks.rs and tracing.rs
    stack = trusted_config_layer_stack(
        {"user": {"config": {"model": "gpt-test"}}},
        Path("unused"),
        [{"key": "hook-a", "current_hash": "sha-a"}],
    )
    assert stack["user"]["config"]["hooks"]["state"]["hook-a"]["trusted_hash"] == "sha-a"

    tracing = install_test_tracing("pycodex.core-test-support")
    try:
        logging.getLogger("pycodex.core-test-support").warning("captured")
        assert [record.getMessage() for record in tracing.records] == ["captured"]
    finally:
        tracing.close()


@pytest.mark.asyncio
async def test_test_codex_builder_owns_workspace_and_real_cli(tmp_path: Path) -> None:
    # Rust: core/tests/common/test_codex.rs
    test = await test_codex().with_home(tmp_path / "home").build()
    await test.write_file("fixture.txt", "hello")

    assert await test.read_file_text("fixture.txt") == "hello"
    assert test.run("--version", timeout=30).returncode == 0


def test_zsh_fork_fixture_is_platform_gated() -> None:
    # Rust: core/tests/common/zsh_fork.rs
    profile = restrictive_workspace_write_profile()
    assert profile["sandbox_mode"] == "workspace-write"
    runtime = zsh_fork_runtime("module-contract")
    if sys.platform == "win32":
        assert runtime is None
    elif runtime is not None:
        assert runtime.zsh_path.is_file()
