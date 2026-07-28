from __future__ import annotations

import base64
import json

from pycodex.app_server_transport.outgoing_message import OutgoingMessage
from pycodex.app_server_transport.transport.remote_control.protocol import (
    ClientEnvelope,
    ClientEvent,
    ClientId,
    ServerEnvelope,
    ServerEvent,
    StreamId,
)
from pycodex.app_server_transport.transport.remote_control.segment import (
    ClientSegmentObservation,
    ClientSegmentReassembler,
    REMOTE_CONTROL_SEGMENT_MAX_BYTES,
    split_server_envelope_for_transport,
)


def _chunk(
    raw: bytes,
    *,
    seq_id: int,
    segment_id: int,
    segment_count: int,
    client_id: str = "client-1",
    stream_id: str = "stream-1",
) -> ClientEnvelope:
    split = len(raw) // segment_count
    start = split * segment_id
    end = len(raw) if segment_id + 1 == segment_count else start + split
    return ClientEnvelope(
        event=ClientEvent.client_message_chunk(
            segment_id=segment_id,
            segment_count=segment_count,
            message_size_bytes=len(raw),
            message_chunk_base64=base64.b64encode(raw[start:end]).decode("ascii"),
        ),
        client_id=ClientId(client_id),
        stream_id=StreamId(stream_id),
        seq_id=seq_id,
    )


def test_reassembles_client_message_chunks() -> None:
    message = {"method": "initialized", "params": None}
    raw = json.dumps(message, separators=(",", ":")).encode()
    reassembler = ClientSegmentReassembler()

    first = reassembler.observe(_chunk(raw, seq_id=7, segment_id=0, segment_count=2))
    assert first.kind is ClientSegmentObservation.Kind.PENDING

    second = reassembler.observe(_chunk(raw, seq_id=7, segment_id=1, segment_count=2))
    assert second.kind is ClientSegmentObservation.Kind.FORWARD
    assert second.envelope is not None
    assert second.envelope.event.message == message
    assert second.envelope.seq_id == 7


def test_stale_and_out_of_order_chunks_do_not_corrupt_newer_assembly() -> None:
    raw = json.dumps({"method": "initialized"}).encode()
    reassembler = ClientSegmentReassembler()

    assert (
        reassembler.observe(_chunk(raw, seq_id=8, segment_id=0, segment_count=2)).kind
        is ClientSegmentObservation.Kind.PENDING
    )
    assert (
        reassembler.observe(_chunk(raw, seq_id=7, segment_id=0, segment_count=2)).kind
        is ClientSegmentObservation.Kind.DROPPED
    )
    assert (
        reassembler.observe(_chunk(raw, seq_id=8, segment_id=1, segment_count=2)).kind
        is ClientSegmentObservation.Kind.FORWARD
    )


def test_invalidating_stream_drops_incomplete_assembly() -> None:
    raw = json.dumps({"method": "initialized"}).encode()
    client_id = ClientId("client-1")
    stream_id = StreamId("stream-1")
    reassembler = ClientSegmentReassembler()

    assert (
        reassembler.observe(_chunk(raw, seq_id=7, segment_id=0, segment_count=2)).kind
        is ClientSegmentObservation.Kind.PENDING
    )
    reassembler.invalidate_stream(client_id, stream_id)
    assert (
        reassembler.observe(_chunk(raw, seq_id=7, segment_id=1, segment_count=2)).kind
        is ClientSegmentObservation.Kind.DROPPED
    )


def test_splits_large_server_messages_into_bounded_wire_chunks() -> None:
    envelope = ServerEnvelope(
        event=ServerEvent.server_message(
            OutgoingMessage.app_server_notification(
                {"method": "configWarning", "params": {"summary": "x" * 180_000}}
            )
        ),
        client_id=ClientId("client-1"),
        stream_id=StreamId("stream-1"),
        seq_id=9,
    )

    chunks = split_server_envelope_for_transport(envelope)

    assert len(chunks) > 1
    assert all(chunk.event.kind is ServerEvent.Kind.SERVER_MESSAGE_CHUNK for chunk in chunks)
    assert all(chunk.seq_id == 9 for chunk in chunks)
    assert all(
        len(json.dumps(chunk.to_mapping(), separators=(",", ":")).encode())
        <= REMOTE_CONTROL_SEGMENT_MAX_BYTES
        for chunk in chunks
    )
