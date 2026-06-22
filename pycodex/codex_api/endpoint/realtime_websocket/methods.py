"""Runtime helpers from Rust ``realtime_websocket/methods.rs``."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from typing import Any
from typing import Callable
from typing import Iterable
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from pycodex.codex_client.retry import backoff
from pycodex.protocol import RealtimeAudioFrame
from pycodex.protocol import RealtimeOutputModality
from pycodex.protocol import RealtimeVoice

from ...error import ApiError
from ...provider import Provider
from ..responses_websocket import ResponsesWebsocketBinaryMessage
from ..responses_websocket import ResponsesWebsocketCloseMessage
from ..responses_websocket import ResponsesWebsocketFrameMessage
from ..responses_websocket import ResponsesWebsocketTextMessage
from ..responses_websocket import connect_websocket
from .methods_common import conversation_function_call_output_message
from .methods_common import conversation_item_create_message
from .methods_common import session_update_session
from .methods_common import websocket_intent
from .protocol import RealtimeEventParser
from .protocol import RealtimeEvent
from .protocol import RealtimeHandoffRequested
from .protocol import RealtimeSessionConfig
from .protocol import RealtimeSessionMode
from .protocol import RealtimeTranscriptDelta
from .protocol import RealtimeTranscriptDone
from .protocol import RealtimeTranscriptEntry
from .protocol import parse_realtime_event


@dataclass(frozen=True)
class RealtimeTextMessage:
    text: str


@dataclass(frozen=True)
class RealtimeBinaryMessage:
    data: bytes


@dataclass(frozen=True)
class RealtimeCloseMessage:
    code: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class RealtimePingMessage:
    data: bytes = b""


@dataclass(frozen=True)
class RealtimePongMessage:
    data: bytes = b""


@dataclass(frozen=True)
class RealtimeFrameMessage:
    data: Any = None


class RealtimeWebsocketConnectionClosed(Exception):
    pass


class RealtimeWebsocketAlreadyClosed(Exception):
    pass


class RealtimeWebsocketMemoryStream:
    """Small injectable stream used to test Rust writer semantics without a websocket dependency."""

    def __init__(self) -> None:
        self.sent_payloads: list[str] = []
        self.closed = False
        self.send_error: Exception | None = None
        self.close_error: Exception | None = None

    def send(self, payload: str) -> None:
        if self.send_error is not None:
            raise self.send_error
        if self.closed:
            raise RealtimeWebsocketAlreadyClosed("already closed")
        self.sent_payloads.append(payload)

    def next(self) -> Any:
        raise RealtimeWebsocketConnectionClosed("connection closed")

    def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class RealtimeWebsocketClient:
    def __init__(
        self,
        provider: Provider,
        connector: Callable[[str, Mapping[str, str]], Any] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.provider = provider
        self._connector = connector or connect_realtime_websocket_url
        self._sleep = sleeper or time.sleep

    @classmethod
    def new(
        cls,
        provider: Provider,
        connector: Callable[[str, Mapping[str, str]], Any] | None = None,
    ) -> "RealtimeWebsocketClient":
        return cls(provider, connector)

    def connect(
        self,
        config: RealtimeSessionConfig,
        extra_headers: Mapping[str, str] | None = None,
        default_headers: Mapping[str, str] | None = None,
    ) -> "RealtimeWebsocketConnection":
        ws_url = websocket_url_from_api_url(
            self.provider.base_url,
            self.provider.query_params,
            config.model,
            config.event_parser,
            config.session_mode,
        )
        return self._connect_realtime_websocket_url(
            ws_url,
            config,
            extra_headers or {},
            default_headers or {},
        )

    def connect_webrtc_sideband(
        self,
        config: RealtimeSessionConfig,
        call_id: str,
        extra_headers: Mapping[str, str] | None = None,
        default_headers: Mapping[str, str] | None = None,
    ) -> "RealtimeWebsocketConnection":
        last_error: ApiError | None = None
        for attempt in range(self.provider.retry.max_attempts + 1):
            try:
                return self._connect_webrtc_sideband_once(
                    config,
                    call_id,
                    extra_headers or {},
                    default_headers or {},
                )
            except ApiError as err:
                last_error = err
                if attempt >= self.provider.retry.max_attempts:
                    break
                self._sleep(backoff(self.provider.retry.base_delay, attempt + 1))
        if last_error is not None:
            raise last_error
        raise ApiError.stream("realtime sideband websocket retry loop exhausted")

    def _connect_webrtc_sideband_once(
        self,
        config: RealtimeSessionConfig,
        call_id: str,
        extra_headers: Mapping[str, str],
        default_headers: Mapping[str, str],
    ) -> "RealtimeWebsocketConnection":
        ws_url = websocket_url_from_api_url_for_call(
            self.provider.base_url,
            self.provider.query_params,
            config.event_parser,
            config.session_mode,
            call_id,
        )
        return self._connect_realtime_websocket_url(ws_url, config, extra_headers, default_headers)

    def _connect_realtime_websocket_url(
        self,
        ws_url: str,
        config: RealtimeSessionConfig,
        extra_headers: Mapping[str, str],
        default_headers: Mapping[str, str],
    ) -> "RealtimeWebsocketConnection":
        headers = merge_request_headers(
            self.provider.headers,
            with_session_id_header(extra_headers, config.session_id),
            default_headers,
        )
        try:
            connected = self._connector(ws_url, headers)
        except ApiError:
            raise
        except Exception as err:
            raise ApiError.stream(f"failed to connect realtime websocket: {err}") from err

        stream = connected[0] if isinstance(connected, tuple) else connected
        connection = RealtimeWebsocketConnection.new(
            stream,
            _RealtimeWebsocketMessageIterator(stream),
            config.event_parser,
        )
        connection.writer().send_session_update(
            config.instructions,
            config.session_mode,
            config.output_modality,
            config.voice,
        )
        return connection


def connect_realtime_websocket_url(
    ws_url: str,
    headers: Mapping[str, str],
) -> Any:
    try:
        return connect_websocket(ws_url, dict(headers), None)[0]
    except ApiError:
        raise
    except Exception as err:
        raise ApiError.stream(f"failed to connect realtime websocket: {err}") from err


def merge_request_headers(
    provider_headers: Mapping[str, str] | None,
    extra_headers: Mapping[str, str] | None,
    default_headers: Mapping[str, str] | None,
) -> dict[str, str]:
    headers = dict(provider_headers or {})
    _extend_case_insensitive(headers, extra_headers or {}, overwrite=True)
    for name, value in (default_headers or {}).items():
        if not _contains_header(headers, name):
            headers[name] = value
    return headers


def _contains_header(headers: Mapping[str, str], name: str) -> bool:
    wanted = name.lower()
    return any(key.lower() == wanted for key in headers)


def with_session_id_header(
    headers: Mapping[str, str] | None,
    session_id: str | None,
) -> dict[str, str]:
    merged = dict(headers or {})
    if session_id is None:
        return merged
    if not _valid_header_value(session_id):
        raise ApiError.stream("invalid realtime session id header: invalid header value")
    _set_case_insensitive(merged, "x-session-id", session_id)
    return merged


def _extend_case_insensitive(
    target: dict[str, str],
    source: Mapping[str, str],
    *,
    overwrite: bool,
) -> None:
    for name, value in source.items():
        existing = _find_header_key(target, name)
        if existing is not None:
            if overwrite:
                del target[existing]
                target[name] = value
            continue
        target[name] = value


def _set_case_insensitive(target: dict[str, str], name: str, value: str) -> None:
    existing = _find_header_key(target, name)
    if existing is not None:
        del target[existing]
    target[name] = value


def _find_header_key(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key in headers:
        if key.lower() == wanted:
            return key
    return None


def _valid_header_value(value: str) -> bool:
    return all(ch == "\t" or " " <= ch <= "~" for ch in value)


class _RealtimeWebsocketMessageIterator:
    def __init__(self, stream: Any) -> None:
        self.stream = stream

    def __iter__(self) -> "_RealtimeWebsocketMessageIterator":
        return self

    def __next__(self) -> Any:
        next_message = getattr(self.stream, "next", None)
        if next_message is None:
            raise StopIteration
        try:
            message = next_message()
        except (RealtimeWebsocketConnectionClosed, RealtimeWebsocketAlreadyClosed):
            raise StopIteration from None
        if isinstance(message, ResponsesWebsocketTextMessage):
            return RealtimeTextMessage(message.text)
        if isinstance(message, ResponsesWebsocketBinaryMessage):
            return RealtimeBinaryMessage(message.data)
        if isinstance(message, ResponsesWebsocketCloseMessage):
            return RealtimeCloseMessage(message.code, message.reason)
        if isinstance(message, ResponsesWebsocketFrameMessage):
            return RealtimeFrameMessage(message.data)
        return message


class RealtimeWebsocketWriter:
    def __init__(
        self,
        stream: Any,
        event_parser: RealtimeEventParser = RealtimeEventParser.REALTIME_V2,
        closed_state: dict[str, bool] | None = None,
    ) -> None:
        self.stream = stream
        self.event_parser = event_parser
        self._closed_state = closed_state if closed_state is not None else {"closed": False}

    def send_audio_frame(self, frame: RealtimeAudioFrame) -> None:
        self._send_json({"type": "input_audio_buffer.append", "audio": frame.data})

    def send_conversation_item_create(self, text: str) -> None:
        self._send_json(conversation_item_create_message(self.event_parser, text))

    def send_conversation_function_call_output(self, call_id: str, output_text: str) -> None:
        self._send_json(
            conversation_function_call_output_message(self.event_parser, call_id, output_text)
        )

    def send_response_create(self) -> None:
        self._send_json({"type": "response.create"})

    def send_session_update(
        self,
        instructions: str,
        session_mode: RealtimeSessionMode,
        output_modality: RealtimeOutputModality,
        voice: RealtimeVoice,
    ) -> None:
        session = session_update_session(
            self.event_parser,
            instructions,
            session_mode,
            output_modality,
            voice,
        )
        self._send_json({"type": "session.update", "session": session})

    def close(self) -> None:
        if self._closed_state["closed"]:
            return
        self._closed_state["closed"] = True
        close = getattr(self.stream, "close", None)
        if close is None:
            return
        try:
            close()
        except (RealtimeWebsocketAlreadyClosed, RealtimeWebsocketConnectionClosed):
            return
        except Exception as err:
            raise ApiError.stream(f"failed to close websocket: {err}") from err

    def send_payload(self, payload: str) -> None:
        if self._closed_state["closed"]:
            raise ApiError.stream("realtime websocket connection is closed")
        try:
            sender = getattr(self.stream, "send_text", None) or getattr(self.stream, "send")
            sender(payload)
        except Exception as err:
            raise ApiError.stream(f"failed to send realtime request: {err}") from err

    def _send_json(self, message: Mapping[str, Any]) -> None:
        try:
            payload = json.dumps(message, separators=(",", ":"))
        except Exception as err:
            raise ApiError.stream(f"failed to encode realtime request: {err}") from err
        self.send_payload(payload)


class RealtimeWebsocketEvents:
    def __init__(
        self,
        messages: Iterable[Any],
        event_parser: RealtimeEventParser = RealtimeEventParser.REALTIME_V2,
        closed_state: dict[str, bool] | None = None,
        active_transcript: RealtimeActiveTranscript | None = None,
    ) -> None:
        self._messages = iter(messages)
        self.event_parser = event_parser
        self._closed_state = closed_state if closed_state is not None else {"closed": False}
        self.active_transcript = (
            active_transcript if active_transcript is not None else RealtimeActiveTranscript.new()
        )

    def next_event(self) -> RealtimeEvent | None:
        if self._closed_state["closed"]:
            return None

        while True:
            try:
                message = next(self._messages)
            except StopIteration:
                self._closed_state["closed"] = True
                return None

            if isinstance(message, Exception):
                self._closed_state["closed"] = True
                raise ApiError.stream(f"failed to read websocket message: {message}") from message

            if isinstance(message, str):
                message = RealtimeTextMessage(message)
            elif isinstance(message, bytes):
                message = RealtimeBinaryMessage(message)

            if isinstance(message, RealtimeTextMessage):
                event = parse_realtime_event(message.text, self.event_parser)
                if event is None:
                    continue
                return self.active_transcript.update_active_transcript(event)

            if isinstance(message, RealtimeCloseMessage):
                self._closed_state["closed"] = True
                return None

            if isinstance(message, RealtimeBinaryMessage):
                return RealtimeEvent.error("unexpected binary realtime websocket event")

            if isinstance(message, (RealtimeFrameMessage, RealtimePingMessage, RealtimePongMessage)):
                continue
            continue


class RealtimeWebsocketConnection:
    def __init__(
        self,
        stream: Any,
        messages: Iterable[Any],
        event_parser: RealtimeEventParser = RealtimeEventParser.REALTIME_V2,
    ) -> None:
        closed_state = {"closed": False}
        self._writer = RealtimeWebsocketWriter(stream, event_parser, closed_state)
        self._events = RealtimeWebsocketEvents(messages, event_parser, closed_state)

    @classmethod
    def new(
        cls,
        stream: Any,
        messages: Iterable[Any],
        event_parser: RealtimeEventParser = RealtimeEventParser.REALTIME_V2,
    ) -> "RealtimeWebsocketConnection":
        return cls(stream, messages, event_parser)

    def send_audio_frame(self, frame: RealtimeAudioFrame) -> None:
        self._writer.send_audio_frame(frame)

    def send_conversation_item_create(self, text: str) -> None:
        self._writer.send_conversation_item_create(text)

    def send_conversation_function_call_output(self, call_id: str, output_text: str) -> None:
        self._writer.send_conversation_function_call_output(call_id, output_text)

    def close(self) -> None:
        self._writer.close()

    def next_event(self) -> RealtimeEvent | None:
        return self._events.next_event()

    def writer(self) -> RealtimeWebsocketWriter:
        return self._writer

    def events(self) -> RealtimeWebsocketEvents:
        return self._events


@dataclass
class RealtimeActiveTranscript:
    entries: list[RealtimeTranscriptEntry]
    last_handoff_entry_count: int = 0
    new_input_entry: bool = False
    new_output_entry: bool = False

    @classmethod
    def new(cls) -> "RealtimeActiveTranscript":
        return cls([])

    def update_active_transcript(self, event: RealtimeEvent) -> RealtimeEvent:
        if event.kind == "InputAudioSpeechStarted":
            self.new_input_entry = True
            return event
        if event.kind == "InputTranscriptDelta" and isinstance(
            event.payload,
            RealtimeTranscriptDelta,
        ):
            force_new = self.new_input_entry
            append_transcript_delta(self.entries, "user", event.payload.delta, force_new)
            self.new_input_entry = False
            return event
        if event.kind == "OutputTranscriptDelta" and isinstance(
            event.payload,
            RealtimeTranscriptDelta,
        ):
            force_new = self.new_output_entry
            append_transcript_delta(self.entries, "assistant", event.payload.delta, force_new)
            self.new_output_entry = False
            return event
        if event.kind == "InputTranscriptDone" and isinstance(event.payload, RealtimeTranscriptDone):
            force_new = self.new_input_entry
            apply_transcript_done(self.entries, "user", event.payload.text, force_new)
            self.new_input_entry = False
            return event
        if event.kind == "OutputTranscriptDone" and isinstance(
            event.payload,
            RealtimeTranscriptDone,
        ):
            force_new = self.new_output_entry
            apply_transcript_done(self.entries, "assistant", event.payload.text, force_new)
            self.new_output_entry = False
            return event
        if event.kind == "HandoffRequested" and isinstance(
            event.payload,
            RealtimeHandoffRequested,
        ):
            append_handoff_input(self.entries, event.payload.input_transcript)
            handoff = replace(
                event.payload,
                active_transcript=tuple(self.entries[self.last_handoff_entry_count :]),
            )
            self.last_handoff_entry_count = len(self.entries)
            self.new_input_entry = True
            self.new_output_entry = True
            return RealtimeEvent.handoff_requested(handoff)
        if event.kind == "ResponseCreated":
            self.new_output_entry = True
        return event


def append_transcript_delta(
    entries: list[RealtimeTranscriptEntry],
    role: str,
    delta: str,
    force_new: bool,
) -> None:
    if not delta:
        return
    if not force_new and entries and entries[-1].role == role:
        entries[-1] = replace(entries[-1], text=f"{entries[-1].text}{delta}")
        return
    entries.append(RealtimeTranscriptEntry(role, delta))


def apply_transcript_done(
    entries: list[RealtimeTranscriptEntry],
    role: str,
    text: str,
    force_new: bool,
) -> None:
    if not text:
        return
    if not force_new and entries and entries[-1].role == role:
        entries[-1] = replace(entries[-1], text=text)
        return
    entries.append(RealtimeTranscriptEntry(role, text))


def append_handoff_input(entries: list[RealtimeTranscriptEntry], input_text: str) -> None:
    text = input_text.strip()
    if not text or contains_transcript_entry(entries, "user", text):
        return
    entries.append(RealtimeTranscriptEntry("user", text))


def contains_transcript_entry(
    entries: list[RealtimeTranscriptEntry],
    role: str,
    text: str,
) -> bool:
    trimmed = text.strip()
    return any(entry.role == role and entry.text.strip() == trimmed for entry in entries)


def websocket_config() -> dict[str, Any]:
    return {}


def websocket_url_from_api_url(
    api_url: str,
    query_params: Mapping[str, str] | None,
    model: str | None,
    event_parser: RealtimeEventParser,
    session_mode: RealtimeSessionMode,
) -> str:
    del session_mode
    parsed = urlsplit(api_url)
    if not parsed.scheme or not parsed.netloc:
        raise ApiError.stream("failed to parse realtime api_url: relative URL without a base")

    path = _normalize_realtime_path(parsed.path)
    if parsed.scheme in ("ws", "wss"):
        scheme = parsed.scheme
    elif parsed.scheme in ("http", "https"):
        scheme = "ws" if parsed.scheme == "http" else "wss"
    else:
        raise ApiError.stream(f"unsupported realtime api_url scheme: {parsed.scheme}")

    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    intent = websocket_intent(event_parser)
    has_extra_query_params = any(
        key != "intent" and not (key == "model" and model is not None)
        for key in (query_params or {})
    )
    if intent is not None or model is not None or has_extra_query_params:
        if intent is not None:
            pairs.append(("intent", intent))
        if model is not None:
            pairs.append(("model", model))
        if query_params is not None:
            for key, value in query_params.items():
                if key == "intent" or (key == "model" and model is not None):
                    continue
                pairs.append((key, value))

    query = urlencode(pairs)
    return urlunsplit((scheme, parsed.netloc, path, query, parsed.fragment))


def websocket_url_from_api_url_for_call(
    api_url: str,
    query_params: Mapping[str, str] | None,
    event_parser: RealtimeEventParser,
    session_mode: RealtimeSessionMode,
    call_id: str,
) -> str:
    url = websocket_url_from_api_url(
        api_url,
        query_params,
        None,
        event_parser,
        session_mode,
    )
    parsed = urlsplit(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    pairs.append(("call_id", call_id))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), parsed.fragment))


def _normalize_realtime_path(path: str) -> str:
    if path == "" or path == "/":
        return "/v1/realtime"
    if path.endswith("/realtime"):
        return path
    if path.endswith("/realtime/"):
        return path.rstrip("/")
    if path.endswith("/v1"):
        return f"{path}/realtime"
    if path.endswith("/v1/"):
        return f"{path}realtime"
    return path
