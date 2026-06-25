from pycodex.tui.chatwidget.realtime import (
    ERROR_CLOSED_REASON,
    REALTIME_FOOTER_HINT_ITEMS,
    RESPONSE_CANCELLED_ITEM_TYPE,
    SPEECH_STARTED_ITEM_TYPE,
    TRANSPORT_CLOSED_REASON,
    RealtimeConversationPhase,
    RealtimeConversationStart,
    RealtimeConversationUiState,
    RealtimeConversationUiTransport,
    RealtimeConversationUiTransportKind,
    RealtimeWebrtcEvent,
    RealtimeWebrtcOffer,
    RealtimeWebrtcTransportStart,
    RealtimeWidgetModel,
    ThreadRealtimeClosedNotification,
    ThreadRealtimeErrorNotification,
    ThreadRealtimeItemAddedNotification,
    ThreadRealtimeOutputAudioDeltaNotification,
    ThreadRealtimeStartedNotification,
    start_realtime_meter_task,
    start_realtime_webrtc_offer_task,
)


class FakeHandle:
    def __init__(self):
        self.closed = False
        self.answer_sdp = None

    def close(self):
        self.closed = True

    def apply_answer_sdp(self, sdp):
        self.answer_sdp = sdp


def test_phase_live_active_helpers_match_rust_variants():
    state = RealtimeConversationUiState()
    assert not state.is_live()
    assert not state.is_active()

    state.phase = RealtimeConversationPhase.STARTING
    assert state.is_live()
    assert not state.is_active()

    state.phase = RealtimeConversationPhase.ACTIVE
    assert state.is_live()
    assert state.is_active()

    state.phase = RealtimeConversationPhase.STOPPING
    assert state.is_live()
    assert not state.is_active()


def test_start_websocket_submits_start_sets_footer_and_redraw():
    widget = RealtimeWidgetModel(voice_config={"voice": "alloy"})

    widget.start_realtime_conversation()

    assert widget.realtime_conversation.phase is RealtimeConversationPhase.STARTING
    assert widget.realtime_conversation.transport.kind is RealtimeConversationUiTransportKind.WEBSOCKET
    assert widget.footer_hint_override == REALTIME_FOOTER_HINT_ITEMS
    assert widget.submitted_ops == [RealtimeConversationStart(transport=None, voice_config={"voice": "alloy"})]
    assert widget.redraw_requests == 1


def test_request_close_handles_live_and_inactive_paths():
    inactive = RealtimeWidgetModel()
    inactive.request_realtime_conversation_close("already stopped")
    assert inactive.info_messages == ["already stopped"]
    assert inactive.submitted_ops == []

    handle = FakeHandle()
    live = RealtimeWidgetModel()
    live.realtime_conversation.phase = RealtimeConversationPhase.ACTIVE
    live.realtime_conversation.realtime_session_id = "sess"
    live.realtime_conversation.transport = RealtimeConversationUiTransport.webrtc(handle)

    live.request_realtime_conversation_close()

    assert live.realtime_conversation.phase is RealtimeConversationPhase.STOPPING
    assert live.realtime_conversation.requested_close is True
    assert live.submitted_ops[-1].session_id == "sess"
    assert live.footer_hint_override is None
    assert live.local_audio_stops == 1
    assert handle.closed is True


def test_started_audio_and_item_notifications_follow_transport_guards():
    widget = RealtimeWidgetModel()
    widget.start_realtime_conversation()

    widget.on_realtime_conversation_started(ThreadRealtimeStartedNotification("sess"))
    widget.on_realtime_output_audio_delta(ThreadRealtimeOutputAudioDeltaNotification("delta"))
    widget.on_realtime_item_added(ThreadRealtimeItemAddedNotification({"type": SPEECH_STARTED_ITEM_TYPE}))
    widget.on_realtime_item_added(ThreadRealtimeItemAddedNotification({"type": RESPONSE_CANCELLED_ITEM_TYPE}))

    assert widget.realtime_conversation.phase is RealtimeConversationPhase.ACTIVE
    assert widget.realtime_conversation.realtime_session_id == "sess"
    assert widget.local_audio_starts == 1
    assert widget.audio_out == ["delta"]
    assert widget.playback_interrupts == 2

    webrtc = RealtimeWidgetModel(transport_config=RealtimeConversationUiTransportKind.WEBRTC)
    webrtc.start_realtime_conversation()
    webrtc.on_realtime_output_audio_delta(ThreadRealtimeOutputAudioDeltaNotification("ignored"))
    webrtc.on_realtime_item_added(ThreadRealtimeItemAddedNotification({"type": SPEECH_STARTED_ITEM_TYPE}))
    assert webrtc.audio_out == []
    assert webrtc.playback_interrupts == 0


def test_error_and_closed_notifications_reset_or_close_like_rust():
    widget = RealtimeWidgetModel()
    widget.realtime_conversation.phase = RealtimeConversationPhase.ACTIVE
    widget.on_realtime_error(ThreadRealtimeErrorNotification("boom"))

    assert widget.error_messages == ["Realtime voice error: boom"]
    assert widget.realtime_conversation.phase is RealtimeConversationPhase.STOPPING

    unexpected = RealtimeWidgetModel()
    unexpected.realtime_conversation.phase = RealtimeConversationPhase.ACTIVE
    unexpected.on_realtime_conversation_closed(ThreadRealtimeClosedNotification("server_closed"))
    assert unexpected.realtime_conversation.phase is RealtimeConversationPhase.INACTIVE
    assert unexpected.info_messages == ["Realtime voice mode closed: server_closed"]

    error_close = RealtimeWidgetModel()
    error_close.realtime_conversation.phase = RealtimeConversationPhase.ACTIVE
    error_close.on_realtime_conversation_closed(ThreadRealtimeClosedNotification(ERROR_CLOSED_REASON))
    assert error_close.info_messages == []

    webrtc_transport_closed = RealtimeWidgetModel(transport_config=RealtimeConversationUiTransportKind.WEBRTC)
    webrtc_transport_closed.start_realtime_conversation()
    webrtc_transport_closed.on_realtime_conversation_closed(ThreadRealtimeClosedNotification(TRANSPORT_CLOSED_REASON))
    assert webrtc_transport_closed.realtime_conversation.phase is RealtimeConversationPhase.STARTING


def test_webrtc_offer_sdp_events_and_meter_flow():
    handle = FakeHandle()
    widget = RealtimeWidgetModel(transport_config=RealtimeConversationUiTransportKind.WEBRTC)
    widget.start_realtime_conversation()
    assert widget.events

    widget.on_realtime_webrtc_offer_created(RealtimeWebrtcOffer("offer-sdp", handle))
    assert widget.realtime_conversation.transport.handle is handle
    assert widget.submitted_ops[-1].transport == RealtimeWebrtcTransportStart(sdp="offer-sdp")

    widget.on_realtime_conversation_sdp("answer-sdp")
    assert handle.answer_sdp == "answer-sdp"

    widget.on_realtime_webrtc_event(RealtimeWebrtcEvent.connected())
    assert widget.realtime_conversation.phase is RealtimeConversationPhase.ACTIVE
    assert widget.footer_hint_override == REALTIME_FOOTER_HINT_ITEMS

    widget.on_realtime_webrtc_event(RealtimeWebrtcEvent.local_audio_level(0.5))
    assert widget.realtime_conversation.meter_placeholder_id == "recording-meter"
    assert widget.stop_realtime_conversation_for_deleted_meter("recording-meter") is True
    assert handle.closed is True


def test_task_hooks_send_semantic_events_without_fabricating_runtime_io():
    events = []
    plan = start_realtime_webrtc_offer_task(events)
    assert events == [plan]

    handle = FakeHandle()
    start_realtime_webrtc_offer_task(events, lambda: RealtimeWebrtcOffer("sdp", handle))
    assert events[-1] == ("RealtimeWebrtcOfferCreated", RealtimeWebrtcOffer("sdp", handle))

    meter_plan = start_realtime_meter_task(events, "meter-id", lambda: "rec")
    assert meter_plan.text == "rec"
    assert events[-1] == meter_plan
