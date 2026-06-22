from __future__ import annotations

import asyncio

import pytest

from pycodex.app_server_protocol.jsonrpc_lite import JSONRPCMessage, JSONRPCRequest
from pycodex.exec_server import (
    ExecServerError,
    RelayData,
    RelayFrameBodyKind,
    RelayMessageFrame,
    RelayReset,
    RelayResume,
    JsonRpcConnectionEvent,
    JsonRpcWebSocketMessage,
    decode_relay_message_frame,
    encode_relay_message_frame,
    harness_connection_from_websocket,
    jsonrpc_payload,
    run_multiplexed_environment,
)


def test_relay_resume_frame_uses_rust_prost_wire_shape() -> None:
    # Rust crate/module:
    # codex-exec-server/src/relay.rs::RelayMessageFrame::resume and
    # src/relay_proto.rs generated prost message layout.
    # Contract: resume frames use version 1, the stream_id field, and an empty
    # oneof resume body at field number 7.
    frame = RelayMessageFrame.resume("stream-1")

    encoded = encode_relay_message_frame(frame)
    decoded = decode_relay_message_frame(encoded)

    assert encoded == b"\x08\x01\x12\x08stream-1\x3a\x00"
    assert decoded == frame
    assert decoded.validate() is RelayFrameBodyKind.RESUME


def test_relay_data_frame_encodes_and_decodes_jsonrpc_payload() -> None:
    # Rust crate/module:
    # codex-exec-server/src/relay.rs::{RelayMessageFrame::data,jsonrpc_payload,into_jsonrpc_message}.
    # Contract: JSON-RPC messages are compact JSON bytes inside a single-segment
    # RelayData body, and data frames validate back to JSONRPCMessage.
    message = JSONRPCMessage(JSONRPCRequest(id=1, method="test", params=None))
    payload = jsonrpc_payload(message)
    frame = RelayMessageFrame.data("s", 7, payload)

    encoded = encode_relay_message_frame(frame)
    decoded = decode_relay_message_frame(encoded)

    assert encoded == b"\x08\x01\x12\x01s\x2a\x1e\x08\x07\x18\x01\x22\x18{\"id\":1,\"method\":\"test\"}"
    assert decoded.validate() is RelayFrameBodyKind.DATA
    assert isinstance(decoded.body, RelayData)
    assert decoded.body.seq == 7
    assert decoded.body.segment_index == 0
    assert decoded.body.segment_count == 1
    assert decoded.into_jsonrpc_message() == message


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (
            RelayMessageFrame(version=2, stream_id="s", body_kind=RelayFrameBodyKind.RESUME, body=RelayResume()),
            "exec-server protocol error: unsupported relay message frame version 2",
        ),
        (
            RelayMessageFrame(version=1, stream_id=" ", body_kind=RelayFrameBodyKind.RESUME, body=RelayResume()),
            "exec-server protocol error: relay message frame is missing stream_id",
        ),
        (
            RelayMessageFrame.data("s", 0, b""),
            "exec-server protocol error: relay data message frame is missing required fields",
        ),
        (
            RelayMessageFrame(version=1, stream_id="s", body_kind=RelayFrameBodyKind.RESET, body=RelayReset("")),
            "exec-server protocol error: relay reset message frame is missing reason",
        ),
        (
            RelayMessageFrame(version=1, stream_id="s"),
            "exec-server protocol error: relay message frame is missing body",
        ),
    ],
)
def test_relay_frame_validation_errors_match_rust(frame: RelayMessageFrame, message: str) -> None:
    # Rust source contract:
    # codex-exec-server/src/relay.rs::RelayMessageFrame::validate.
    with pytest.raises(ExecServerError) as exc_info:
        frame.validate()
    assert str(exc_info.value) == message


def test_relay_non_data_frame_is_not_jsonrpc_payload() -> None:
    # Rust source contract:
    # codex-exec-server/src/relay.rs::RelayMessageFrame::into_jsonrpc_message.
    with pytest.raises(ExecServerError) as exc_info:
        RelayMessageFrame.resume("stream-1").into_jsonrpc_message()
    assert str(exc_info.value) == "exec-server protocol error: expected relay data message frame"


def test_relay_reset_reason_only_returns_nonempty_reset_reason() -> None:
    # Rust source contract:
    # codex-exec-server/src/relay.rs::RelayMessageFrame::into_reset_reason.
    reset = RelayMessageFrame(version=1, stream_id="s", body_kind=RelayFrameBodyKind.RESET, body=RelayReset("bye"))
    data = RelayMessageFrame.data("s", 1, b"{}")

    assert reset.into_reset_reason() == "bye"
    assert data.into_reset_reason() is None


def test_decode_relay_message_frame_maps_malformed_protobuf_to_protocol_error() -> None:
    # Rust source contract:
    # codex-exec-server/src/relay.rs::decode_relay_message_frame.
    with pytest.raises(ExecServerError) as exc_info:
        decode_relay_message_frame(b"\x80")
    assert str(exc_info.value).startswith(
        "exec-server protocol error: invalid relay message frame: unexpected EOF while reading varint"
    )


def test_harness_connection_receives_relay_data() -> None:
    # Rust test:
    # codex-exec-server/src/relay.rs::tests::harness_connection_receives_relay_data.
    # Contract: the harness connection sends an initial resume frame and routes
    # matching relay data frames into JsonRpcConnectionEvent::Message.
    async def run() -> tuple[str, JsonRpcConnectionEvent]:
        websocket = ControlledRelayWebSocket()
        connection = harness_connection_from_websocket(websocket, "test")
        try:
            resume = await asyncio.wait_for(websocket.outgoing.get(), 1)
            assert resume.kind == "binary"
            assert isinstance(resume.data, bytes)
            stream_id = decode_relay_message_frame(resume.data).stream_id
            message = JSONRPCMessage(JSONRPCRequest(id=1, method="test"))
            await websocket.incoming.put(
                JsonRpcWebSocketMessage.binary(
                    encode_relay_message_frame(
                        RelayMessageFrame.data(stream_id, 0, jsonrpc_payload(message))
                    )
                )
            )
            event = await asyncio.wait_for(connection.incoming_rx.get(), 1)
            return stream_id, event
        finally:
            await connection.close()

    stream_id, event = asyncio.run(run())

    assert stream_id
    assert event == JsonRpcConnectionEvent.message_event(JSONRPCMessage(JSONRPCRequest(id=1, method="test")))


def test_harness_connection_reports_text_frames_as_malformed() -> None:
    # Rust test:
    # codex-exec-server/src/relay.rs::tests::harness_connection_reports_text_frames_as_malformed.
    async def run() -> JsonRpcConnectionEvent:
        websocket = ControlledRelayWebSocket()
        connection = harness_connection_from_websocket(websocket, "test")
        try:
            await asyncio.wait_for(websocket.outgoing.get(), 1)
            await websocket.incoming.put(JsonRpcWebSocketMessage.text("nope"))
            return await asyncio.wait_for(connection.incoming_rx.get(), 1)
        finally:
            await connection.close()

    event = asyncio.run(run())

    assert event == JsonRpcConnectionEvent.malformed_message(
        "relay exec-server transport expects binary protobuf frames"
    )


def test_harness_connection_reports_server_close() -> None:
    # Rust test:
    # codex-exec-server/src/relay.rs::tests::harness_connection_reports_server_close.
    async def run() -> JsonRpcConnectionEvent:
        websocket = ControlledRelayWebSocket()
        connection = harness_connection_from_websocket(websocket, "test")
        try:
            await asyncio.wait_for(websocket.outgoing.get(), 1)
            await websocket.incoming.put(JsonRpcWebSocketMessage.close())
            return await asyncio.wait_for(connection.incoming_rx.get(), 1)
        finally:
            await connection.close()

    assert asyncio.run(run()) == JsonRpcConnectionEvent.disconnected(None)


def test_harness_connection_keeps_outbound_frame_while_send_is_backpressured() -> None:
    # Rust test:
    # codex-exec-server/src/relay.rs::tests::harness_connection_keeps_outbound_frame_while_send_is_backpressured.
    # Contract: while an outbound relay data frame write is blocked, ignored
    # inbound frames do not advance the single relay transport loop and the
    # data frame is still written once backpressure clears.
    async def run() -> tuple[bool, RelayMessageFrame]:
        websocket = ControlledRelayWebSocket()
        connection = harness_connection_from_websocket(websocket, "test")
        try:
            resume = await asyncio.wait_for(websocket.outgoing.get(), 1)
            assert isinstance(resume.data, bytes)
            stream_id = decode_relay_message_frame(resume.data).stream_id
            websocket.block_writes()
            message = JSONRPCMessage(JSONRPCRequest(id=1, method="test"))
            await connection.outgoing_tx.put(message)
            await websocket.wait_for_blocked_write()
            await websocket.incoming.put(JsonRpcWebSocketMessage.pong(b"check"))
            try:
                await asyncio.wait_for(connection.incoming_rx.get(), 0.05)
                no_event = False
            except TimeoutError:
                no_event = True
            websocket.release_write()
            outgoing = await asyncio.wait_for(websocket.outgoing.get(), 1)
            assert outgoing.kind == "binary"
            assert isinstance(outgoing.data, bytes)
            frame = decode_relay_message_frame(outgoing.data)
            assert frame.stream_id == stream_id
            return no_event, frame
        finally:
            await connection.close()

    no_event, frame = asyncio.run(run())

    assert no_event is True
    assert frame.into_jsonrpc_message() == JSONRPCMessage(JSONRPCRequest(id=1, method="test"))


def test_run_multiplexed_environment_spawns_virtual_stream_and_frames_processor_response() -> None:
    # Rust source contract:
    # codex-exec-server/src/relay.rs::run_multiplexed_environment and
    # spawn_virtual_stream.
    # Contract: a relay data frame creates a virtual JSON-RPC connection for
    # that stream, feeds the decoded message to the processor, and frames the
    # processor's outbound JSON-RPC message back onto the physical websocket.
    async def run() -> tuple[JsonRpcConnectionEvent, RelayMessageFrame]:
        websocket = ControlledRelayWebSocket()
        response = JSONRPCMessage(JSONRPCRequest(id=2, method="reply"))
        processor = RecordingRelayProcessor(response=response, stop_after_response=True)
        task = asyncio.create_task(run_multiplexed_environment(websocket, processor))
        try:
            request = JSONRPCMessage(JSONRPCRequest(id=1, method="test"))
            await websocket.incoming.put(
                JsonRpcWebSocketMessage.binary(
                    encode_relay_message_frame(
                        RelayMessageFrame.data("stream-a", 3, jsonrpc_payload(request))
                    )
                )
            )
            event = await asyncio.wait_for(processor.events.get(), 1)
            outgoing = await asyncio.wait_for(websocket.outgoing.get(), 1)
            assert outgoing.kind == "binary"
            assert isinstance(outgoing.data, bytes)
            return event, decode_relay_message_frame(outgoing.data)
        finally:
            await websocket.incoming.put(JsonRpcWebSocketMessage.close())
            await asyncio.wait_for(task, 1)

    event, frame = asyncio.run(run())

    assert event == JsonRpcConnectionEvent.message_event(JSONRPCMessage(JSONRPCRequest(id=1, method="test")))
    assert frame.stream_id == "stream-a"
    assert frame.validate() is RelayFrameBodyKind.DATA
    assert isinstance(frame.body, RelayData)
    assert frame.body.seq == 0
    assert frame.into_jsonrpc_message() == JSONRPCMessage(JSONRPCRequest(id=2, method="reply"))


def test_run_multiplexed_environment_reset_disconnects_matching_virtual_stream() -> None:
    # Rust source contract:
    # codex-exec-server/src/relay.rs::run_multiplexed_environment reset branch
    # and VirtualStream::disconnect.
    async def run() -> list[JsonRpcConnectionEvent]:
        websocket = ControlledRelayWebSocket()
        processor = RecordingRelayProcessor()
        task = asyncio.create_task(run_multiplexed_environment(websocket, processor))
        try:
            request = JSONRPCMessage(JSONRPCRequest(id=1, method="test"))
            await websocket.incoming.put(
                JsonRpcWebSocketMessage.binary(
                    encode_relay_message_frame(
                        RelayMessageFrame.data("stream-reset", 0, jsonrpc_payload(request))
                    )
                )
            )
            await websocket.incoming.put(
                JsonRpcWebSocketMessage.binary(
                    encode_relay_message_frame(RelayMessageFrame.reset("stream-reset", "bye"))
                )
            )
            return [
                await asyncio.wait_for(processor.events.get(), 1),
                await asyncio.wait_for(processor.events.get(), 1),
            ]
        finally:
            await websocket.incoming.put(JsonRpcWebSocketMessage.close())
            await asyncio.wait_for(task, 1)

    events = asyncio.run(run())

    assert events == [
        JsonRpcConnectionEvent.message_event(JSONRPCMessage(JSONRPCRequest(id=1, method="test"))),
        JsonRpcConnectionEvent.disconnected("bye"),
    ]


def test_run_multiplexed_environment_close_disconnects_active_virtual_streams() -> None:
    # Rust source contract:
    # codex-exec-server/src/relay.rs::run_multiplexed_environment loop exit.
    # Contract: when the physical websocket closes, all active virtual streams
    # receive a disconnected event with no reason.
    async def run() -> list[JsonRpcConnectionEvent]:
        websocket = ControlledRelayWebSocket()
        processor = RecordingRelayProcessor()
        task = asyncio.create_task(run_multiplexed_environment(websocket, processor))
        request = JSONRPCMessage(JSONRPCRequest(id=1, method="test"))
        await websocket.incoming.put(
            JsonRpcWebSocketMessage.binary(
                encode_relay_message_frame(RelayMessageFrame.data("stream-close", 0, jsonrpc_payload(request)))
            )
        )
        first = await asyncio.wait_for(processor.events.get(), 1)
        await websocket.incoming.put(JsonRpcWebSocketMessage.close())
        await asyncio.wait_for(task, 1)
        second = await asyncio.wait_for(processor.events.get(), 1)
        return [first, second]

    events = asyncio.run(run())

    assert events == [
        JsonRpcConnectionEvent.message_event(JSONRPCMessage(JSONRPCRequest(id=1, method="test"))),
        JsonRpcConnectionEvent.disconnected(None),
    ]


def test_run_multiplexed_environment_drops_malformed_non_data_and_nonbinary_frames() -> None:
    # Rust source contract:
    # codex-exec-server/src/relay.rs::run_multiplexed_environment frame
    # filtering before stream creation.
    async def run() -> int:
        websocket = ControlledRelayWebSocket()
        processor = RecordingRelayProcessor()
        task = asyncio.create_task(run_multiplexed_environment(websocket, processor))
        await websocket.incoming.put(JsonRpcWebSocketMessage.text("nope"))
        await websocket.incoming.put(JsonRpcWebSocketMessage.binary(b"\x80"))
        await websocket.incoming.put(
            JsonRpcWebSocketMessage.binary(encode_relay_message_frame(RelayMessageFrame.resume("stream-ignored")))
        )
        await asyncio.sleep(0)
        await websocket.incoming.put(JsonRpcWebSocketMessage.close())
        await asyncio.wait_for(task, 1)
        return processor.connections

    assert asyncio.run(run()) == 0


class ControlledRelayWebSocket:
    def __init__(self) -> None:
        self.incoming: asyncio.Queue[JsonRpcWebSocketMessage | None] = asyncio.Queue()
        self.outgoing: asyncio.Queue[JsonRpcWebSocketMessage] = asyncio.Queue()
        self._write_ready = asyncio.Event()
        self._write_ready.set()
        self._blocked = asyncio.Event()

    async def recv(self) -> JsonRpcWebSocketMessage | None:
        return await self.incoming.get()

    async def send(self, message: JsonRpcWebSocketMessage) -> None:
        if not self._write_ready.is_set():
            self._blocked.set()
        await self._write_ready.wait()
        await self.outgoing.put(message)

    def block_writes(self) -> None:
        self._write_ready.clear()
        self._blocked.clear()

    def release_write(self) -> None:
        self._write_ready.set()

    async def wait_for_blocked_write(self) -> None:
        await asyncio.wait_for(self._blocked.wait(), 1)


class RecordingRelayProcessor:
    def __init__(
        self,
        *,
        response: JSONRPCMessage | None = None,
        stop_after_response: bool = False,
    ) -> None:
        self.response = response
        self.stop_after_response = stop_after_response
        self.events: asyncio.Queue[JsonRpcConnectionEvent] = asyncio.Queue()
        self.connections = 0

    async def run_connection(self, connection: object) -> None:
        self.connections += 1
        assert hasattr(connection, "incoming_rx")
        assert hasattr(connection, "outgoing_tx")
        while True:
            event = await connection.incoming_rx.get()
            await self.events.put(event)
            if event.kind == "disconnected":
                return
            if self.response is not None:
                await connection.outgoing_tx.put(self.response)
                if self.stop_after_response:
                    return
