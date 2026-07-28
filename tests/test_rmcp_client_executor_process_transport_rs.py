from __future__ import annotations

import json

import pytest

from pycodex.exec_server.process import ExecProcess, ExecProcessEvent, ExecProcessEventReceiver
from pycodex.exec_server.protocol import (
    ByteChunk,
    ExecOutputStream,
    ProcessOutputChunk,
    ReadResponse,
    WriteResponse,
    WriteStatus,
)
from pycodex.rmcp_client.executor_process_transport import ExecutorProcessTransport


class _Process(ExecProcess):
    def __init__(self, events: list[ExecProcessEvent]) -> None:
        self.events = ExecProcessEventReceiver(events)
        self.writes: list[bytes] = []
        self.terminate_calls = 0

    def subscribe_events(self) -> ExecProcessEventReceiver:
        return self.events

    async def write(self, chunk: bytes) -> WriteResponse:
        self.writes.append(bytes(chunk))
        return WriteResponse(WriteStatus.ACCEPTED)

    async def read(
        self,
        after_seq: int | None,
        max_bytes: int | None,
        wait_ms: int | None,
    ) -> ReadResponse:
        return ReadResponse([], 1, False, None, True)

    async def terminate(self) -> None:
        self.terminate_calls += 1


@pytest.mark.asyncio
async def test_executor_transport_frames_json_and_ignores_stderr() -> None:
    # Rust: executor_process_transport.rs Transport<RoleClient>.
    response = {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}
    process = _Process(
        [
            ExecProcessEvent.output(
                ProcessOutputChunk(
                    1,
                    ExecOutputStream.STDERR,
                    ByteChunk(b"diagnostic\n"),
                )
            ),
            ExecProcessEvent.output(
                ProcessOutputChunk(
                    2,
                    ExecOutputStream.STDOUT,
                    ByteChunk(json.dumps(response).encode("utf-8") + b"\n"),
                )
            ),
        ]
    )
    transport = ExecutorProcessTransport(process, "fixture")

    request = {"jsonrpc": "2.0", "id": 7, "method": "ping"}
    await transport.send(request)
    received = await transport.receive()
    await transport.close()

    assert process.writes == [json.dumps(request, separators=(",", ":")).encode() + b"\n"]
    assert received == response
    assert process.terminate_calls == 1


@pytest.mark.asyncio
async def test_executor_transport_rejects_closed_stdin() -> None:
    class _ClosedProcess(_Process):
        async def write(self, chunk: bytes) -> WriteResponse:
            return WriteResponse(WriteStatus.STDIN_CLOSED)

    transport = ExecutorProcessTransport(_ClosedProcess([]), "fixture")
    with pytest.raises(BrokenPipeError, match="stdin closed"):
        await transport.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})

