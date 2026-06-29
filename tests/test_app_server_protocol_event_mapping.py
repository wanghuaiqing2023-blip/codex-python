from pycodex.app_server_protocol import item_event_to_server_notification


def test_reasoning_content_delta_with_summary_index_maps_to_summary_text_delta() -> None:
    # Rust source contract:
    # - codex-rs/core/src/session/turn.rs maps
    #   ResponseEvent::ReasoningSummaryDelta into EventMsg::ReasoningContentDelta.
    # - codex-rs/app-server-protocol/src/protocol/event_mapping.rs maps that
    #   EventMsg::ReasoningContentDelta into ServerNotification::ReasoningSummaryTextDelta.
    notification = item_event_to_server_notification(
        {
            "type": "reasoning_content_delta",
            "item_id": "reason-1",
            "delta": "**Reading** files",
            "summary_index": 2,
        },
        "thread-1",
        "turn-1",
    )

    assert notification.type == "ReasoningSummaryTextDelta"
    assert notification.payload.delta == "**Reading** files"
    assert notification.payload.summary_index == 2


def test_reasoning_content_delta_with_content_index_maps_to_raw_text_delta() -> None:
    # Python product-path compatibility:
    # - pycodex.core.http_transport emits response.reasoning_text.delta as
    #   reasoning_content_delta with content_index.
    # - codex-tui::chatwidget::protocol only displays ReasoningTextDelta when
    #   show_raw_agent_reasoning is enabled, so this must not be projected as
    #   ReasoningSummaryTextDelta.
    notification = item_event_to_server_notification(
        {
            "type": "reasoning_content_delta",
            "item_id": "reason-1",
            "delta": "private raw reasoning",
            "content_index": 3,
        },
        "thread-1",
        "turn-1",
    )

    assert notification.type == "ReasoningTextDelta"
    assert notification.payload.delta == "private raw reasoning"
    assert notification.payload.content_index == 3


def test_reasoning_raw_content_delta_maps_to_raw_text_delta() -> None:
    # Rust source contract:
    # - codex-rs/core/src/session/turn.rs maps raw
    #   ResponseEvent::ReasoningContentDelta into EventMsg::ReasoningRawContentDelta.
    # - codex-rs/app-server-protocol/src/protocol/event_mapping.rs maps it to
    #   ServerNotification::ReasoningTextDelta.
    notification = item_event_to_server_notification(
        {
            "type": "reasoning_raw_content_delta",
            "item_id": "reason-1",
            "delta": "private raw reasoning",
            "content_index": 4,
        },
        "thread-1",
        "turn-1",
    )

    assert notification.type == "ReasoningTextDelta"
    assert notification.payload.delta == "private raw reasoning"
    assert notification.payload.content_index == 4
