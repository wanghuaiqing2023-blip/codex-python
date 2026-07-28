from __future__ import annotations

import base64
import binascii
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .protocol import (
    ClientEnvelope,
    ClientEvent,
    ClientId,
    ServerEnvelope,
    ServerEvent,
    StreamId,
)

REMOTE_CONTROL_SEGMENT_TARGET_BYTES = 100 * 1024
REMOTE_CONTROL_SEGMENT_MAX_BYTES = 150 * 1024
REMOTE_CONTROL_REASSEMBLED_MAX_BYTES = 100 * 1024 * 1024
REMOTE_CONTROL_SEGMENT_COUNT_MAX = 1024
_REMOTE_CONTROL_SEGMENT_ASSEMBLY_MAX_COUNT = 128


@dataclass
class _ClientSegmentAssembly:
    stream_id: StreamId
    seq_id: int
    segment_count: int
    message_size_bytes: int
    raw: bytearray
    next_segment_id: int
    last_chunk_seen_at: float


@dataclass(frozen=True)
class ClientSegmentObservation:
    class Kind(Enum):
        FORWARD = "forward"
        PENDING = "pending"
        DROPPED = "dropped"

    kind: Kind
    envelope: ClientEnvelope | None = None

    @classmethod
    def forward(cls, envelope: ClientEnvelope) -> "ClientSegmentObservation":
        return cls(cls.Kind.FORWARD, envelope)

    @classmethod
    def pending(cls) -> "ClientSegmentObservation":
        return cls(cls.Kind.PENDING)

    @classmethod
    def dropped(cls) -> "ClientSegmentObservation":
        return cls(cls.Kind.DROPPED)


class ClientSegmentReassembler:
    def __init__(self) -> None:
        self._assemblies: dict[ClientId, _ClientSegmentAssembly] = {}

    def observe(self, envelope: ClientEnvelope) -> ClientSegmentObservation:
        event = envelope.event
        if event.kind is not ClientEvent.Kind.CLIENT_MESSAGE_CHUNK:
            return ClientSegmentObservation.forward(envelope)
        if envelope.seq_id is None or envelope.stream_id is None:
            return ClientSegmentObservation.dropped()

        segment_id = event.segment_id
        segment_count = event.segment_count
        message_size_bytes = event.message_size_bytes
        encoded = event.message_chunk_base64
        assert segment_id is not None
        assert segment_count is not None
        assert message_size_bytes is not None
        assert encoded is not None

        if self.should_ignore_chunk(
            envelope.client_id,
            envelope.stream_id,
            envelope.seq_id,
            segment_id,
        ):
            return ClientSegmentObservation.dropped()
        if (
            segment_count == 0
            or segment_count > REMOTE_CONTROL_SEGMENT_COUNT_MAX
            or segment_id >= segment_count
            or message_size_bytes == 0
            or message_size_bytes > REMOTE_CONTROL_REASSEMBLED_MAX_BYTES
            or not encoded
        ):
            self._remove_assembly(envelope.client_id, envelope.stream_id)
            return ClientSegmentObservation.dropped()

        now = time.monotonic()
        assembly = self._assemblies.get(envelope.client_id)
        if assembly is None or assembly.stream_id != envelope.stream_id:
            self._evict_assemblies_if_full()
            assembly = _ClientSegmentAssembly(
                stream_id=envelope.stream_id,
                seq_id=envelope.seq_id,
                segment_count=segment_count,
                message_size_bytes=message_size_bytes,
                raw=bytearray(),
                next_segment_id=0,
                last_chunk_seen_at=now,
            )
            self._assemblies[envelope.client_id] = assembly

        if envelope.seq_id < assembly.seq_id:
            return ClientSegmentObservation.dropped()
        metadata_matches = (
            envelope.seq_id == assembly.seq_id
            and segment_count == assembly.segment_count
            and message_size_bytes == assembly.message_size_bytes
        )
        if not metadata_matches:
            self._remove_assembly(envelope.client_id, envelope.stream_id)
            return ClientSegmentObservation.dropped()
        if segment_id < assembly.next_segment_id:
            return ClientSegmentObservation.pending()
        if segment_id != assembly.next_segment_id:
            self._remove_assembly(envelope.client_id, envelope.stream_id)
            return ClientSegmentObservation.dropped()

        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            self._remove_assembly(envelope.client_id, envelope.stream_id)
            return ClientSegmentObservation.dropped()
        if len(assembly.raw) + len(decoded) > message_size_bytes:
            self._remove_assembly(envelope.client_id, envelope.stream_id)
            return ClientSegmentObservation.dropped()

        assembly.raw.extend(decoded)
        assembly.next_segment_id += 1
        assembly.last_chunk_seen_at = now
        if assembly.next_segment_id < segment_count:
            return ClientSegmentObservation.pending()
        if len(assembly.raw) != message_size_bytes:
            self._remove_assembly(envelope.client_id, envelope.stream_id)
            return ClientSegmentObservation.dropped()

        try:
            message = json.loads(bytes(assembly.raw))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._remove_assembly(envelope.client_id, envelope.stream_id)
            return ClientSegmentObservation.dropped()
        self._remove_assembly(envelope.client_id, envelope.stream_id)
        return ClientSegmentObservation.forward(
            ClientEnvelope(
                event=ClientEvent.client_message(message),
                client_id=envelope.client_id,
                stream_id=envelope.stream_id,
                seq_id=envelope.seq_id,
                cursor=envelope.cursor,
            )
        )

    def invalidate_stream(self, client_id: ClientId, stream_id: StreamId) -> None:
        self._remove_assembly(client_id, stream_id)

    def invalidate_client(self, client_id: ClientId) -> None:
        self._assemblies.pop(client_id, None)

    def should_ignore_chunk(
        self,
        client_id: ClientId,
        stream_id: StreamId,
        seq_id: int,
        segment_id: int,
    ) -> bool:
        assembly = self._assemblies.get(client_id)
        return bool(
            assembly is not None
            and assembly.stream_id == stream_id
            and (
                seq_id < assembly.seq_id
                or (seq_id == assembly.seq_id and segment_id < assembly.next_segment_id)
            )
        )

    def _remove_assembly(self, client_id: ClientId, stream_id: StreamId) -> None:
        assembly = self._assemblies.get(client_id)
        if assembly is not None and assembly.stream_id == stream_id:
            self._assemblies.pop(client_id, None)

    def _evict_assemblies_if_full(self) -> None:
        while len(self._assemblies) >= _REMOTE_CONTROL_SEGMENT_ASSEMBLY_MAX_COUNT:
            oldest = min(
                self._assemblies,
                key=lambda client_id: self._assemblies[client_id].last_chunk_seen_at,
            )
            self._assemblies.pop(oldest, None)


def _compact_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def split_server_envelope_for_transport(
    envelope: ServerEnvelope,
) -> list[ServerEnvelope]:
    if envelope.event.kind is not ServerEvent.Kind.SERVER_MESSAGE:
        return [envelope]
    if len(_compact_json(envelope.to_mapping())) <= REMOTE_CONTROL_SEGMENT_MAX_BYTES:
        return [envelope]

    message = envelope.event.message
    if message is None:
        raise ValueError("server message is missing payload")
    raw = _compact_json(message.to_mapping())
    message_size_bytes = len(raw)
    if message_size_bytes > REMOTE_CONTROL_REASSEMBLED_MAX_BYTES:
        return []

    segment_count = max(
        2,
        (message_size_bytes + REMOTE_CONTROL_SEGMENT_TARGET_BYTES - 1)
        // REMOTE_CONTROL_SEGMENT_TARGET_BYTES,
    )
    while segment_count <= REMOTE_CONTROL_SEGMENT_COUNT_MAX:
        chunk_size = max(1, (message_size_bytes + segment_count - 1) // segment_count)
        chunks = [
            raw[offset : offset + chunk_size]
            for offset in range(0, message_size_bytes, chunk_size)
        ]
        actual_count = len(chunks)
        envelopes = [
            _build_chunk_envelope(
                envelope,
                segment_id=segment_id,
                segment_count=actual_count,
                message_size_bytes=message_size_bytes,
                chunk=chunk,
            )
            for segment_id, chunk in enumerate(chunks)
        ]
        if all(
            len(_compact_json(chunk_envelope.to_mapping()))
            <= REMOTE_CONTROL_SEGMENT_MAX_BYTES
            for chunk_envelope in envelopes
        ):
            return envelopes
        segment_count += 1
    return []


def _build_chunk_envelope(
    envelope: ServerEnvelope,
    *,
    segment_id: int,
    segment_count: int,
    message_size_bytes: int,
    chunk: bytes,
) -> ServerEnvelope:
    if segment_count > REMOTE_CONTROL_SEGMENT_COUNT_MAX:
        raise ValueError("remote-control segment count exceeds maximum")
    return ServerEnvelope(
        event=ServerEvent.server_message_chunk(
            segment_id=segment_id,
            segment_count=segment_count,
            message_size_bytes=message_size_bytes,
            message_chunk_base64=base64.b64encode(chunk).decode("ascii"),
        ),
        client_id=envelope.client_id,
        stream_id=envelope.stream_id,
        seq_id=envelope.seq_id,
    )


__all__ = [
    "ClientSegmentObservation",
    "ClientSegmentReassembler",
    "REMOTE_CONTROL_REASSEMBLED_MAX_BYTES",
    "REMOTE_CONTROL_SEGMENT_COUNT_MAX",
    "REMOTE_CONTROL_SEGMENT_MAX_BYTES",
    "REMOTE_CONTROL_SEGMENT_TARGET_BYTES",
    "split_server_envelope_for_transport",
]
