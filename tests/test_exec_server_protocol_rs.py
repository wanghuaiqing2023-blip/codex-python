"""Rust-derived tests for codex-exec-server/src/protocol.rs."""

from __future__ import annotations

import pytest

from pycodex.exec_server import (
    ByteChunk,
    ExecClosedNotification,
    ExecEnvPolicy,
    ExecExitedNotification,
    ExecOutputDeltaNotification,
    ExecOutputStream,
    ExecParams,
    HttpHeader,
    HttpRequestBodyDeltaNotification,
    HttpRequestParams,
    HttpRequestResponse,
    ProcessId,
    ProcessOutputChunk,
    ReadResponse,
    decode_exec_params,
    decode_http_request_params,
    decode_read_params,
    decode_terminate_params,
    decode_write_params,
    encode_exec_closed_notification,
    encode_exec_exited_notification,
    encode_exec_output_delta_notification,
    encode_http_request_body_delta_notification,
    encode_http_request_response,
    encode_read_response,
    encode_write_response,
    WriteResponse,
    WriteStatus,
)
from pycodex.protocol import ShellEnvironmentPolicyInherit


def test_bytechunk_is_transparent_base64_wire_value():
    # Rust: codex-exec-server/src/protocol.rs::ByteChunk and base64_bytes
    # Contract: protocol byte chunks serialize as one base64 string and decode
    # back to the original bytes.
    chunk = ByteChunk(b"hello\x00world")

    assert chunk.to_base64() == "aGVsbG8Ad29ybGQ="
    assert ByteChunk.from_base64("aGVsbG8Ad29ybGQ=").into_inner() == b"hello\x00world"
    with pytest.raises(Exception):
        ByteChunk.from_base64("not valid base64!")


def test_exec_params_decode_camel_case_defaults_and_env_policy():
    # Rust: codex-exec-server/src/protocol.rs::ExecParams/ExecEnvPolicy
    # Contract: serde camelCase fields decode into typed protocol values, with
    # omitted envPolicy/pipeStdin/arg0 using the Rust defaults.
    minimal = decode_exec_params(
        {
            "processId": "proc-1",
            "argv": ["python", "-V"],
            "cwd": "/tmp",
            "env": {"A": "B"},
            "tty": False,
        }
    )
    with_policy = decode_exec_params(
        {
            "processId": "proc-2",
            "argv": ["sh"],
            "cwd": "/work",
            "envPolicy": {
                "inherit": "core",
                "ignoreDefaultExcludes": True,
                "exclude": ["SECRET"],
                "set": {"X": "Y"},
                "includeOnly": ["PATH"],
            },
            "env": {},
            "tty": True,
            "pipeStdin": True,
            "arg0": "login-sh",
        }
    )

    assert minimal == ExecParams(
        process_id=ProcessId.new("proc-1"),
        argv=["python", "-V"],
        cwd="/tmp",
        env={"A": "B"},
        tty=False,
    )
    assert with_policy.env_policy == ExecEnvPolicy(
        inherit=ShellEnvironmentPolicyInherit.CORE,
        ignore_default_excludes=True,
        exclude=["SECRET"],
        set={"X": "Y"},
        include_only=["PATH"],
    )
    assert with_policy.pipe_stdin is True
    assert with_policy.arg0 == "login-sh"


def test_process_request_response_wire_shapes_use_base64_and_camel_case():
    # Rust: codex-exec-server/src/protocol.rs::{ReadParams,WriteParams,TerminateParams,ReadResponse,WriteResponse}
    # Contract: process request params and responses use Rust camelCase names,
    # transparent process ids, and base64 byte chunks.
    read = decode_read_params({"processId": "proc", "afterSeq": None, "maxBytes": 128, "waitMs": 25})
    write = decode_write_params({"processId": "proc", "chunk": "aGk="})
    terminate = decode_terminate_params({"processId": "proc"})

    assert read.process_id == ProcessId.new("proc")
    assert read.max_bytes == 128
    assert write.chunk.into_inner() == b"hi"
    assert terminate.process_id == ProcessId.new("proc")
    assert encode_read_response(
        ReadResponse(
            chunks=[ProcessOutputChunk(seq=7, stream=ExecOutputStream.STDOUT, chunk=ByteChunk(b"out"))],
            next_seq=8,
            exited=True,
            exit_code=0,
            closed=True,
        )
    ) == {
        "chunks": [{"seq": 7, "stream": "stdout", "chunk": "b3V0"}],
        "nextSeq": 8,
        "exited": True,
        "exitCode": 0,
        "closed": True,
        "failure": None,
    }
    assert encode_write_response(WriteResponse(WriteStatus.STDIN_CLOSED)) == {"status": "stdinClosed"}


def test_http_request_timeout_treats_omitted_and_null_as_no_timeout():
    # Rust: codex-exec-server/src/protocol.rs test
    # `http_request_timeout_treats_omitted_and_null_as_no_timeout`.
    # Contract: omitted and null timeoutMs both decode to None; a number is
    # preserved as the exact millisecond deadline.
    omitted = decode_http_request_params(
        {"method": "GET", "url": "https://example.test", "requestId": "req-omitted-timeout"}
    )
    null_timeout = decode_http_request_params(
        {"method": "GET", "url": "https://example.test", "requestId": "req-null-timeout", "timeoutMs": None}
    )
    explicit_timeout = decode_http_request_params(
        {"method": "GET", "url": "https://example.test", "requestId": "req-explicit-timeout", "timeoutMs": 1234}
    )

    assert (omitted.request_id, omitted.timeout_ms) == ("req-omitted-timeout", None)
    assert (null_timeout.request_id, null_timeout.timeout_ms) == ("req-null-timeout", None)
    assert (explicit_timeout.request_id, explicit_timeout.timeout_ms) == ("req-explicit-timeout", 1234)


def test_http_request_and_response_wire_shapes():
    # Rust: codex-exec-server/src/protocol.rs::{HttpRequestParams,HttpRequestResponse}
    # Contract: headers default to an ordered list, body uses bodyBase64, and
    # streamResponse defaults false unless explicitly set.
    request = decode_http_request_params(
        {
            "method": "POST",
            "url": "https://example.test/upload",
            "headers": [{"name": "x-test", "value": "1"}],
            "bodyBase64": "cGF5bG9hZA==",
            "requestId": "req-1",
            "streamResponse": True,
        }
    )

    assert request == HttpRequestParams(
        method="POST",
        url="https://example.test/upload",
        headers=[HttpHeader("x-test", "1")],
        request_id="req-1",
        body=ByteChunk(b"payload"),
        stream_response=True,
    )
    assert encode_http_request_response(
        HttpRequestResponse(status=201, headers=[HttpHeader("content-type", "text/plain")], body=ByteChunk(b"ok"))
    ) == {
        "status": 201,
        "headers": [{"name": "content-type", "value": "text/plain"}],
        "bodyBase64": "b2s=",
    }


def test_notification_wire_shapes_use_rust_field_names():
    # Rust: codex-exec-server/src/protocol.rs::{HttpRequestBodyDeltaNotification,Exec*Notification}
    # Contract: streamed HTTP and process notifications use camelCase names and
    # base64 byte fields named like the Rust serde attributes.
    assert encode_http_request_body_delta_notification(
        HttpRequestBodyDeltaNotification(request_id="req", seq=1, delta=ByteChunk(b"part"), done=True)
    ) == {"requestId": "req", "seq": 1, "deltaBase64": "cGFydA==", "done": True}
    assert encode_exec_output_delta_notification(
        ExecOutputDeltaNotification(
            process_id=ProcessId.new("proc"),
            seq=2,
            stream=ExecOutputStream.STDERR,
            chunk=ByteChunk(b"err"),
        )
    ) == {"processId": "proc", "seq": 2, "stream": "stderr", "chunk": "ZXJy"}
    assert encode_exec_exited_notification(ExecExitedNotification(ProcessId.new("proc"), 3, 9)) == {
        "processId": "proc",
        "seq": 3,
        "exitCode": 9,
    }
    assert encode_exec_closed_notification(ExecClosedNotification(ProcessId.new("proc"), 4)) == {
        "processId": "proc",
        "seq": 4,
    }
