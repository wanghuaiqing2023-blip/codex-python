"""Rust integration parity for ``core/tests/suite/items.rs``.

The Rust suite drives mocked Responses streams and observes the emitted turn
items, legacy events, plan-mode text, and delta metadata.  Python keeps those
observable contracts at the protocol/event-mapping/stream-parser boundary,
without recreating the Rust network fixture harness.
"""

from __future__ import annotations

import pytest

from pycodex.core.client import _item_lifecycle_event
from pycodex.core.event_mapping import parse_turn_item
from pycodex.core.stream_events_utils import save_image_generation_result
from pycodex.protocol import (
    AgentMessageContent,
    AgentMessageContentDeltaEvent,
    AgentMessageItem,
    ByteRange,
    ContentItem,
    ImageGenerationItem,
    ItemCompletedEvent,
    ItemStartedEvent,
    ReasoningContentDeltaEvent,
    ReasoningItem,
    ReasoningItemContent,
    ReasoningRawContentDeltaEvent,
    ReasoningItemReasoningSummary,
    ResponseItem,
    TextElement,
    TurnItem,
    UserInput,
    WebSearchAction,
)
from pycodex.utils.stream_parser import AssistantTextStreamParser, ProposedPlanSegment, ProposedPlanSegmentKind


def _legacy_payload_types(event) -> tuple[str, ...]:
    return tuple(item.type for item in event.as_legacy_events())


def _agent_text(item: TurnItem) -> str:
    assert item.type == "AgentMessage"
    return "".join(content.text for content in item.item.content)


def _parse_plan_stream(chunks: tuple[str, ...]) -> tuple[str, str, list[ProposedPlanSegment]]:
    parser = AssistantTextStreamParser(plan_mode=True)
    visible: list[str] = []
    plan: list[str] = []
    segments: list[ProposedPlanSegment] = []
    for chunk in chunks:
        parsed = parser.push_str(chunk)
        visible.append(parsed.visible_text)
        segments.extend(parsed.plan_segments)
        for segment in parsed.plan_segments:
            if segment.kind == ProposedPlanSegmentKind.PROPOSED_PLAN_DELTA:
                plan.append(segment.text)
    tail = parser.finish()
    visible.append(tail.visible_text)
    segments.extend(tail.plan_segments)
    for segment in tail.plan_segments:
        if segment.kind == ProposedPlanSegmentKind.PROPOSED_PLAN_DELTA:
            plan.append(segment.text)
    return "".join(visible), "".join(plan), segments


def test_user_message_item_is_emitted() -> None:
    """Rust: ``user_message_item_is_emitted``."""

    text_elements = (TextElement.new(ByteRange(0, 6), "<file>"),)
    expected_input = UserInput.text_input("please inspect sample.txt", text_elements)
    item = parse_turn_item(ResponseItem.message("user", (ContentItem.input_text(expected_input.text or ""),)))

    assert item is not None
    assert item.type == "UserMessage"
    assert item.item.content == (UserInput.text_input("please inspect sample.txt"),)
    user_turn_item = TurnItem.user_message(type(item.item).new((expected_input,)))
    started = ItemStartedEvent("thread-1", "turn-1", user_turn_item, 123)
    completed = ItemCompletedEvent("thread-1", "turn-1", user_turn_item, 456)
    assert started.item.item.content == completed.item.item.content == (expected_input,)
    legacy = completed.as_legacy_events()[0].payload
    assert legacy.message == "please inspect sample.txt"
    assert legacy.text_elements == text_elements


def test_assistant_message_item_is_emitted() -> None:
    """Rust: ``assistant_message_item_is_emitted``."""

    item = parse_turn_item(ResponseItem.message("assistant", (ContentItem.output_text("all done"),), id="msg-1"))

    assert item == TurnItem.agent_message(
        AgentMessageItem("msg-1", (AgentMessageContent.text_content("all done"),))
    )
    completed = ItemCompletedEvent("thread-1", "turn-1", item, 456)
    legacy = completed.as_legacy_events()[0].payload
    assert legacy.message == "all done"


def test_reasoning_item_is_emitted() -> None:
    """Rust: ``reasoning_item_is_emitted``."""

    response = ResponseItem.reasoning(
        id="reasoning-1",
        summary=(
            ReasoningItemReasoningSummary("summary_text", "Consider inputs"),
            ReasoningItemReasoningSummary("summary_text", "Compute output"),
        ),
        content=(ReasoningItemContent("reasoning_text", "Detailed reasoning trace"),),
    )
    item = parse_turn_item(response)

    assert item == TurnItem.reasoning(
        ReasoningItem("reasoning-1", ("Consider inputs", "Compute output"), ("Detailed reasoning trace",))
    )
    raw_events = ItemCompletedEvent("thread-1", "turn-1", item).as_legacy_events(show_raw_agent_reasoning=True)
    assert _legacy_payload_types(ItemCompletedEvent("thread-1", "turn-1", item)) == ("agent_reasoning", "agent_reasoning")
    assert tuple(event.type for event in raw_events) == (
        "agent_reasoning",
        "agent_reasoning",
        "agent_reasoning_raw_content",
    )


def test_web_search_item_is_emitted() -> None:
    """Rust: ``web_search_item_is_emitted``."""

    action = WebSearchAction.search(query="weather seattle")
    item = parse_turn_item(ResponseItem.web_search_call("web-search-1", "completed", action=action))

    assert item is not None
    assert item.type == "WebSearch"
    assert item.item.id == "web-search-1"
    assert item.item.action == action
    begin = ItemStartedEvent("thread-1", "turn-1", item, 123).as_legacy_events()[0].payload
    end = ItemCompletedEvent("thread-1", "turn-1", item, 456).as_legacy_events()[0].payload
    assert begin.call_id == "web-search-1"
    assert end.call_id == "web-search-1"
    assert end.query == "weather seattle"


def test_image_generation_call_event_is_emitted(tmp_path) -> None:
    """Rust: ``image_generation_call_event_is_emitted``."""

    saved_path = save_image_generation_result(tmp_path, "session-1", "ig_image_saved_to_temp_dir_default", "Zm9v")
    item = TurnItem.image_generation(
        ImageGenerationItem(
            "ig_image_saved_to_temp_dir_default",
            "completed",
            "Zm9v",
            "A tiny blue square",
            saved_path,
        )
    )

    begin = ItemStartedEvent("thread-1", "turn-1", item, 123).as_legacy_events()[0].payload
    end = ItemCompletedEvent("thread-1", "turn-1", item, 456).as_legacy_events()[0].payload
    assert begin.call_id == "ig_image_saved_to_temp_dir_default"
    assert end.call_id == "ig_image_saved_to_temp_dir_default"
    assert end.status == "completed"
    assert end.revised_prompt == "A tiny blue square"
    assert end.result == "Zm9v"
    assert end.saved_path == saved_path
    assert saved_path.read_bytes() == b"foo"


def test_image_generation_call_event_is_emitted_when_image_save_fails(tmp_path) -> None:
    """Rust: ``image_generation_call_event_is_emitted_when_image_save_fails``."""

    with pytest.raises(ValueError):
        save_image_generation_result(tmp_path, "session-1", "ig_invalid", "_-8")
    item = TurnItem.image_generation(ImageGenerationItem("ig_invalid", "completed", "_-8", "broken payload", None))
    end = ItemCompletedEvent("thread-1", "turn-1", item, 456).as_legacy_events()[0].payload

    assert end.call_id == "ig_invalid"
    assert end.status == "completed"
    assert end.revised_prompt == "broken payload"
    assert end.result == "_-8"
    assert end.saved_path is None


def test_agent_message_content_delta_has_item_metadata() -> None:
    """Rust: ``agent_message_content_delta_has_item_metadata``."""

    item = TurnItem.agent_message(AgentMessageItem("msg-1", ()))
    started = _item_lifecycle_event("item_started", "thread-1", "turn-1", item)
    delta = AgentMessageContentDeltaEvent(
        thread_id=started["thread_id"],
        turn_id=started["turn_id"],
        item_id=started["item"]["id"],
        delta="streamed response",
    )

    assert delta.thread_id == "thread-1"
    assert delta.turn_id == "turn-1"
    assert delta.item_id == "msg-1"
    assert delta.delta == "streamed response"


def test_plan_mode_emits_plan_item_from_proposed_plan_block() -> None:
    """Rust: ``plan_mode_emits_plan_item_from_proposed_plan_block``."""

    visible, plan, segments = _parse_plan_stream(("Intro\n<proposed_plan>\n- Step 1\n- Step 2\n</proposed_plan>\nOutro",))

    assert visible == "Intro\nOutro"
    assert plan == "- Step 1\n- Step 2\n"
    assert ProposedPlanSegment.proposed_plan_start() in segments
    assert ProposedPlanSegment.proposed_plan_end() in segments


def test_plan_mode_strips_plan_from_agent_messages() -> None:
    """Rust: ``plan_mode_strips_plan_from_agent_messages``."""

    visible, plan, _segments = _parse_plan_stream(("Intro\n<proposed_plan>\n- Step 1\n- Step 2\n</proposed_plan>\nOutro",))
    agent_item = TurnItem.agent_message(
        AgentMessageItem("msg-1", (AgentMessageContent.text_content(visible),))
    )

    assert _agent_text(agent_item) == "Intro\nOutro"
    assert plan == "- Step 1\n- Step 2\n"


def test_plan_mode_streaming_citations_are_stripped_across_added_deltas_and_done() -> None:
    """Rust: ``plan_mode_streaming_citations_are_stripped_across_added_deltas_and_done``."""

    chunks = (
        "Intro <oai-mem-",
        "citation>outer-doc</oai-mem-citation>\n<proposed",
        "_plan>\n- Step 1<oai-mem-",
        "citation>plan-doc</oai-mem-citation>\n- Step 2\n</proposed_plan>\nOu",
        "tro",
    )
    visible, plan, _segments = _parse_plan_stream(chunks)

    assert visible == "Intro \nOutro"
    assert plan == "- Step 1\n- Step 2\n"
    assert "<oai-mem-citation>" not in visible
    assert "<oai-mem-citation>" not in plan


def test_plan_mode_streaming_proposed_plan_tag_split_across_added_and_delta_is_parsed() -> None:
    """Rust: ``plan_mode_streaming_proposed_plan_tag_split_across_added_and_delta_is_parsed``."""

    visible, plan, _segments = _parse_plan_stream(("Intro\n<proposed", "_plan>\n- Step 1\n</proposed_plan>\nOutro"))

    assert visible == "Intro\nOutro"
    assert plan == "- Step 1\n"


def test_plan_mode_handles_missing_plan_close_tag() -> None:
    """Rust: ``plan_mode_handles_missing_plan_close_tag``."""

    visible, plan, _segments = _parse_plan_stream(("Intro\n<proposed_plan>\n- Step 1\n",))

    assert visible == "Intro\n"
    assert plan == "- Step 1\n"


def test_reasoning_content_delta_has_item_metadata() -> None:
    """Rust: ``reasoning_content_delta_has_item_metadata``."""

    event = ReasoningContentDeltaEvent("thread-1", "turn-1", "reasoning-1", "step one")

    assert event.thread_id == "thread-1"
    assert event.turn_id == "turn-1"
    assert event.item_id == "reasoning-1"
    assert event.delta == "step one"
    assert event.summary_index == 0


def test_reasoning_raw_content_delta_respects_flag() -> None:
    """Rust: ``reasoning_raw_content_delta_respects_flag``."""

    item = TurnItem.reasoning(ReasoningItem("reasoning-raw", ("complete",), ("raw detail",)))
    hidden = ItemCompletedEvent("thread-1", "turn-1", item).as_legacy_events(show_raw_agent_reasoning=False)
    shown = ItemCompletedEvent("thread-1", "turn-1", item).as_legacy_events(show_raw_agent_reasoning=True)
    delta = ReasoningRawContentDeltaEvent("thread-1", "turn-1", "reasoning-raw", "raw detail")

    assert tuple(event.type for event in hidden) == ("agent_reasoning",)
    assert tuple(event.type for event in shown) == ("agent_reasoning", "agent_reasoning_raw_content")
    assert delta.item_id == "reasoning-raw"
    assert delta.delta == "raw detail"
