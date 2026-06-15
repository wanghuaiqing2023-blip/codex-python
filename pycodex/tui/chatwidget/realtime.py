"""Semantic Python port of Rust ``codex-tui::chatwidget::realtime``.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/realtime.rs``.

The Rust module owns the realtime voice conversation state machine and wires it
into ``ChatWidget`` side effects.  Python represents those side effects as
semantic records so phase transitions, footer hints, transport selection, and
notification handling remain testable without claiming real microphone,
playback, WebRTC, or ratatui behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, MutableSequence, Optional, Tuple, Union

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::realtime",
    source="codex/codex-rs/tui/src/chatwidget/realtime.rs",
    status="complete",
)

REALTIME_FOOTER_HINT_ITEMS: Tuple[Tuple[str, str], ...] = (("/realtime", "stop live voice"),)
SPEECH_STARTED_ITEM_TYPE = "input_audio_buffer.speech_started"
RESPONSE_CANCELLED_ITEM_TYPE = "response.cancelled"
TRANSPORT_CLOSED_REASON = "transport_closed"
ERROR_CLOSED_REASON = "error"


class RealtimeConversationPhase(Enum):
    """Rust ``RealtimeConversationPhase`` values."""

    INACTIVE = "Inactive"
    STARTING = "Starting"
    ACTIVE = "Active"
    STOPPING = "Stopping"


class RealtimeConversationUiTransportKind(Enum):
    """Semantic discriminator for Rust ``RealtimeConversationUiTransport``."""

    WEBSOCKET = "Websocket"
    WEBRTC = "Webrtc"


@dataclass
class RealtimeConversationUiTransport:
    """Semantic equivalent of Rust ``RealtimeConversationUiTransport``."""

    kind: RealtimeConversationUiTransportKind = RealtimeConversationUiTransportKind.WEBSOCKET
    handle: Optional[Any] = None

    @classmethod
    def websocket(cls) -> "RealtimeConversationUiTransport":
        return cls(RealtimeConversationUiTransportKind.WEBSOCKET)

    @classmethod
    def webrtc(cls, handle: Optional[Any] = None) -> "RealtimeConversationUiTransport":
        return cls(RealtimeConversationUiTransportKind.WEBRTC, handle)

    def uses_webrtc(self) -> bool:
        return self.kind is RealtimeConversationUiTransportKind.WEBRTC

    def close_handle(self) -> Optional[Any]:
        handle = self.handle
        self.handle = None
        if handle is not None and hasattr(handle, "close"):
            handle.close()
        return handle


@dataclass
class RealtimeConversationUiState:
    """Rust ``RealtimeConversationUiState`` phase and transport fields."""

    phase: RealtimeConversationPhase = RealtimeConversationPhase.INACTIVE
    requested_close: bool = False
    realtime_session_id: Optional[str] = None
    transport: RealtimeConversationUiTransport = field(default_factory=RealtimeConversationUiTransport.websocket)
    meter_placeholder_id: Optional[Any] = None

    def is_live(self) -> bool:
        return self.phase in {
            RealtimeConversationPhase.STARTING,
            RealtimeConversationPhase.ACTIVE,
            RealtimeConversationPhase.STOPPING,
        }

    def is_active(self) -> bool:
        return self.phase is RealtimeConversationPhase.ACTIVE


@dataclass(frozen=True)
class ThreadRealtimeStartedNotification:
    realtime_session_id: Optional[str] = None


@dataclass(frozen=True)
class ThreadRealtimeOutputAudioDeltaNotification:
    audio: Any


@dataclass(frozen=True)
class ThreadRealtimeItemAddedNotification:
    item: Any


@dataclass(frozen=True)
class ThreadRealtimeErrorNotification:
    message: str


@dataclass(frozen=True)
class ThreadRealtimeClosedNotification:
    reason: Optional[str] = None


@dataclass(frozen=True)
class RealtimeConversationStart:
    transport: Optional[Any] = None
    voice_config: Optional[Any] = None


@dataclass(frozen=True)
class RealtimeConversationClose:
    session_id: Optional[str] = None


@dataclass(frozen=True)
class RealtimeWebrtcOffer:
    offer_sdp: str
    handle: Any


@dataclass(frozen=True)
class RealtimeWebrtcTransportStart:
    sdp: str


class RealtimeWebrtcEventKind(Enum):
    CONNECTED = "Connected"
    CLOSED = "Closed"
    FAILED = "Failed"
    LOCAL_AUDIO_LEVEL = "LocalAudioLevel"


@dataclass(frozen=True)
class RealtimeWebrtcEvent:
    kind: RealtimeWebrtcEventKind
    message: Optional[str] = None
    peak: Optional[float] = None

    @classmethod
    def connected(cls) -> "RealtimeWebrtcEvent":
        return cls(RealtimeWebrtcEventKind.CONNECTED)

    @classmethod
    def closed(cls) -> "RealtimeWebrtcEvent":
        return cls(RealtimeWebrtcEventKind.CLOSED)

    @classmethod
    def failed(cls, message: str) -> "RealtimeWebrtcEvent":
        return cls(RealtimeWebrtcEventKind.FAILED, message=message)

    @classmethod
    def local_audio_level(cls, peak: float) -> "RealtimeWebrtcEvent":
        return cls(RealtimeWebrtcEventKind.LOCAL_AUDIO_LEVEL, peak=peak)


@dataclass(frozen=True)
class RealtimeWebrtcOfferTaskPlan:
    event: str = "RealtimeWebrtcOfferRequested"


@dataclass(frozen=True)
class RealtimeMeterTaskPlan:
    notification_id: Any
    text: str
    event: str = "UpdateRecordingMeter"


def realtime_footer_hint_items() -> tuple[tuple[str, str], ...]:
    return REALTIME_FOOTER_HINT_ITEMS


def start_realtime_webrtc_offer_task(
    app_event_tx: Any,
    starter: Optional[Callable[[], RealtimeWebrtcOffer]] = None,
) -> RealtimeWebrtcOfferTaskPlan:
    """Semantic hook for Rust's WebRTC-offer background task.

    When ``starter`` is provided the result or exception is delivered to
    ``app_event_tx`` as ``("RealtimeWebrtcOfferCreated", result)``.  Without a
    starter this returns a request plan instead of fabricating a WebRTC offer.
    """

    plan = RealtimeWebrtcOfferTaskPlan()
    if starter is None:
        _send_event(app_event_tx, plan)
        return plan
    try:
        result: Union[RealtimeWebrtcOffer, Exception] = starter()
    except Exception as exc:  # pragma: no cover - parity tests inspect value shape.
        result = exc
    _send_event(app_event_tx, ("RealtimeWebrtcOfferCreated", result))
    return plan


def start_realtime_meter_task(
    app_event_tx: Any,
    notification_id: Any,
    meter_text_fn: Optional[Callable[[], str]] = None,
) -> RealtimeMeterTaskPlan:
    """Semantic hook for Rust's recording-meter background task."""

    text = meter_text_fn() if meter_text_fn is not None else ""
    plan = RealtimeMeterTaskPlan(notification_id=notification_id, text=text)
    _send_event(app_event_tx, plan)
    return plan


@dataclass
class RealtimeWidgetModel:
    """Small semantic model for Rust ``ChatWidget`` realtime methods."""

    realtime_conversation: RealtimeConversationUiState = field(default_factory=RealtimeConversationUiState)
    transport_config: RealtimeConversationUiTransportKind = RealtimeConversationUiTransportKind.WEBSOCKET
    realtime_enabled: bool = True
    voice_config: Optional[Any] = None
    footer_hint_override: Optional[Tuple[Tuple[str, str], ...]] = None
    submitted_ops: list = field(default_factory=list)
    info_messages: list = field(default_factory=list)
    error_messages: list = field(default_factory=list)
    audio_out: list = field(default_factory=list)
    events: list = field(default_factory=list)
    redraw_requests: int = 0
    local_audio_starts: int = 0
    local_audio_stops: int = 0
    playback_interrupts: int = 0

    def realtime_footer_hint_items(self) -> Tuple[Tuple[str, str], ...]:
        return realtime_footer_hint_items()

    def start_realtime_conversation(self) -> None:
        state = self.realtime_conversation
        state.phase = RealtimeConversationPhase.STARTING
        state.requested_close = False
        state.realtime_session_id = None
        self.footer_hint_override = self.realtime_footer_hint_items()

        if self.transport_config is RealtimeConversationUiTransportKind.WEBRTC:
            state.transport = RealtimeConversationUiTransport.webrtc()
            start_realtime_webrtc_offer_task(self.events)
        else:
            state.transport = RealtimeConversationUiTransport.websocket()
            self.submit_realtime_conversation_start(None)
        self.request_redraw()

    def submit_realtime_conversation_start(self, transport: Optional[Any]) -> None:
        self.submitted_ops.append(RealtimeConversationStart(transport=transport, voice_config=self.voice_config))

    def request_realtime_conversation_close(self, info_message: Optional[str] = None) -> None:
        state = self.realtime_conversation
        if not state.is_live():
            if info_message is not None:
                self.add_info_message(info_message)
            return

        state.requested_close = True
        state.phase = RealtimeConversationPhase.STOPPING
        self.submitted_ops.append(RealtimeConversationClose(session_id=state.realtime_session_id))
        self.stop_local_audio()
        self.close_realtime_webrtc_transport()
        self.footer_hint_override = None
        if info_message is not None:
            self.add_info_message(info_message)
        else:
            self.request_redraw()

    def stop_realtime_conversation_from_ui(self) -> None:
        self.request_realtime_conversation_close(None)

    def stop_realtime_conversation_for_deleted_meter(self, notification_id: Any) -> bool:
        state = self.realtime_conversation
        if state.is_live() and state.meter_placeholder_id == notification_id:
            state.meter_placeholder_id = None
            self.stop_realtime_conversation_from_ui()
            return True
        return False

    def reset_realtime_conversation_state(self) -> None:
        self.stop_local_audio()
        self.close_realtime_webrtc_transport()
        self.footer_hint_override = None
        self.realtime_conversation = RealtimeConversationUiState()

    def fail_realtime_conversation(self, message: str) -> None:
        self.add_error_message(message)
        if self.realtime_conversation.is_live():
            self.request_realtime_conversation_close(None)
        else:
            self.reset_realtime_conversation_state()
            self.request_redraw()

    def on_realtime_conversation_started(self, notification: ThreadRealtimeStartedNotification) -> None:
        if not self.realtime_enabled:
            self.request_realtime_conversation_close(None)
            return

        self.realtime_conversation.realtime_session_id = notification.realtime_session_id
        self.footer_hint_override = self.realtime_footer_hint_items()
        if self.realtime_conversation_uses_webrtc():
            self.realtime_conversation.phase = RealtimeConversationPhase.STARTING
        else:
            self.realtime_conversation.phase = RealtimeConversationPhase.ACTIVE
            self.start_local_audio()
        self.request_redraw()

    def on_realtime_output_audio_delta(self, notification: ThreadRealtimeOutputAudioDeltaNotification) -> None:
        if self.realtime_conversation_uses_webrtc():
            return
        self.audio_out.append(notification.audio)

    def on_realtime_item_added(self, notification: ThreadRealtimeItemAddedNotification) -> None:
        if self.realtime_conversation_uses_webrtc():
            return
        item_type = _item_type(notification.item)
        if item_type in {SPEECH_STARTED_ITEM_TYPE, RESPONSE_CANCELLED_ITEM_TYPE}:
            self.interrupt_audio_playback()

    def on_realtime_error(self, notification: ThreadRealtimeErrorNotification) -> None:
        self.fail_realtime_conversation(f"Realtime voice error: {notification.message}")

    def on_realtime_conversation_closed(self, notification: ThreadRealtimeClosedNotification) -> None:
        if (
            self.realtime_conversation_uses_webrtc()
            and self.realtime_conversation.is_live()
            and notification.reason == TRANSPORT_CLOSED_REASON
        ):
            return

        requested_close = self.realtime_conversation.requested_close
        reason = notification.reason
        self.reset_realtime_conversation_state()
        if not requested_close and reason is not None and reason != ERROR_CLOSED_REASON:
            self.add_info_message(f"Realtime voice mode closed: {reason}")
        self.request_redraw()

    def on_realtime_conversation_sdp(self, sdp: str) -> None:
        if not self.realtime_conversation_uses_webrtc():
            return
        handle = self.realtime_conversation.transport.handle
        if handle is None:
            return
        try:
            handle.apply_answer_sdp(sdp)
        except Exception as exc:
            self.fail_realtime_conversation(f"Failed to connect realtime WebRTC: {exc}")

    def on_realtime_webrtc_offer_created(self, result: Union[RealtimeWebrtcOffer, Exception]) -> None:
        state = self.realtime_conversation
        if state.phase is not RealtimeConversationPhase.STARTING:
            return
        if not state.transport.uses_webrtc() or state.transport.handle is not None:
            return
        if isinstance(result, Exception):
            self.fail_realtime_conversation(f"Failed to start realtime WebRTC: {result}")
            return
        state.transport.handle = result.handle
        self.submit_realtime_conversation_start(RealtimeWebrtcTransportStart(sdp=result.offer_sdp))
        self.request_redraw()

    def on_realtime_webrtc_event(self, event: RealtimeWebrtcEvent) -> None:
        if not self.realtime_conversation_uses_webrtc():
            return
        if event.kind is RealtimeWebrtcEventKind.CONNECTED:
            if self.realtime_conversation.phase is RealtimeConversationPhase.STARTING:
                self.realtime_conversation.phase = RealtimeConversationPhase.ACTIVE
                self.footer_hint_override = self.realtime_footer_hint_items()
                self.request_redraw()
        elif event.kind is RealtimeWebrtcEventKind.CLOSED:
            self.reset_realtime_conversation_state()
            self.request_redraw()
        elif event.kind is RealtimeWebrtcEventKind.FAILED:
            self.fail_realtime_conversation(f"Realtime WebRTC error: {event.message}")
        elif event.kind is RealtimeWebrtcEventKind.LOCAL_AUDIO_LEVEL:
            self.on_realtime_webrtc_local_audio_level(event.peak or 0.0)

    def on_realtime_webrtc_local_audio_level(self, peak: float) -> None:
        if not self.realtime_conversation_uses_webrtc() or peak == 0:
            return
        if self.realtime_conversation.transport.handle is None:
            return
        if self.realtime_conversation.meter_placeholder_id is None:
            self.realtime_conversation.meter_placeholder_id = "recording-meter"

    def realtime_conversation_uses_webrtc(self) -> bool:
        return self.realtime_conversation.transport.uses_webrtc()

    def close_realtime_webrtc_transport(self) -> None:
        if self.realtime_conversation.transport.uses_webrtc():
            self.realtime_conversation.transport.close_handle()

    def add_info_message(self, message: str) -> None:
        self.info_messages.append(message)

    def add_error_message(self, message: str) -> None:
        self.error_messages.append(message)

    def request_redraw(self) -> None:
        self.redraw_requests += 1

    def start_local_audio(self) -> None:
        self.local_audio_starts += 1

    def stop_local_audio(self) -> None:
        self.local_audio_stops += 1

    def interrupt_audio_playback(self) -> None:
        self.playback_interrupts += 1


def _item_type(item: Any) -> Optional[str]:
    if isinstance(item, dict):
        value = item.get("type")
        return str(value) if value is not None else None
    value = getattr(item, "type", None)
    return str(value) if value is not None else None


def _send_event(sink: Any, event: Any) -> None:
    if sink is None:
        return
    if callable(sink):
        sink(event)
    elif hasattr(sink, "send"):
        sink.send(event)
    elif isinstance(sink, MutableSequence):
        sink.append(event)
    elif hasattr(sink, "append"):
        sink.append(event)


__all__ = [
    "ERROR_CLOSED_REASON",
    "REALTIME_FOOTER_HINT_ITEMS",
    "RESPONSE_CANCELLED_ITEM_TYPE",
    "RUST_MODULE",
    "SPEECH_STARTED_ITEM_TYPE",
    "TRANSPORT_CLOSED_REASON",
    "RealtimeConversationClose",
    "RealtimeConversationPhase",
    "RealtimeConversationStart",
    "RealtimeConversationUiState",
    "RealtimeConversationUiTransport",
    "RealtimeConversationUiTransportKind",
    "RealtimeFooterHintItems",
    "RealtimeMeterTaskPlan",
    "RealtimeWebrtcEvent",
    "RealtimeWebrtcEventKind",
    "RealtimeWebrtcOffer",
    "RealtimeWebrtcOfferTaskPlan",
    "RealtimeWebrtcTransportStart",
    "RealtimeWidgetModel",
    "ThreadRealtimeClosedNotification",
    "ThreadRealtimeErrorNotification",
    "ThreadRealtimeItemAddedNotification",
    "ThreadRealtimeOutputAudioDeltaNotification",
    "ThreadRealtimeStartedNotification",
    "realtime_footer_hint_items",
    "start_realtime_meter_task",
    "start_realtime_webrtc_offer_task",
]

# Backwards-friendly alias for callers that mirror Rust naming around footer hints.
RealtimeFooterHintItems = tuple
