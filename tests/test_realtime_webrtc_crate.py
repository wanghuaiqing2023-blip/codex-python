from __future__ import annotations

from queue import Queue

import pytest

from pycodex.realtime_webrtc import (
    RealtimeWebrtcError,
    RealtimeWebrtcEvent,
    RealtimeWebrtcEventKind,
    RealtimeWebrtcSession,
    RealtimeWebrtcSessionHandle,
    StartedRealtimeWebrtcSession,
    UnsupportedPlatform,
    audio_level_to_peak,
    message_error,
)


def test_public_event_shapes_and_started_session() -> None:
    # Rust crate/module: codex-realtime-webrtc src/lib.rs. Behavior contract:
    # public event/session shapes expose the same connected/audio/closed/failed
    # data boundaries as the Rust enum and StartedRealtimeWebrtcSession struct.
    connected = RealtimeWebrtcEvent(RealtimeWebrtcEventKind.CONNECTED)
    level = RealtimeWebrtcEvent(RealtimeWebrtcEventKind.LOCAL_AUDIO_LEVEL, 42)
    failed = RealtimeWebrtcEvent(RealtimeWebrtcEventKind.FAILED, "boom")
    handle = RealtimeWebrtcSessionHandle(local_audio_peak_value=7)
    events: Queue[RealtimeWebrtcEvent] = Queue()
    session = StartedRealtimeWebrtcSession("offer", handle, events)

    assert connected.kind is RealtimeWebrtcEventKind.CONNECTED
    assert connected.value is None
    assert level.value == 42
    assert failed.value == "boom"
    assert session.offer_sdp == "offer"
    assert session.handle is handle
    assert session.events is events


def test_non_native_public_methods_report_unsupported_platform() -> None:
    # Rust crate/module: codex-realtime-webrtc src/lib.rs. Behavior contract:
    # outside the native macOS implementation, start/apply_answer_sdp report
    # unsupported platform while close is harmless.
    with pytest.raises(UnsupportedPlatform, match="realtime WebRTC is not supported on this platform"):
        RealtimeWebrtcSession.start()

    handle = RealtimeWebrtcSessionHandle(local_audio_peak_value=9)
    with pytest.raises(UnsupportedPlatform, match="realtime WebRTC is not supported on this platform"):
        handle.apply_answer_sdp("answer")

    assert handle.close() is None
    assert handle.local_audio_peak() == 9


def test_message_error_formats_native_error_context() -> None:
    # Rust crate/module: codex-realtime-webrtc src/native.rs. Behavior
    # contract: message_error formats native errors as "{prefix}: {err}".
    error = message_error("failed to create WebRTC offer", ValueError("bad sdp"))

    assert isinstance(error, RealtimeWebrtcError)
    assert str(error) == "failed to create WebRTC offer: bad sdp"


def test_audio_level_to_peak_clamps_and_rounds_like_rust() -> None:
    # Rust crate/module: codex-realtime-webrtc src/native.rs. Behavior
    # contract: clamp to [0, 1], multiply by i16::MAX, round, cast to u16.
    assert audio_level_to_peak(-0.5) == 0
    assert audio_level_to_peak(0.0) == 0
    assert audio_level_to_peak(0.5) == 16384
    assert audio_level_to_peak(1.0) == 32767
    assert audio_level_to_peak(1.5) == 32767
