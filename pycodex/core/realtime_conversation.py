"""Pure helpers from Codex realtime conversation handling.

Ported from the standalone formatting/header helpers in
``codex/codex-rs/core/src/realtime_conversation.rs``. Realtime websocket,
audio, model-client, and session orchestration remain outside this stdlib-only
slice.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


REALTIME_USER_TEXT_PREFIX = "[USER] "
REALTIME_BACKEND_TEXT_PREFIX = "[BACKEND] "
REALTIME_STARTUP_CONTEXT_TOKEN_BUDGET = 5_300
DEFAULT_REALTIME_MODEL = "gpt-realtime-1.5"
REALTIME_V2_HANDOFF_COMPLETE_ACKNOWLEDGEMENT = (
    "Background agent finished. Use the preceding [BACKEND] messages as the result."
)
REALTIME_V2_STEER_ACKNOWLEDGEMENT = "This was sent to steer the previous background agent task."
AUDIO_IN_QUEUE_CAPACITY = 256
USER_TEXT_IN_QUEUE_CAPACITY = 64
HANDOFF_OUT_QUEUE_CAPACITY = 64
OUTPUT_EVENTS_QUEUE_CAPACITY = 256


class RealtimeWsVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"


class RealtimeSessionKind(str, Enum):
    V1 = "v1"
    V2 = "v2"


class RealtimeConversationEnd(str, Enum):
    REQUESTED = "requested"
    TRANSPORT_CLOSED = "transport_closed"
    ERROR = "error"


@dataclass(frozen=True)
class HandoffOutput:
    handoff_id: str
    output_text: str
    final: bool = False


@dataclass
class RealtimeHandoffState:
    output_tx: asyncio.Queue[HandoffOutput]
    session_kind: RealtimeSessionKind = RealtimeSessionKind.V1
    active_handoff: str | None = None
    last_output_text: str | None = None

    @classmethod
    def new(
        cls,
        output_tx: asyncio.Queue[HandoffOutput] | None = None,
        session_kind: RealtimeSessionKind | str = RealtimeSessionKind.V1,
    ) -> "RealtimeHandoffState":
        return cls(
            output_tx=output_tx if output_tx is not None else asyncio.Queue(maxsize=HANDOFF_OUT_QUEUE_CAPACITY),
            session_kind=RealtimeSessionKind(session_kind),
        )


@dataclass
class ConversationState:
    audio_tx: asyncio.Queue[Any]
    user_text_tx: asyncio.Queue[str]
    handoff: RealtimeHandoffState
    output_events: asyncio.Queue[Any]
    session_kind: RealtimeSessionKind = RealtimeSessionKind.V1
    realtime_active: bool = True
    runtime: Any = None
    fanout_task: Any = None


@dataclass(frozen=True)
class RealtimeStart:
    api_provider: Any = None
    extra_headers: Mapping[str, str] | None = None
    session_config: Any = None
    model_client: Any = None
    sdp: str | None = None
    runtime: Any = None
    session_kind: RealtimeSessionKind | str = RealtimeSessionKind.V1


@dataclass(frozen=True)
class RealtimeStartOutput:
    realtime_active: bool
    events_rx: asyncio.Queue[Any]
    sdp: str | None = None


class RealtimeConversationManager:
    """Stdlib runtime boundary for Codex realtime conversation state.

    Rust source: ``codex-rs/core/src/realtime_conversation.rs``. Concrete
    websocket/WebRTC IO stays behind an optional runtime provider, but the
    manager-owned state, input queues, handoff semantics, and shutdown behavior
    mirror the Rust module.
    """

    def __init__(self) -> None:
        self._state: ConversationState | None = None
        self._lock = asyncio.Lock()

    async def running_state(self) -> object | None:
        async with self._lock:
            return object() if self._state is not None and self._state.realtime_active else None

    async def is_running_v2(self) -> bool:
        async with self._lock:
            return bool(
                self._state is not None
                and self._state.realtime_active
                and self._state.session_kind is RealtimeSessionKind.V2
            )

    async def start(self, start: RealtimeStart) -> RealtimeStartOutput:
        previous_state: ConversationState | None
        async with self._lock:
            previous_state = self._state
            self._state = None
        if previous_state is not None:
            await stop_conversation_state(previous_state, abort_fanout=True)
        return await self._start_inner(start)

    async def _start_inner(self, start: RealtimeStart) -> RealtimeStartOutput:
        runtime = start.runtime
        if runtime is None:
            runtime = start.model_client
        if runtime is not None:
            starter = getattr(runtime, "start_realtime_conversation", None)
            if callable(starter):
                started = await _maybe_await(starter(start))
                if isinstance(started, RealtimeStartOutput):
                    output = started
                else:
                    output = RealtimeStartOutput(
                        realtime_active=True,
                        events_rx=getattr(started, "events_rx", asyncio.Queue(maxsize=OUTPUT_EVENTS_QUEUE_CAPACITY)),
                        sdp=getattr(started, "sdp", start.sdp),
                    )
                state = ConversationState(
                    audio_tx=asyncio.Queue(maxsize=AUDIO_IN_QUEUE_CAPACITY),
                    user_text_tx=asyncio.Queue(maxsize=USER_TEXT_IN_QUEUE_CAPACITY),
                    handoff=RealtimeHandoffState.new(session_kind=start.session_kind),
                    output_events=output.events_rx,
                    session_kind=RealtimeSessionKind(start.session_kind),
                    runtime=runtime,
                )
                async with self._lock:
                    self._state = state
                return output

        state = ConversationState(
            audio_tx=asyncio.Queue(maxsize=AUDIO_IN_QUEUE_CAPACITY),
            user_text_tx=asyncio.Queue(maxsize=USER_TEXT_IN_QUEUE_CAPACITY),
            handoff=RealtimeHandoffState.new(session_kind=start.session_kind),
            output_events=asyncio.Queue(maxsize=OUTPUT_EVENTS_QUEUE_CAPACITY),
            session_kind=RealtimeSessionKind(start.session_kind),
            runtime=runtime,
        )
        async with self._lock:
            self._state = state
        return RealtimeStartOutput(realtime_active=True, events_rx=state.output_events, sdp=start.sdp)

    async def register_fanout_task(self, realtime_active: object, fanout_task: Any) -> None:
        async with self._lock:
            if self._state is not None and self._state.realtime_active:
                self._state.fanout_task = fanout_task
                return
        abort = getattr(fanout_task, "cancel", None) or getattr(fanout_task, "abort", None)
        if callable(abort):
            abort()

    async def finish_if_active(self, realtime_active: object) -> None:
        async with self._lock:
            state = self._state
            self._state = None
        if state is not None:
            await stop_conversation_state(state, abort_fanout=False)

    async def audio_in(self, frame: Any) -> None:
        state = await self._require_state()
        try:
            state.audio_tx.put_nowait(frame)
        except asyncio.QueueFull:
            return

    async def text_in(self, text: str) -> None:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        state = await self._require_state()
        await state.user_text_tx.put(prefix_realtime_text(text, REALTIME_USER_TEXT_PREFIX, state.session_kind))

    async def handoff_out(self, output_text: str) -> None:
        if not isinstance(output_text, str):
            raise TypeError("output_text must be a string")
        state = await self._require_state()
        handoff_id = state.handoff.active_handoff
        if handoff_id is None:
            return
        output_text = prefix_realtime_text(output_text, REALTIME_BACKEND_TEXT_PREFIX, state.session_kind)
        state.handoff.last_output_text = output_text
        await state.handoff.output_tx.put(HandoffOutput(handoff_id, output_text, final=False))

    async def handoff_complete(self) -> None:
        async with self._lock:
            state = self._state
        if state is None or state.session_kind is RealtimeSessionKind.V1:
            return
        handoff_id = state.handoff.active_handoff
        output_text = state.handoff.last_output_text
        if handoff_id is None or output_text is None:
            return
        await state.handoff.output_tx.put(HandoffOutput(handoff_id, output_text, final=True))

    async def active_handoff_id(self) -> str | None:
        async with self._lock:
            return self._state.handoff.active_handoff if self._state is not None else None

    async def clear_active_handoff(self) -> None:
        async with self._lock:
            if self._state is not None:
                self._state.handoff.active_handoff = None
                self._state.handoff.last_output_text = None

    async def shutdown(self) -> None:
        async with self._lock:
            state = self._state
            self._state = None
        if state is not None:
            await stop_conversation_state(state, abort_fanout=True)

    async def _require_state(self) -> ConversationState:
        async with self._lock:
            state = self._state
        if state is None or not state.realtime_active:
            raise RuntimeError("conversation is not running")
        return state


@dataclass(frozen=True)
class RealtimeTranscriptEntry:
    role: str
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, str):
            raise TypeError("role must be a string")
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

    @classmethod
    def from_value(cls, value: "RealtimeTranscriptEntry | Mapping[str, object]") -> "RealtimeTranscriptEntry":
        if isinstance(value, RealtimeTranscriptEntry):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("transcript entries must be RealtimeTranscriptEntry or mapping values")
        role = value.get("role")
        text = value.get("text")
        if not isinstance(role, str):
            raise TypeError("transcript entry role must be a string")
        if not isinstance(text, str):
            raise TypeError("transcript entry text must be a string")
        return cls(role=role, text=text)


@dataclass(frozen=True)
class RealtimeHandoffRequested:
    handoff_id: str
    item_id: str
    input_transcript: str
    active_transcript: tuple[RealtimeTranscriptEntry, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.handoff_id, str):
            raise TypeError("handoff_id must be a string")
        if not isinstance(self.item_id, str):
            raise TypeError("item_id must be a string")
        if not isinstance(self.input_transcript, str):
            raise TypeError("input_transcript must be a string")
        if isinstance(self.active_transcript, (str, bytes)) or not isinstance(self.active_transcript, Sequence):
            raise TypeError("active_transcript must be a sequence")
        object.__setattr__(
            self,
            "active_transcript",
            tuple(RealtimeTranscriptEntry.from_value(entry) for entry in self.active_transcript),
        )


def realtime_transcript_delta_from_handoff(handoff: RealtimeHandoffRequested) -> str | None:
    handoff = _handoff(handoff)
    active_transcript = "\n".join(f"{entry.role}: {entry.text}" for entry in handoff.active_transcript)
    return active_transcript or None


def realtime_text_from_handoff_request(handoff: RealtimeHandoffRequested) -> str | None:
    handoff = _handoff(handoff)
    if handoff.input_transcript:
        return handoff.input_transcript
    return realtime_transcript_delta_from_handoff(handoff)


def realtime_delegation_from_handoff(handoff: RealtimeHandoffRequested) -> str | None:
    handoff = _handoff(handoff)
    input_text = realtime_text_from_handoff_request(handoff)
    if input_text is None:
        return None
    return wrap_realtime_delegation_input(
        input_text,
        realtime_transcript_delta_from_handoff(handoff),
    )


def wrap_realtime_delegation_input(input: str, transcript_delta: str | None = None) -> str:
    if not isinstance(input, str):
        raise TypeError("input must be a string")
    if transcript_delta is not None and not isinstance(transcript_delta, str):
        raise TypeError("transcript_delta must be a string or None")
    escaped_input = escape_xml_text(input)
    if transcript_delta:
        escaped_delta = escape_xml_text(transcript_delta)
        return (
            "<realtime_delegation>\n"
            f"  <input>{escaped_input}</input>\n"
            f"  <transcript_delta>{escaped_delta}</transcript_delta>\n"
            "</realtime_delegation>"
        )
    return f"<realtime_delegation>\n  <input>{escaped_input}</input>\n</realtime_delegation>"


def escape_xml_text(input: str) -> str:
    if not isinstance(input, str):
        raise TypeError("input must be a string")
    return input.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def realtime_request_headers(
    realtime_session_id: str | None,
    api_key: str | None,
    version: RealtimeWsVersion | str,
) -> dict[str, str]:
    ws_version = RealtimeWsVersion(version)
    headers: dict[str, str] = {}
    if ws_version is RealtimeWsVersion.V1:
        headers["openai-alpha"] = "quicksilver=v1"
    if realtime_session_id is not None:
        if not isinstance(realtime_session_id, str):
            raise TypeError("realtime_session_id must be a string or None")
        if _valid_header_value(realtime_session_id):
            headers["x-session-id"] = realtime_session_id
    if api_key is not None:
        if not isinstance(api_key, str):
            raise TypeError("api_key must be a string or None")
        auth_value = f"Bearer {api_key}"
        if not _valid_header_value(auth_value):
            raise ValueError("invalid realtime api key header")
        headers["authorization"] = auth_value
    return headers


def prefix_realtime_text(text: str, prefix: str, session_kind: RealtimeSessionKind | str) -> str:
    session_kind = RealtimeSessionKind(session_kind)
    if session_kind is RealtimeSessionKind.V2 and not text.startswith(prefix):
        return f"{prefix}{text}"
    return text


async def stop_conversation_state(state: ConversationState, abort_fanout: bool) -> None:
    state.realtime_active = False
    runtime = state.runtime
    shutdown = getattr(runtime, "shutdown_realtime_conversation", None) if runtime is not None else None
    if callable(shutdown):
        await _maybe_await(shutdown(state))
    fanout_task = state.fanout_task
    if abort_fanout and fanout_task is not None:
        abort = getattr(fanout_task, "cancel", None) or getattr(fanout_task, "abort", None)
        if callable(abort):
            abort()


async def end_realtime_conversation(
    sess: object,
    sub_id: str,
    end: RealtimeConversationEnd | str = RealtimeConversationEnd.REQUESTED,
) -> None:
    conversation = getattr(sess, "conversation", None)
    shutdown = getattr(conversation, "shutdown", None)
    if callable(shutdown):
        await _maybe_await(shutdown())
    await send_realtime_conversation_closed(sess, sub_id, end)


async def send_realtime_conversation_closed(
    sess: object,
    sub_id: str,
    end: RealtimeConversationEnd | str,
) -> None:
    reason = RealtimeConversationEnd(end).value
    await _send_session_event(
        sess,
        {
            "id": sub_id,
            "msg": {
                "type": "realtime_conversation_closed",
                "reason": reason,
            },
        },
    )


async def handle_text(sess: object, sub_id: str, params: object) -> None:
    conversation = getattr(sess, "conversation", None)
    text_in = getattr(conversation, "text_in", None)
    if not callable(text_in):
        await send_conversation_error(sess, sub_id, "conversation is not running")
        return
    text = getattr(params, "text", None)
    if isinstance(params, Mapping):
        text = params.get("text")
    try:
        await _maybe_await(text_in(str(text)))
    except Exception as exc:
        await send_conversation_error(sess, sub_id, str(exc))


async def handle_close(sess: object, sub_id: str) -> None:
    await end_realtime_conversation(sess, sub_id, RealtimeConversationEnd.REQUESTED)


async def send_conversation_error(
    sess: object,
    sub_id: str,
    message: str,
    codex_error_info: str = "bad_request",
) -> None:
    await _send_session_event(
        sess,
        {
            "id": sub_id,
            "msg": {
                "type": "error",
                "message": message,
                "codex_error_info": codex_error_info,
            },
        },
    )


def realtime_conversation_list_voices() -> dict[str, list[str]]:
    return {"voices": ["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]}


async def _send_session_event(sess: object, event: Mapping[str, object]) -> None:
    send = getattr(sess, "send_event_raw", None) or getattr(sess, "send_event", None)
    if callable(send):
        await _maybe_await(send(event))


async def _maybe_await(value: object) -> object:
    if hasattr(value, "__await__"):
        return await value  # type: ignore[misc]
    return value


def _valid_header_value(value: str) -> bool:
    return all(ch == "\t" or (ord(ch) >= 32 and ch not in "\r\n") for ch in value)


def _handoff(value: RealtimeHandoffRequested) -> RealtimeHandoffRequested:
    if not isinstance(value, RealtimeHandoffRequested):
        raise TypeError("handoff must be RealtimeHandoffRequested")
    return value


__all__ = [
    "AUDIO_IN_QUEUE_CAPACITY",
    "ConversationState",
    "DEFAULT_REALTIME_MODEL",
    "HANDOFF_OUT_QUEUE_CAPACITY",
    "HandoffOutput",
    "OUTPUT_EVENTS_QUEUE_CAPACITY",
    "REALTIME_BACKEND_TEXT_PREFIX",
    "REALTIME_STARTUP_CONTEXT_TOKEN_BUDGET",
    "REALTIME_USER_TEXT_PREFIX",
    "REALTIME_V2_HANDOFF_COMPLETE_ACKNOWLEDGEMENT",
    "REALTIME_V2_STEER_ACKNOWLEDGEMENT",
    "RealtimeConversationEnd",
    "RealtimeConversationManager",
    "RealtimeHandoffRequested",
    "RealtimeHandoffState",
    "RealtimeSessionKind",
    "RealtimeStart",
    "RealtimeStartOutput",
    "RealtimeTranscriptEntry",
    "RealtimeWsVersion",
    "USER_TEXT_IN_QUEUE_CAPACITY",
    "end_realtime_conversation",
    "escape_xml_text",
    "handle_close",
    "handle_text",
    "prefix_realtime_text",
    "realtime_delegation_from_handoff",
    "realtime_conversation_list_voices",
    "realtime_request_headers",
    "realtime_text_from_handoff_request",
    "realtime_transcript_delta_from_handoff",
    "send_conversation_error",
    "send_realtime_conversation_closed",
    "stop_conversation_state",
    "wrap_realtime_delegation_input",
]
