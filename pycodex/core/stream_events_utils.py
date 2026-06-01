"""Small stream-event helpers ported from Codex core."""

from __future__ import annotations

import base64
import binascii
import inspect
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path

from pycodex.core.context import ImageGenerationInstructions
from pycodex.core.event_mapping import parse_turn_item
from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tool_router import ToolCall, ToolRouter
from pycodex.protocol import AgentMessageContent, AgentMessageItem, ImageGenerationItem, MessagePhase, ResponseInputItem, ResponseItem, ToolName, TurnItem
from pycodex.protocol import MemoryCitation, MemoryCitationEntry


GENERATED_IMAGE_ARTIFACTS_DIR = "generated_images"
CITATION_OPEN = "<oai-mem-citation>"
CITATION_CLOSE = "</oai-mem-citation>"
PROPOSED_PLAN_OPEN = "<proposed_plan>"
PROPOSED_PLAN_CLOSE = "</proposed_plan>"


def _sanitize_image_artifact_component(value: str) -> str:
    _ensure_str(value, "image artifact component")
    sanitized = "".join(
        ch if ch.isascii() and (ch.isalnum() or ch in {"-", "_"}) else "_"
        for ch in value
    )
    return sanitized or "generated_image"


def image_generation_artifact_path(
    codex_home: str | Path,
    session_id: str,
    call_id: str,
) -> Path:
    _ensure_pathlike(codex_home, "codex_home")
    _ensure_str(session_id, "session_id")
    _ensure_str(call_id, "call_id")
    return (
        Path(codex_home)
        / GENERATED_IMAGE_ARTIFACTS_DIR
        / _sanitize_image_artifact_component(session_id)
        / f"{_sanitize_image_artifact_component(call_id)}.png"
    )


def save_image_generation_result(
    codex_home: str | Path,
    session_id: str,
    call_id: str,
    result: str,
) -> Path:
    _ensure_pathlike(codex_home, "codex_home")
    _ensure_str(session_id, "session_id")
    _ensure_str(call_id, "call_id")
    _ensure_str(result, "result")
    try:
        data = base64.b64decode(result.strip().encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError(f"invalid image generation payload: {exc}") from exc

    path = image_generation_artifact_path(codex_home, session_id, call_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def raw_assistant_output_text_from_item(item: ResponseItem) -> str | None:
    _ensure_response_item(item)
    if item.type != "message" or item.role != "assistant":
        return None
    return "".join(
        content.text or ""
        for content in item.content
        if content.type == "output_text"
    )


def agent_message_text(item: AgentMessageItem) -> str:
    if not isinstance(item, AgentMessageItem):
        raise TypeError("item must be an AgentMessageItem")
    return "".join(content.text for content in item.content)


def realtime_text_for_event(event: object) -> str | None:
    event_type, payload = _event_type_and_payload(event)
    if event_type == "agent_message":
        message = _payload_get(payload, "message")
        return message if isinstance(message, str) else None
    if event_type == "item_completed":
        item = _payload_get(payload, "item")
        if isinstance(item, TurnItem) and item.type == "AgentMessage":
            return agent_message_text(item.item)
        return None
    return None


def _strip_citations(text: str) -> str:
    _ensure_str(text, "text")
    visible: list[str] = []
    position = 0
    while True:
        start = text.find(CITATION_OPEN, position)
        if start == -1:
            visible.append(text[position:])
            break
        visible.append(text[position:start])
        content_start = start + len(CITATION_OPEN)
        end = text.find(CITATION_CLOSE, content_start)
        if end == -1:
            break
        position = end + len(CITATION_CLOSE)
    return "".join(visible)


def _citation_payloads(text: str) -> tuple[str, ...]:
    _ensure_str(text, "text")
    payloads: list[str] = []
    position = 0
    while True:
        start = text.find(CITATION_OPEN, position)
        if start == -1:
            break
        content_start = start + len(CITATION_OPEN)
        end = text.find(CITATION_CLOSE, content_start)
        if end == -1:
            break
        payloads.append(text[content_start:end])
        position = end + len(CITATION_CLOSE)
    return tuple(payloads)


def _tag_body(text: str, tag: str) -> str | None:
    open_tag = f"<{tag}>"
    close_tag = f"</{tag}>"
    start = text.find(open_tag)
    if start == -1:
        return None
    content_start = start + len(open_tag)
    end = text.find(close_tag, content_start)
    if end == -1:
        return None
    return text[content_start:end]


def _parse_memory_citation_entry(line: str) -> MemoryCitationEntry | None:
    stripped = line.strip()
    if not stripped or "|note=" not in stripped:
        return None
    location, note = stripped.split("|note=", 1)
    if ":" not in location or "-" not in location:
        return None
    path, span = location.rsplit(":", 1)
    line_start, line_end = span.split("-", 1)
    try:
        return MemoryCitationEntry(
            path=path,
            line_start=int(line_start),
            line_end=int(line_end),
            note=note,
        )
    except (TypeError, ValueError):
        return None


def _parse_memory_citation(payload: str) -> MemoryCitation | None:
    entries_body = _tag_body(payload, "citation_entries")
    if entries_body is None:
        return None
    entries = tuple(
        entry
        for entry in (_parse_memory_citation_entry(line) for line in entries_body.splitlines())
        if entry is not None
    )
    rollout_ids_body = _tag_body(payload, "rollout_ids")
    rollout_ids = tuple(
        line.strip()
        for line in (rollout_ids_body or "").splitlines()
        if line.strip()
    )
    if not entries and not rollout_ids:
        return None
    return MemoryCitation(entries=entries, rollout_ids=rollout_ids)


def memory_citation_from_response_item(item: ResponseItem) -> MemoryCitation | None:
    raw_text = raw_assistant_output_text_from_item(item)
    if raw_text is None:
        return None
    for payload in _citation_payloads(raw_text):
        citation = _parse_memory_citation(payload)
        if citation is not None:
            return citation
    return None


def _is_line_start(text: str, position: int) -> bool:
    _ensure_str(text, "text")
    _ensure_non_negative_int(position, "position")
    return position == 0 or text[position - 1] == "\n"


def _strip_proposed_plan_blocks(text: str) -> str:
    _ensure_str(text, "text")
    visible: list[str] = []
    position = 0
    while True:
        start = text.find(PROPOSED_PLAN_OPEN, position)
        while start != -1 and not _is_line_start(text, start):
            start = text.find(PROPOSED_PLAN_OPEN, start + len(PROPOSED_PLAN_OPEN))
        if start == -1:
            visible.append(text[position:])
            break

        visible.append(text[position:start])
        content_start = start + len(PROPOSED_PLAN_OPEN)
        if content_start < len(text) and text[content_start] not in {"\n", "\r"}:
            visible.append(PROPOSED_PLAN_OPEN)
            position = content_start
            continue

        end = text.find(PROPOSED_PLAN_CLOSE, content_start)
        if end == -1:
            break
        position = end + len(PROPOSED_PLAN_CLOSE)
        if position < len(text) and text[position] == "\r":
            position += 1
        if position < len(text) and text[position] == "\n":
            position += 1
    return "".join(visible)


def strip_hidden_assistant_markup(text: str, plan_mode: bool) -> str:
    _ensure_str(text, "text")
    _ensure_bool(plan_mode, "plan_mode")
    visible = _strip_citations(text)
    if plan_mode:
        visible = _strip_proposed_plan_blocks(visible)
    return visible


def last_assistant_message_from_item(
    item: ResponseItem,
    plan_mode: bool,
) -> str | None:
    _ensure_response_item(item)
    _ensure_bool(plan_mode, "plan_mode")
    combined = raw_assistant_output_text_from_item(item)
    if combined is None or combined == "":
        return None
    stripped = strip_hidden_assistant_markup(combined, plan_mode)
    if stripped.strip() == "":
        return None
    return stripped


def get_last_assistant_message_from_turn(responses: Sequence[ResponseItem]) -> str | None:
    if isinstance(responses, (str, bytes, ResponseItem)) or not isinstance(responses, Sequence):
        raise TypeError("responses must be a sequence of ResponseItem")
    if not all(isinstance(item, ResponseItem) for item in responses):
        raise TypeError("responses must contain ResponseItem values")
    for item in reversed(responses):
        message = last_assistant_message_from_item(item, plan_mode=False)
        if message is not None:
            return message
    return None


def response_item_may_include_external_context(item: ResponseItem) -> bool:
    _ensure_response_item(item)
    return item.type in {"tool_search_call", "tool_search_output", "web_search_call"}


def completed_item_defers_mailbox_delivery_to_next_turn(
    item: ResponseItem,
    plan_mode: bool,
) -> bool:
    _ensure_response_item(item)
    _ensure_bool(plan_mode, "plan_mode")
    if item.type == "message":
        if item.role != "assistant" or item.phase == MessagePhase.COMMENTARY:
            return False
        return last_assistant_message_from_item(item, plan_mode) is not None
    if item.type == "image_generation_call":
        return True
    return False


def response_input_to_response_item(input_item: ResponseInputItem) -> ResponseItem | None:
    if not isinstance(input_item, ResponseInputItem):
        raise TypeError("input_item must be a ResponseInputItem")
    if input_item.type in {
        "function_call_output",
        "custom_tool_call_output",
        "mcp_tool_call_output",
        "tool_search_output",
    }:
        return ResponseItem.from_response_input_item(input_item)
    return None


@dataclass(frozen=True)
class OutputItemResult:
    last_agent_message: str | None = None
    needs_follow_up: bool = False
    tool_future: object | None = None


@dataclass(frozen=True)
class SamplingOutputState:
    needs_follow_up: bool = False
    last_agent_message: str | None = None
    in_flight: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.needs_follow_up, bool):
            raise TypeError("needs_follow_up must be a bool")
        if self.last_agent_message is not None and not isinstance(self.last_agent_message, str):
            raise TypeError("last_agent_message must be a string or None")
        if not isinstance(self.in_flight, tuple):
            object.__setattr__(self, "in_flight", tuple(self.in_flight))


@dataclass(frozen=True)
class SamplingMailboxPreemptionPlan:
    needs_follow_up: bool
    last_agent_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.needs_follow_up, bool):
            raise TypeError("needs_follow_up must be a bool")
        if self.last_agent_message is not None and not isinstance(self.last_agent_message, str):
            raise TypeError("last_agent_message must be a string or None")


@dataclass(frozen=True)
class SamplingOutputItemAddedPlan:
    active_tool_argument_diff_consumer: tuple[str, object] | None = None
    reset_tool_argument_diff_consumer: bool = False
    active_item: TurnItem | None = None
    turn_item_to_emit: TurnItem | None = None
    active_item_is_streaming_to_client: bool = False
    seeded_item_id: str | None = None
    seeded_visible_text: str | None = None
    seeded_parsed: object | None = None
    seeded_raw_text: str | None = None

    def __post_init__(self) -> None:
        if self.active_tool_argument_diff_consumer is not None:
            if (
                not isinstance(self.active_tool_argument_diff_consumer, tuple)
                or len(self.active_tool_argument_diff_consumer) != 2
                or not isinstance(self.active_tool_argument_diff_consumer[0], str)
            ):
                raise TypeError("active_tool_argument_diff_consumer must be a (call_id, consumer) tuple or None")
        if not isinstance(self.reset_tool_argument_diff_consumer, bool):
            raise TypeError("reset_tool_argument_diff_consumer must be a bool")
        if self.active_item is not None and not isinstance(self.active_item, TurnItem):
            raise TypeError("active_item must be a TurnItem or None")
        if self.turn_item_to_emit is not None and not isinstance(self.turn_item_to_emit, TurnItem):
            raise TypeError("turn_item_to_emit must be a TurnItem or None")
        if not isinstance(self.active_item_is_streaming_to_client, bool):
            raise TypeError("active_item_is_streaming_to_client must be a bool")
        if self.seeded_item_id is not None and not isinstance(self.seeded_item_id, str):
            raise TypeError("seeded_item_id must be a string or None")
        if self.seeded_visible_text is not None and not isinstance(self.seeded_visible_text, str):
            raise TypeError("seeded_visible_text must be a string or None")
        if self.seeded_raw_text is not None and not isinstance(self.seeded_raw_text, str):
            raise TypeError("seeded_raw_text must be a string or None")


@dataclass(frozen=True)
class SamplingOutputItemAddedApplyPlan:
    active_tool_argument_diff_consumer_after: tuple[str, object] | None = None
    should_reset_tool_argument_diff_consumer: bool = False
    pending_agent_message_item: TurnItem | None = None
    turn_item_started_to_emit: TurnItem | None = None
    seeded_streamed_assistant_text_plan: SamplingStreamedAssistantTextDeltaPlan | None = None
    active_item_after: TurnItem | None = None
    active_item_is_streaming_to_client_after: bool = False

    def __post_init__(self) -> None:
        if self.active_tool_argument_diff_consumer_after is not None:
            if (
                not isinstance(self.active_tool_argument_diff_consumer_after, tuple)
                or len(self.active_tool_argument_diff_consumer_after) != 2
                or not isinstance(self.active_tool_argument_diff_consumer_after[0], str)
            ):
                raise TypeError(
                    "active_tool_argument_diff_consumer_after must be a (call_id, consumer) tuple or None"
                )
        _ensure_bool(self.should_reset_tool_argument_diff_consumer, "should_reset_tool_argument_diff_consumer")
        if self.pending_agent_message_item is not None and not isinstance(self.pending_agent_message_item, TurnItem):
            raise TypeError("pending_agent_message_item must be a TurnItem or None")
        if self.turn_item_started_to_emit is not None and not isinstance(self.turn_item_started_to_emit, TurnItem):
            raise TypeError("turn_item_started_to_emit must be a TurnItem or None")
        if self.seeded_streamed_assistant_text_plan is not None and not isinstance(
            self.seeded_streamed_assistant_text_plan,
            SamplingStreamedAssistantTextDeltaPlan,
        ):
            raise TypeError("seeded_streamed_assistant_text_plan must be SamplingStreamedAssistantTextDeltaPlan")
        if self.active_item_after is not None and not isinstance(self.active_item_after, TurnItem):
            raise TypeError("active_item_after must be a TurnItem or None")
        _ensure_bool(
            self.active_item_is_streaming_to_client_after,
            "active_item_is_streaming_to_client_after",
        )


@dataclass(frozen=True)
class SamplingOutputTextDeltaPlan:
    item_id: str
    delta: str
    parsed: object | None = None
    raw_content_delta: str | None = None
    thread_id: str = ""
    turn_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str):
            raise TypeError("item_id must be a string")
        if not isinstance(self.delta, str):
            raise TypeError("delta must be a string")
        if self.raw_content_delta is not None and not isinstance(self.raw_content_delta, str):
            raise TypeError("raw_content_delta must be a string or None")
        _ensure_str(self.thread_id, "thread_id")
        _ensure_str(self.turn_id, "turn_id")


@dataclass(frozen=True)
class SamplingAssistantTextFlushPlan:
    item_id: str
    parsed: object

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str):
            raise TypeError("item_id must be a string")


@dataclass(frozen=True)
class SamplingAssistantTextFlushAllPlan:
    item_plans: tuple[SamplingAssistantTextFlushPlan, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.item_plans, tuple):
            object.__setattr__(self, "item_plans", tuple(self.item_plans))
        for item_plan in self.item_plans:
            if not isinstance(item_plan, SamplingAssistantTextFlushPlan):
                raise TypeError("item_plans must contain SamplingAssistantTextFlushPlan values")


@dataclass(frozen=True)
class SamplingStreamedAssistantTextDeltaPlan:
    item_id: str
    visible_text_delta: str | None = None
    plan_segments_plan: object | None = None
    citations: tuple[str, ...] = ()
    ignored_citations: bool = False
    thread_id: str = ""
    turn_id: str = ""

    def __post_init__(self) -> None:
        _ensure_str(self.item_id, "item_id")
        if self.visible_text_delta is not None:
            _ensure_str(self.visible_text_delta, "visible_text_delta")
        if not isinstance(self.citations, tuple):
            object.__setattr__(self, "citations", tuple(self.citations))
        for citation in self.citations:
            _ensure_str(citation, "citations item")
        _ensure_bool(self.ignored_citations, "ignored_citations")
        _ensure_str(self.thread_id, "thread_id")
        _ensure_str(self.turn_id, "turn_id")


@dataclass(frozen=True)
class SamplingOutputTextDeltaApplyPlan:
    item_id: str
    streamed_assistant_text_plan: SamplingStreamedAssistantTextDeltaPlan | None = None
    raw_content_delta: str | None = None
    thread_id: str = ""
    turn_id: str = ""

    def __post_init__(self) -> None:
        _ensure_str(self.item_id, "item_id")
        if self.streamed_assistant_text_plan is not None and not isinstance(
            self.streamed_assistant_text_plan,
            SamplingStreamedAssistantTextDeltaPlan,
        ):
            raise TypeError("streamed_assistant_text_plan must be SamplingStreamedAssistantTextDeltaPlan or None")
        if self.raw_content_delta is not None:
            _ensure_str(self.raw_content_delta, "raw_content_delta")
        _ensure_str(self.thread_id, "thread_id")
        _ensure_str(self.turn_id, "turn_id")


@dataclass(frozen=True)
class SamplingOutputItemDoneTransitionPlan:
    previously_active_item: TurnItem | None = None
    previously_streamed_item: TurnItem | None = None
    active_item_after: TurnItem | None = None
    active_item_is_streaming_to_client_after: bool = False
    finished_tool_input_event: object | None = None
    assistant_text_flush_plan: SamplingAssistantTextFlushPlan | None = None
    thread_id: str = ""
    turn_id: str = ""

    def __post_init__(self) -> None:
        if self.previously_active_item is not None and not isinstance(self.previously_active_item, TurnItem):
            raise TypeError("previously_active_item must be a TurnItem or None")
        if self.previously_streamed_item is not None and not isinstance(self.previously_streamed_item, TurnItem):
            raise TypeError("previously_streamed_item must be a TurnItem or None")
        if self.active_item_after is not None and not isinstance(self.active_item_after, TurnItem):
            raise TypeError("active_item_after must be a TurnItem or None")
        if not isinstance(self.active_item_is_streaming_to_client_after, bool):
            raise TypeError("active_item_is_streaming_to_client_after must be a bool")
        if self.assistant_text_flush_plan is not None and not isinstance(
            self.assistant_text_flush_plan,
            SamplingAssistantTextFlushPlan,
        ):
            raise TypeError("assistant_text_flush_plan must be a SamplingAssistantTextFlushPlan or None")
        _ensure_str(self.thread_id, "thread_id")
        _ensure_str(self.turn_id, "turn_id")


@dataclass(frozen=True)
class SamplingOutputItemDoneApplyPlan:
    transition_plan: SamplingOutputItemDoneTransitionPlan
    streamed_assistant_text_plan: SamplingStreamedAssistantTextDeltaPlan | None = None
    plan_mode_assistant_done_plan: SamplingPlanModeAssistantDonePlan | None = None
    should_continue_loop: bool = False
    preempt_for_mailbox_mail: bool = False
    output_result: OutputItemResult | None = None
    state_after_output_result: SamplingOutputState | None = None
    mailbox_preemption_plan: SamplingMailboxPreemptionPlan | None = None
    completed_item: ResponseItem | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.transition_plan, SamplingOutputItemDoneTransitionPlan):
            raise TypeError("transition_plan must be a SamplingOutputItemDoneTransitionPlan")
        if self.streamed_assistant_text_plan is not None and not isinstance(
            self.streamed_assistant_text_plan,
            SamplingStreamedAssistantTextDeltaPlan,
        ):
            raise TypeError("streamed_assistant_text_plan must be SamplingStreamedAssistantTextDeltaPlan or None")
        if self.plan_mode_assistant_done_plan is not None and not isinstance(
            self.plan_mode_assistant_done_plan,
            SamplingPlanModeAssistantDonePlan,
        ):
            raise TypeError("plan_mode_assistant_done_plan must be SamplingPlanModeAssistantDonePlan or None")
        _ensure_bool(self.should_continue_loop, "should_continue_loop")
        _ensure_bool(self.preempt_for_mailbox_mail, "preempt_for_mailbox_mail")
        if self.output_result is not None and not isinstance(self.output_result, OutputItemResult):
            raise TypeError("output_result must be an OutputItemResult or None")
        if self.state_after_output_result is not None and not isinstance(
            self.state_after_output_result,
            SamplingOutputState,
        ):
            raise TypeError("state_after_output_result must be SamplingOutputState or None")
        if self.mailbox_preemption_plan is not None and not isinstance(
            self.mailbox_preemption_plan,
            SamplingMailboxPreemptionPlan,
        ):
            raise TypeError("mailbox_preemption_plan must be SamplingMailboxPreemptionPlan or None")
        if self.completed_item is not None:
            _ensure_response_item(self.completed_item)


@dataclass(frozen=True)
class SamplingMetadataEventPlan:
    event_type: str
    payload: object
    should_maybe_warn_server_model_mismatch: bool = False
    should_mark_server_model_warning_if_emitted: bool = False
    should_emit_model_verification: bool = False
    should_mark_model_verification_emitted: bool = False
    should_set_server_reasoning_included: bool = False
    should_record_rate_limits: bool = False
    should_emit_token_count: bool = False
    should_refresh_models_etag: bool = False

    def __post_init__(self) -> None:
        _ensure_str(self.event_type, "event_type")
        for field_name in (
            "should_maybe_warn_server_model_mismatch",
            "should_mark_server_model_warning_if_emitted",
            "should_emit_model_verification",
            "should_mark_model_verification_emitted",
            "should_set_server_reasoning_included",
            "should_record_rate_limits",
            "should_emit_token_count",
            "should_refresh_models_etag",
        ):
            _ensure_bool(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class SamplingMetadataEventApplyPlan:
    event_type: str
    server_model_to_check: str | None = None
    should_mark_server_model_warning_if_emitted: bool = False
    model_verification_to_emit: object | None = None
    should_mark_model_verification_emitted: bool = False
    server_reasoning_included: bool | None = None
    rate_limits_to_record: object | None = None
    models_etag_to_refresh: str | None = None
    should_emit_token_count: bool = False

    def __post_init__(self) -> None:
        _ensure_str(self.event_type, "event_type")
        if self.server_model_to_check is not None:
            _ensure_str(self.server_model_to_check, "server_model_to_check")
        _ensure_bool(
            self.should_mark_server_model_warning_if_emitted,
            "should_mark_server_model_warning_if_emitted",
        )
        _ensure_bool(self.should_mark_model_verification_emitted, "should_mark_model_verification_emitted")
        if self.server_reasoning_included is not None:
            _ensure_bool(self.server_reasoning_included, "server_reasoning_included")
        if self.models_etag_to_refresh is not None:
            _ensure_str(self.models_etag_to_refresh, "models_etag_to_refresh")
        _ensure_bool(self.should_emit_token_count, "should_emit_token_count")


@dataclass(frozen=True)
class SamplingCompletedEventPlan:
    response_id: str
    token_usage: object | None
    needs_follow_up: bool
    last_agent_message: str | None = None
    completed_response_id: str | None = None
    should_flush_assistant_text_segments_all: bool = True
    should_record_token_usage: bool = True
    should_emit_token_count: bool = True
    should_emit_turn_diff: bool = True
    thread_id: str = ""
    turn_id: str = ""

    def __post_init__(self) -> None:
        _ensure_str(self.response_id, "response_id")
        if self.last_agent_message is not None:
            _ensure_str(self.last_agent_message, "last_agent_message")
        if self.completed_response_id is not None:
            _ensure_str(self.completed_response_id, "completed_response_id")
        for field_name in (
            "needs_follow_up",
            "should_flush_assistant_text_segments_all",
            "should_record_token_usage",
            "should_emit_token_count",
            "should_emit_turn_diff",
        ):
            _ensure_bool(getattr(self, field_name), field_name)
        _ensure_str(self.thread_id, "thread_id")
        _ensure_str(self.turn_id, "turn_id")


@dataclass(frozen=True)
class SamplingCompletedEventApplyPlan:
    response_id: str
    flush_all_plan: SamplingAssistantTextFlushAllPlan | None = None
    token_usage_to_record: object | None = None
    should_record_token_usage: bool = True
    should_emit_token_count: bool = True
    should_emit_turn_diff: bool = True
    completed_response_id_after: str | None = None
    result_needs_follow_up: bool = False
    result_last_agent_message: str | None = None
    thread_id: str = ""
    turn_id: str = ""

    def __post_init__(self) -> None:
        _ensure_str(self.response_id, "response_id")
        if self.flush_all_plan is not None and not isinstance(
            self.flush_all_plan,
            SamplingAssistantTextFlushAllPlan,
        ):
            raise TypeError("flush_all_plan must be SamplingAssistantTextFlushAllPlan or None")
        _ensure_bool(self.should_record_token_usage, "should_record_token_usage")
        _ensure_bool(self.should_emit_token_count, "should_emit_token_count")
        _ensure_bool(self.should_emit_turn_diff, "should_emit_turn_diff")
        if self.completed_response_id_after is not None:
            _ensure_str(self.completed_response_id_after, "completed_response_id_after")
        _ensure_bool(self.result_needs_follow_up, "result_needs_follow_up")
        _ensure_str(self.thread_id, "thread_id")
        _ensure_str(self.turn_id, "turn_id")
        if self.result_last_agent_message is not None:
            _ensure_str(self.result_last_agent_message, "result_last_agent_message")


@dataclass(frozen=True)
class SamplingStreamEventDispatchPlan:
    event_type: str
    no_op: bool = False
    output_item_done_transition_plan: SamplingOutputItemDoneTransitionPlan | None = None
    output_item_added_plan: SamplingOutputItemAddedPlan | None = None
    output_text_delta_plan: SamplingOutputTextDeltaPlan | None = None
    tool_call_input_delta_plan: SamplingToolCallInputDeltaPlan | None = None
    reasoning_delta_plan: SamplingReasoningDeltaPlan | None = None
    completed_event_plan: SamplingCompletedEventPlan | None = None
    metadata_event_plan: SamplingMetadataEventPlan | None = None

    def __post_init__(self) -> None:
        _ensure_str(self.event_type, "event_type")
        _ensure_bool(self.no_op, "no_op")
        if self.output_item_done_transition_plan is not None and not isinstance(
            self.output_item_done_transition_plan,
            SamplingOutputItemDoneTransitionPlan,
        ):
            raise TypeError("output_item_done_transition_plan must be SamplingOutputItemDoneTransitionPlan or None")
        if self.output_item_added_plan is not None and not isinstance(
            self.output_item_added_plan,
            SamplingOutputItemAddedPlan,
        ):
            raise TypeError("output_item_added_plan must be SamplingOutputItemAddedPlan or None")
        if self.output_text_delta_plan is not None and not isinstance(
            self.output_text_delta_plan,
            SamplingOutputTextDeltaPlan,
        ):
            raise TypeError("output_text_delta_plan must be SamplingOutputTextDeltaPlan or None")
        if self.tool_call_input_delta_plan is not None and not isinstance(
            self.tool_call_input_delta_plan,
            SamplingToolCallInputDeltaPlan,
        ):
            raise TypeError("tool_call_input_delta_plan must be SamplingToolCallInputDeltaPlan or None")
        if self.reasoning_delta_plan is not None and not isinstance(
            self.reasoning_delta_plan,
            SamplingReasoningDeltaPlan,
        ):
            raise TypeError("reasoning_delta_plan must be SamplingReasoningDeltaPlan or None")
        if self.completed_event_plan is not None and not isinstance(
            self.completed_event_plan,
            SamplingCompletedEventPlan,
        ):
            raise TypeError("completed_event_plan must be SamplingCompletedEventPlan or None")
        if self.metadata_event_plan is not None and not isinstance(
            self.metadata_event_plan,
            SamplingMetadataEventPlan,
        ):
            raise TypeError("metadata_event_plan must be SamplingMetadataEventPlan or None")


@dataclass(frozen=True)
class SamplingStreamEventApplyPlan:
    event_type: str
    no_op: bool = False
    output_item_done_apply_plan: SamplingOutputItemDoneApplyPlan | None = None
    output_item_added_apply_plan: SamplingOutputItemAddedApplyPlan | None = None
    output_text_delta_apply_plan: SamplingOutputTextDeltaApplyPlan | None = None
    tool_call_input_delta_apply_plan: SamplingToolCallInputDeltaApplyPlan | None = None
    reasoning_delta_apply_plan: SamplingReasoningDeltaApplyPlan | None = None
    completed_event_apply_plan: SamplingCompletedEventApplyPlan | None = None
    metadata_event_apply_plan: SamplingMetadataEventApplyPlan | None = None

    def __post_init__(self) -> None:
        _ensure_str(self.event_type, "event_type")
        _ensure_bool(self.no_op, "no_op")
        if self.output_item_done_apply_plan is not None and not isinstance(
            self.output_item_done_apply_plan,
            SamplingOutputItemDoneApplyPlan,
        ):
            raise TypeError("output_item_done_apply_plan must be SamplingOutputItemDoneApplyPlan or None")
        if self.output_item_added_apply_plan is not None and not isinstance(
            self.output_item_added_apply_plan,
            SamplingOutputItemAddedApplyPlan,
        ):
            raise TypeError("output_item_added_apply_plan must be SamplingOutputItemAddedApplyPlan or None")
        if self.output_text_delta_apply_plan is not None and not isinstance(
            self.output_text_delta_apply_plan,
            SamplingOutputTextDeltaApplyPlan,
        ):
            raise TypeError("output_text_delta_apply_plan must be SamplingOutputTextDeltaApplyPlan or None")
        if self.tool_call_input_delta_apply_plan is not None and not isinstance(
            self.tool_call_input_delta_apply_plan,
            SamplingToolCallInputDeltaApplyPlan,
        ):
            raise TypeError("tool_call_input_delta_apply_plan must be SamplingToolCallInputDeltaApplyPlan or None")
        if self.reasoning_delta_apply_plan is not None and not isinstance(
            self.reasoning_delta_apply_plan,
            SamplingReasoningDeltaApplyPlan,
        ):
            raise TypeError("reasoning_delta_apply_plan must be SamplingReasoningDeltaApplyPlan or None")
        if self.completed_event_apply_plan is not None and not isinstance(
            self.completed_event_apply_plan,
            SamplingCompletedEventApplyPlan,
        ):
            raise TypeError("completed_event_apply_plan must be SamplingCompletedEventApplyPlan or None")
        if self.metadata_event_apply_plan is not None and not isinstance(
            self.metadata_event_apply_plan,
            SamplingMetadataEventApplyPlan,
        ):
            raise TypeError("metadata_event_apply_plan must be SamplingMetadataEventApplyPlan or None")


@dataclass(frozen=True)
class SamplingPlanModeAssistantDonePlan:
    handled: bool
    should_continue_loop: bool = False
    should_complete_plan_item_from_message: bool = False
    proposed_plan_completion_plan: SamplingProposedPlanCompletionPlan | None = None
    finalized_turn_item: FinalizedTurnItem | None = None
    turn_item_emit_plan: SamplingPlanModeTurnItemEmitPlan | None = None
    recording_plan: CompletedResponseItemRecordingPlan | None = None
    last_agent_message: str | None = None
    should_update_last_agent_message: bool = False
    should_emit_agent_message_started_if_needed: bool = False
    should_emit_agent_message_completed: bool = False
    should_drop_empty_agent_message: bool = False
    previously_active_item: TurnItem | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "handled",
            "should_continue_loop",
            "should_complete_plan_item_from_message",
            "should_update_last_agent_message",
            "should_emit_agent_message_started_if_needed",
            "should_emit_agent_message_completed",
            "should_drop_empty_agent_message",
        ):
            _ensure_bool(getattr(self, field_name), field_name)
        if self.proposed_plan_completion_plan is not None and not isinstance(
            self.proposed_plan_completion_plan,
            SamplingProposedPlanCompletionPlan,
        ):
            raise TypeError("proposed_plan_completion_plan must be a SamplingProposedPlanCompletionPlan or None")
        if self.finalized_turn_item is not None and not isinstance(self.finalized_turn_item, FinalizedTurnItem):
            raise TypeError("finalized_turn_item must be a FinalizedTurnItem or None")
        if self.turn_item_emit_plan is not None and not isinstance(
            self.turn_item_emit_plan,
            SamplingPlanModeTurnItemEmitPlan,
        ):
            raise TypeError("turn_item_emit_plan must be a SamplingPlanModeTurnItemEmitPlan or None")
        if self.recording_plan is not None and not isinstance(self.recording_plan, CompletedResponseItemRecordingPlan):
            raise TypeError("recording_plan must be a CompletedResponseItemRecordingPlan or None")
        if self.last_agent_message is not None:
            _ensure_str(self.last_agent_message, "last_agent_message")
        if self.previously_active_item is not None and not isinstance(self.previously_active_item, TurnItem):
            raise TypeError("previously_active_item must be a TurnItem or None")


@dataclass(frozen=True)
class SamplingPlanSegmentAction:
    action_type: str
    item_id: str
    delta: str | None = None

    def __post_init__(self) -> None:
        _ensure_str(self.action_type, "action_type")
        _ensure_str(self.item_id, "item_id")
        if self.delta is not None:
            _ensure_str(self.delta, "delta")


@dataclass(frozen=True)
class SamplingPlanSegmentsPlan:
    actions: tuple[SamplingPlanSegmentAction, ...] = ()
    leading_whitespace_by_item_after: tuple[tuple[str, str], ...] = ()
    plan_item_started_after: bool = False
    plan_item_completed_after: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.actions, tuple):
            object.__setattr__(self, "actions", tuple(self.actions))
        for action in self.actions:
            if not isinstance(action, SamplingPlanSegmentAction):
                raise TypeError("actions must contain SamplingPlanSegmentAction values")
        if not isinstance(self.leading_whitespace_by_item_after, tuple):
            object.__setattr__(
                self,
                "leading_whitespace_by_item_after",
                tuple(self.leading_whitespace_by_item_after),
            )
        for item_id, whitespace in self.leading_whitespace_by_item_after:
            _ensure_str(item_id, "leading whitespace item id")
            _ensure_str(whitespace, "leading whitespace")
        _ensure_bool(self.plan_item_started_after, "plan_item_started_after")
        _ensure_bool(self.plan_item_completed_after, "plan_item_completed_after")


@dataclass(frozen=True)
class SamplingProposedPlanCompletionPlan:
    plan_item_id: str
    plan_text: str
    should_start_plan_item: bool = False
    should_complete_plan_item: bool = True
    plan_item_started_after: bool = True
    plan_item_completed_after: bool = True

    def __post_init__(self) -> None:
        _ensure_str(self.plan_item_id, "plan_item_id")
        _ensure_str(self.plan_text, "plan_text")
        for field_name in (
            "should_start_plan_item",
            "should_complete_plan_item",
            "plan_item_started_after",
            "plan_item_completed_after",
        ):
            _ensure_bool(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class SamplingPendingAgentMessageStartPlan:
    item_id: str
    turn_item_to_start: TurnItem | None = None
    started_agent_message_item_ids_after: tuple[str, ...] = ()
    pending_agent_message_item_ids_after: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_str(self.item_id, "item_id")
        if self.turn_item_to_start is not None and not isinstance(self.turn_item_to_start, TurnItem):
            raise TypeError("turn_item_to_start must be a TurnItem or None")
        if not isinstance(self.started_agent_message_item_ids_after, tuple):
            object.__setattr__(
                self,
                "started_agent_message_item_ids_after",
                tuple(self.started_agent_message_item_ids_after),
            )
        if not isinstance(self.pending_agent_message_item_ids_after, tuple):
            object.__setattr__(
                self,
                "pending_agent_message_item_ids_after",
                tuple(self.pending_agent_message_item_ids_after),
            )
        for value in self.started_agent_message_item_ids_after:
            _ensure_str(value, "started_agent_message_item_ids_after")
        for value in self.pending_agent_message_item_ids_after:
            _ensure_str(value, "pending_agent_message_item_ids_after")


@dataclass(frozen=True)
class SamplingPlanModeAgentMessageEmitPlan:
    item_id: str
    text: str
    should_drop_empty_agent_message: bool = False
    pending_start_plan: SamplingPendingAgentMessageStartPlan | None = None
    fallback_start_item: TurnItem | None = None
    should_emit_completed: bool = False
    started_agent_message_item_ids_after: tuple[str, ...] = ()
    pending_agent_message_item_ids_after: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_str(self.item_id, "item_id")
        _ensure_str(self.text, "text")
        _ensure_bool(self.should_drop_empty_agent_message, "should_drop_empty_agent_message")
        if self.pending_start_plan is not None and not isinstance(
            self.pending_start_plan,
            SamplingPendingAgentMessageStartPlan,
        ):
            raise TypeError("pending_start_plan must be a SamplingPendingAgentMessageStartPlan or None")
        if self.fallback_start_item is not None and not isinstance(self.fallback_start_item, TurnItem):
            raise TypeError("fallback_start_item must be a TurnItem or None")
        _ensure_bool(self.should_emit_completed, "should_emit_completed")
        if not isinstance(self.started_agent_message_item_ids_after, tuple):
            object.__setattr__(
                self,
                "started_agent_message_item_ids_after",
                tuple(self.started_agent_message_item_ids_after),
            )
        if not isinstance(self.pending_agent_message_item_ids_after, tuple):
            object.__setattr__(
                self,
                "pending_agent_message_item_ids_after",
                tuple(self.pending_agent_message_item_ids_after),
            )
        for value in self.started_agent_message_item_ids_after:
            _ensure_str(value, "started_agent_message_item_ids_after")
        for value in self.pending_agent_message_item_ids_after:
            _ensure_str(value, "pending_agent_message_item_ids_after")


@dataclass(frozen=True)
class SamplingPlanModeTurnItemEmitPlan:
    turn_item: TurnItem
    agent_message_plan: SamplingPlanModeAgentMessageEmitPlan | None = None
    should_emit_started: bool = False
    should_emit_completed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.turn_item, TurnItem):
            raise TypeError("turn_item must be a TurnItem")
        if self.agent_message_plan is not None and not isinstance(
            self.agent_message_plan,
            SamplingPlanModeAgentMessageEmitPlan,
        ):
            raise TypeError("agent_message_plan must be a SamplingPlanModeAgentMessageEmitPlan or None")
        _ensure_bool(self.should_emit_started, "should_emit_started")
        _ensure_bool(self.should_emit_completed, "should_emit_completed")


@dataclass(frozen=True)
class SamplingInFlightToolResultPlan:
    response_item: ResponseItem | None = None
    should_record_conversation_item: bool = False
    should_mark_thread_memory_mode_polluted: bool = False
    error_message: str | None = None
    should_error_or_panic: bool = False

    def __post_init__(self) -> None:
        if self.response_item is not None and not isinstance(self.response_item, ResponseItem):
            raise TypeError("response_item must be a ResponseItem or None")
        _ensure_bool(self.should_record_conversation_item, "should_record_conversation_item")
        _ensure_bool(self.should_mark_thread_memory_mode_polluted, "should_mark_thread_memory_mode_polluted")
        if self.error_message is not None:
            _ensure_str(self.error_message, "error_message")
        _ensure_bool(self.should_error_or_panic, "should_error_or_panic")


@dataclass(frozen=True)
class SamplingToolCallInputDeltaPlan:
    call_id: str
    delta: str
    event: object | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.delta, str):
            raise TypeError("delta must be a string")


@dataclass(frozen=True)
class SamplingToolCallInputDeltaApplyPlan:
    call_id: str
    delta: str
    event_to_emit: object | None = None
    should_send_event: bool = False

    def __post_init__(self) -> None:
        _ensure_str(self.call_id, "call_id")
        _ensure_str(self.delta, "delta")
        _ensure_bool(self.should_send_event, "should_send_event")


@dataclass(frozen=True)
class SamplingReasoningDeltaPlan:
    event_type: str
    item_id: str
    delta: str | None = None
    summary_index: int | None = None
    content_index: int | None = None
    thread_id: str = ""
    turn_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, str):
            raise TypeError("event_type must be a string")
        if not isinstance(self.item_id, str):
            raise TypeError("item_id must be a string")
        if self.delta is not None and not isinstance(self.delta, str):
            raise TypeError("delta must be a string or None")
        if self.summary_index is not None:
            _ensure_non_negative_int(self.summary_index, "summary_index")
        if self.content_index is not None:
            _ensure_non_negative_int(self.content_index, "content_index")
        _ensure_str(self.thread_id, "thread_id")
        _ensure_str(self.turn_id, "turn_id")


@dataclass(frozen=True)
class SamplingReasoningDeltaApplyPlan:
    event_type: str
    item_id: str
    event_to_emit: object

    def __post_init__(self) -> None:
        _ensure_str(self.event_type, "event_type")
        _ensure_str(self.item_id, "item_id")
        if not isinstance(self.event_to_emit, dict):
            raise TypeError("event_to_emit must be a dict")


@dataclass(frozen=True)
class ToolCallLifecyclePlan:
    tool_name: str
    payload_preview: str | None
    thread_id: str | None = None
    accepts_mailbox_delivery_for_current_turn: bool = True
    records_completed_response_item: bool = True
    needs_follow_up: bool = True


@dataclass(frozen=True)
class ToolCallErrorHandlingPlan:
    response_item: ResponseItem | None = None
    needs_follow_up: bool = False
    fatal_message: str | None = None
    records_completed_response_item: bool = True
    records_model_visible_response: bool = False


@dataclass(frozen=True)
class UnexpectedToolOutputPlan:
    item_type: str
    records_completed_response_item: bool = True
    emits_turn_item: bool = False
    needs_follow_up: bool = False


@dataclass(frozen=True)
class HandleOutputCtx:
    sess: object
    turn_context: object
    turn_store: object | None = None
    tool_runtime: object | None = None
    cancellation_token: object | None = None


@dataclass(frozen=True)
class FinalizedTurnItemFacts:
    memory_citation: object | None = None
    last_agent_message: str | None = None
    defers_mailbox_delivery_to_next_turn: bool = False


@dataclass(frozen=True)
class FinalizedTurnItem:
    turn_item: TurnItem
    facts: FinalizedTurnItemFacts


@dataclass(frozen=True)
class CompletedResponseItemRecordingPlan:
    defer_mailbox_delivery_to_next_turn: bool = False
    mark_thread_memory_mode_polluted: bool = False
    memory_citation: object | None = None


def completed_response_item_recording_plan(
    item: ResponseItem,
    plan_mode: bool,
    finalized_facts: FinalizedTurnItemFacts | None = None,
    *,
    memories_disable_on_external_context: bool = False,
) -> CompletedResponseItemRecordingPlan:
    _ensure_response_item(item)
    _ensure_bool(plan_mode, "plan_mode")
    _ensure_bool(memories_disable_on_external_context, "memories_disable_on_external_context")
    if finalized_facts is not None and not isinstance(finalized_facts, FinalizedTurnItemFacts):
        raise TypeError("finalized_facts must be FinalizedTurnItemFacts or None")

    if finalized_facts is None:
        defer_mailbox = completed_item_defers_mailbox_delivery_to_next_turn(item, plan_mode)
        memory_citation = memory_citation_from_response_item(item)
    else:
        defer_mailbox = finalized_facts.defers_mailbox_delivery_to_next_turn
        memory_citation = finalized_facts.memory_citation

    return CompletedResponseItemRecordingPlan(
        defer_mailbox_delivery_to_next_turn=defer_mailbox,
        mark_thread_memory_mode_polluted=memories_disable_on_external_context
        and response_item_may_include_external_context(item),
        memory_citation=memory_citation,
    )


def tool_call_lifecycle_plan(call: ToolCall, thread_id: object | None = None) -> ToolCallLifecyclePlan:
    if not isinstance(call, ToolCall):
        raise TypeError("call must be a ToolCall")
    payload_preview = call.payload.log_payload()
    if payload_preview is not None and not isinstance(payload_preview, str):
        payload_preview = str(payload_preview)
    return ToolCallLifecyclePlan(
        tool_name=str(call.tool_name),
        payload_preview=payload_preview,
        thread_id=None if thread_id is None else str(thread_id),
    )


def tool_call_error_handling_plan(error: FunctionCallError) -> ToolCallErrorHandlingPlan:
    if not isinstance(error, FunctionCallError):
        raise TypeError("error must be a FunctionCallError")
    if error.is_fatal:
        return ToolCallErrorHandlingPlan(fatal_message=error.message)
    _, response_item = function_call_error_output_result(error)
    return ToolCallErrorHandlingPlan(
        response_item=response_item,
        needs_follow_up=True,
        records_model_visible_response=True,
    )


def unexpected_tool_output_plan(item: ResponseItem) -> UnexpectedToolOutputPlan | None:
    _ensure_response_item(item)
    if item.type not in {"function_call_output", "custom_tool_call_output", "tool_search_output"}:
        return None
    return UnexpectedToolOutputPlan(item_type=item.type)


def finalize_non_tool_response_item(
    item: ResponseItem,
    plan_mode: bool,
) -> FinalizedTurnItem | None:
    """Convert a non-tool response item into a finalized turn item plus facts."""

    turn_item = handle_non_tool_response_item(item, plan_mode)
    if turn_item is None:
        return None
    return _finalized_turn_item_from_turn_item(turn_item)


async def finalize_non_tool_response_item_with_contributors(
    sess: object,
    turn_context: object,
    turn_store: object | None,
    item: ResponseItem,
    plan_mode: bool,
) -> FinalizedTurnItem | None:
    """Convert a non-tool response item, running Rust-style turn-item contributors first."""

    turn_item = await handle_non_tool_response_item_with_contributors(
        sess,
        turn_context,
        turn_store,
        item,
        plan_mode,
    )
    if turn_item is None:
        return None
    return _finalized_turn_item_from_turn_item(turn_item)


def _finalized_turn_item_from_turn_item(turn_item: TurnItem) -> FinalizedTurnItem:
    return FinalizedTurnItem(
        turn_item=turn_item,
        facts=finalized_turn_item_facts(turn_item),
    )


def handle_non_tool_response_item(item: ResponseItem, plan_mode: bool) -> TurnItem | None:
    """Parse and normalize a non-tool response item."""

    turn_item = _parse_non_tool_response_item(item, plan_mode)
    if turn_item is None:
        return None
    return _normalize_non_tool_turn_item(turn_item, plan_mode)


async def handle_non_tool_response_item_with_contributors(
    sess: object,
    turn_context: object,
    turn_store: object | None,
    item: ResponseItem,
    plan_mode: bool,
) -> TurnItem | None:
    """Parse a non-tool response item, run contributors, then normalize hidden markup."""

    turn_item = _parse_non_tool_response_item(item, plan_mode)
    if turn_item is None:
        return None
    turn_item = await apply_turn_item_contributors(sess, turn_store, turn_item)
    turn_item = _normalize_non_tool_turn_item(turn_item, plan_mode)
    if turn_item.type == "ImageGeneration":
        turn_item = await _apply_image_generation_artifact_side_effects(sess, turn_context, turn_item)
    return turn_item


async def apply_turn_item_contributors(sess: object, turn_store: object | None, item: TurnItem) -> TurnItem:
    if not isinstance(item, TurnItem):
        raise TypeError("item must be a TurnItem")
    current = item
    thread_extension_data = _thread_extension_data(sess)
    for contributor in _turn_item_contributors(sess):
        try:
            result = await _maybe_await(_run_turn_item_contributor(contributor, thread_extension_data, turn_store, current))
        except Exception:
            continue
        if isinstance(result, TurnItem):
            current = result
    return current


def _parse_non_tool_response_item(item: ResponseItem, plan_mode: bool) -> TurnItem | None:
    _ensure_response_item(item)
    _ensure_bool(plan_mode, "plan_mode")
    if item.type not in {"message", "reasoning", "web_search_call", "image_generation_call"}:
        return None
    turn_item = parse_turn_item(item)
    if turn_item is None:
        return None
    return turn_item


def _normalize_non_tool_turn_item(turn_item: TurnItem, plan_mode: bool) -> TurnItem:
    if not isinstance(turn_item, TurnItem):
        raise TypeError("turn_item must be a TurnItem")
    _ensure_bool(plan_mode, "plan_mode")
    if turn_item.type == "AgentMessage":
        agent_message = turn_item.item
        combined = "".join(content.text for content in agent_message.content)
        stripped = strip_hidden_assistant_markup(combined, plan_mode)
        return TurnItem.agent_message(
            AgentMessageItem(
                id=agent_message.id,
                content=(AgentMessageContent.text_content(stripped),),
                phase=agent_message.phase,
                memory_citation=agent_message.memory_citation,
            )
        )
    return turn_item


async def _apply_image_generation_artifact_side_effects(
    sess: object,
    turn_context: object,
    turn_item: TurnItem,
) -> TurnItem:
    image_item = turn_item.item
    if not isinstance(image_item, ImageGenerationItem):
        return turn_item
    config = getattr(turn_context, "config", None)
    codex_home = getattr(config, "codex_home", None)
    session_id = str(getattr(sess, "conversation_id", ""))
    if codex_home is None:
        return turn_item
    try:
        saved_path = save_image_generation_result(codex_home, session_id, image_item.id, image_item.result)
    except Exception:
        return turn_item

    image_output_path = image_generation_artifact_path(codex_home, session_id, "<image_id>")
    image_output_dir = image_output_path.parent if image_output_path.parent is not None else Path(codex_home)
    message = ImageGenerationInstructions.new(image_output_dir, image_output_path).into_response_item()
    recorder = getattr(sess, "record_conversation_items", None)
    if callable(recorder):
        await _maybe_await(recorder(turn_context, [message]))

    return TurnItem.image_generation(
        replace(
            image_item,
            saved_path=saved_path,
        )
    )


def finalized_turn_item_facts(turn_item: TurnItem) -> FinalizedTurnItemFacts:
    if not isinstance(turn_item, TurnItem):
        raise TypeError("turn_item must be a TurnItem")
    if turn_item.type == "AgentMessage":
        agent_message = turn_item.item
        combined = "".join(content.text for content in agent_message.content)
        last_agent_message = None if combined.strip() == "" else combined
        defers = agent_message.phase != MessagePhase.COMMENTARY and last_agent_message is not None
        return FinalizedTurnItemFacts(
            memory_citation=agent_message.memory_citation,
            last_agent_message=last_agent_message,
            defers_mailbox_delivery_to_next_turn=defers,
        )
    if turn_item.type == "ImageGeneration":
        return FinalizedTurnItemFacts(defers_mailbox_delivery_to_next_turn=True)
    return FinalizedTurnItemFacts()


def function_call_error_to_response_input(error: FunctionCallError) -> ResponseInputItem:
    """Convert a model-visible tool error into a follow-up response item."""

    if not isinstance(error, FunctionCallError):
        raise TypeError("error must be a FunctionCallError")
    if error.is_fatal:
        raise RuntimeError(error.message)
    return ResponseInputItem.function_call_output("", error.message)


def function_call_error_output_result(error: FunctionCallError) -> tuple[OutputItemResult, ResponseItem]:
    """Mirror the Rust ``RespondToModel`` stream-event branch."""

    response = function_call_error_to_response_input(error)
    response_item = response_input_to_response_item(response)
    if response_item is None:
        raise RuntimeError("function call output did not convert to a response item")
    return OutputItemResult(needs_follow_up=True), response_item


def sampling_output_state_after_result(
    state: SamplingOutputState,
    output_result: OutputItemResult,
) -> SamplingOutputState:
    if not isinstance(state, SamplingOutputState):
        raise TypeError("state must be a SamplingOutputState")
    if not isinstance(output_result, OutputItemResult):
        raise TypeError("output_result must be an OutputItemResult")
    in_flight = state.in_flight
    if output_result.tool_future is not None:
        in_flight = (*in_flight, output_result.tool_future)
    last_agent_message = state.last_agent_message
    if output_result.last_agent_message is not None:
        last_agent_message = output_result.last_agent_message
    return SamplingOutputState(
        needs_follow_up=state.needs_follow_up or output_result.needs_follow_up,
        last_agent_message=last_agent_message,
        in_flight=in_flight,
    )


def sampling_item_preempts_for_mailbox_mail(item: ResponseItem) -> bool:
    _ensure_response_item(item)
    if item.type == "message":
        return item.role == "assistant" and item.phase == MessagePhase.COMMENTARY
    return item.type == "reasoning"


def sampling_mailbox_preemption_plan(
    item: ResponseItem,
    *,
    has_pending_mailbox_items: bool,
    state: SamplingOutputState,
) -> SamplingMailboxPreemptionPlan | None:
    _ensure_bool(has_pending_mailbox_items, "has_pending_mailbox_items")
    if not isinstance(state, SamplingOutputState):
        raise TypeError("state must be a SamplingOutputState")
    if not sampling_item_preempts_for_mailbox_mail(item) or not has_pending_mailbox_items:
        return None
    return SamplingMailboxPreemptionPlan(
        needs_follow_up=True,
        last_agent_message=state.last_agent_message,
    )


def sampling_output_item_added_plan(
    item: ResponseItem,
    *,
    plan_mode: bool,
    defer_streamed_turn_items_for_contributors: bool = False,
    tool_runtime: object | None = None,
    assistant_message_stream_parsers: object | None = None,
) -> SamplingOutputItemAddedPlan:
    _ensure_response_item(item)
    _ensure_bool(plan_mode, "plan_mode")
    _ensure_bool(defer_streamed_turn_items_for_contributors, "defer_streamed_turn_items_for_contributors")

    active_tool_argument_diff_consumer: tuple[str, object] | None = None
    reset_tool_argument_diff_consumer = False
    if item.type == "custom_tool_call":
        consumer = _create_tool_argument_diff_consumer(tool_runtime, item.name or "")
        if consumer is not None:
            active_tool_argument_diff_consumer = (item.call_id or "", consumer)
    elif item.type == "function_call":
        reset_tool_argument_diff_consumer = True

    turn_item = handle_non_tool_response_item(item, plan_mode)
    stream_item_to_client = turn_item is not None and not defer_streamed_turn_items_for_contributors
    seeded_item_id: str | None = None
    seeded_visible_text: str | None = None
    seeded_parsed: object | None = None
    seeded_raw_text: str | None = None
    if stream_item_to_client and turn_item is not None and turn_item.type == "AgentMessage":
        raw_text = raw_assistant_output_text_from_item(item)
        if raw_text is not None:
            seeded_item_id = turn_item.id()
            seeded_raw_text = raw_text
            seed_item_text = getattr(assistant_message_stream_parsers, "seed_item_text", None)
            if callable(seed_item_text):
                seeded_parsed = seed_item_text(seeded_item_id, raw_text)
                seeded_visible_text = _parsed_field(seeded_parsed, "visible_text", "")
                if seeded_visible_text is None:
                    seeded_visible_text = ""
                _ensure_str(seeded_visible_text, "seeded_visible_text")
            else:
                seeded_visible_text = strip_hidden_assistant_markup(raw_text, plan_mode)
            if plan_mode:
                if seeded_parsed is None:
                    seeded_parsed = {"visible_text": seeded_visible_text}
                turn_item = _agent_message_turn_item_with_text(turn_item, "")
            else:
                turn_item = _agent_message_turn_item_with_text(turn_item, seeded_visible_text)
    return SamplingOutputItemAddedPlan(
        active_tool_argument_diff_consumer=active_tool_argument_diff_consumer,
        reset_tool_argument_diff_consumer=reset_tool_argument_diff_consumer,
        active_item=turn_item,
        turn_item_to_emit=turn_item if stream_item_to_client else None,
        active_item_is_streaming_to_client=stream_item_to_client,
        seeded_item_id=seeded_item_id,
        seeded_visible_text=seeded_visible_text,
        seeded_parsed=seeded_parsed,
        seeded_raw_text=seeded_raw_text,
    )


def sampling_output_item_added_apply_plan(
    added_plan: SamplingOutputItemAddedPlan,
    *,
    plan_mode: bool,
    assistant_message_stream_parsers: object | None = None,
    started_agent_message_item_ids: object = (),
    leading_whitespace_by_item: object | None = None,
    plan_item_started: bool = False,
    plan_item_completed: bool = False,
    plan_item_id: str = "plan",
) -> SamplingOutputItemAddedApplyPlan:
    if not isinstance(added_plan, SamplingOutputItemAddedPlan):
        raise TypeError("added_plan must be a SamplingOutputItemAddedPlan")
    _ensure_bool(plan_mode, "plan_mode")

    pending_agent_message_item: TurnItem | None = None
    turn_item_started_to_emit: TurnItem | None = None
    if added_plan.turn_item_to_emit is not None:
        if plan_mode and added_plan.turn_item_to_emit.type == "AgentMessage":
            pending_agent_message_item = added_plan.turn_item_to_emit
        else:
            turn_item_started_to_emit = added_plan.turn_item_to_emit

    seeded_streamed_assistant_text_plan = None
    seeded_parsed = added_plan.seeded_parsed
    if added_plan.seeded_item_id is not None and added_plan.seeded_raw_text is not None:
        seed_item_text = getattr(assistant_message_stream_parsers, "seed_item_text", None)
        if callable(seed_item_text):
            seeded_parsed = seed_item_text(added_plan.seeded_item_id, added_plan.seeded_raw_text)
    if plan_mode and added_plan.seeded_item_id is not None and seeded_parsed is not None:
        seeded_streamed_assistant_text_plan = sampling_streamed_assistant_text_delta_plan(
            added_plan.seeded_item_id,
            seeded_parsed,
            plan_mode=True,
            started_agent_message_item_ids=started_agent_message_item_ids,
            leading_whitespace_by_item=leading_whitespace_by_item,
            plan_item_started=plan_item_started,
            plan_item_completed=plan_item_completed,
            plan_item_id=plan_item_id,
        )

    return SamplingOutputItemAddedApplyPlan(
        active_tool_argument_diff_consumer_after=added_plan.active_tool_argument_diff_consumer,
        should_reset_tool_argument_diff_consumer=added_plan.reset_tool_argument_diff_consumer,
        pending_agent_message_item=pending_agent_message_item,
        turn_item_started_to_emit=turn_item_started_to_emit,
        seeded_streamed_assistant_text_plan=seeded_streamed_assistant_text_plan,
        active_item_after=added_plan.active_item,
        active_item_is_streaming_to_client_after=added_plan.active_item_is_streaming_to_client,
    )


def sampling_output_text_delta_plan(
    active_item: TurnItem | None,
    delta: str,
    *,
    active_item_is_streaming_to_client: bool,
    plan_mode: bool,
    thread_id: str = "",
    turn_id: str = "",
    assistant_message_stream_parsers: object | None = None,
) -> SamplingOutputTextDeltaPlan | None:
    if active_item is not None and not isinstance(active_item, TurnItem):
        raise TypeError("active_item must be a TurnItem or None")
    _ensure_str(delta, "delta")
    _ensure_bool(active_item_is_streaming_to_client, "active_item_is_streaming_to_client")
    _ensure_bool(plan_mode, "plan_mode")
    if active_item is None or not active_item_is_streaming_to_client:
        return None
    item_id = active_item.id()
    if active_item.type == "AgentMessage":
        parse_delta = getattr(assistant_message_stream_parsers, "parse_delta", None)
        if callable(parse_delta):
            parsed = parse_delta(item_id, delta)
        else:
            visible_text = strip_hidden_assistant_markup(delta, plan_mode)
            parsed = {"visible_text": visible_text}
        return SamplingOutputTextDeltaPlan(
            item_id=item_id,
            delta=delta,
            parsed=parsed,
            thread_id=thread_id,
            turn_id=turn_id,
        )
    return SamplingOutputTextDeltaPlan(
        item_id=item_id,
        delta=delta,
        raw_content_delta=delta,
        thread_id=thread_id,
        turn_id=turn_id,
    )


def sampling_output_text_delta_apply_plan(
    text_delta_plan: SamplingOutputTextDeltaPlan | None,
    *,
    plan_mode: bool,
    assistant_message_stream_parsers: object | None = None,
    started_agent_message_item_ids: object = (),
    leading_whitespace_by_item: object | None = None,
    plan_item_started: bool = False,
    plan_item_completed: bool = False,
    plan_item_id: str = "plan",
) -> SamplingOutputTextDeltaApplyPlan | None:
    if text_delta_plan is None:
        return None
    if not isinstance(text_delta_plan, SamplingOutputTextDeltaPlan):
        raise TypeError("text_delta_plan must be a SamplingOutputTextDeltaPlan or None")
    _ensure_bool(plan_mode, "plan_mode")
    if text_delta_plan.parsed is not None:
        parsed = text_delta_plan.parsed
        parse_delta = getattr(assistant_message_stream_parsers, "parse_delta", None)
        if callable(parse_delta):
            parsed = parse_delta(text_delta_plan.item_id, text_delta_plan.delta)
        return SamplingOutputTextDeltaApplyPlan(
            item_id=text_delta_plan.item_id,
            streamed_assistant_text_plan=sampling_streamed_assistant_text_delta_plan(
                text_delta_plan.item_id,
                parsed,
                plan_mode=plan_mode,
                thread_id=text_delta_plan.thread_id,
                turn_id=text_delta_plan.turn_id,
                started_agent_message_item_ids=started_agent_message_item_ids,
                leading_whitespace_by_item=leading_whitespace_by_item,
                plan_item_started=plan_item_started,
                plan_item_completed=plan_item_completed,
                plan_item_id=plan_item_id,
            ),
            thread_id=text_delta_plan.thread_id,
            turn_id=text_delta_plan.turn_id,
        )
    if text_delta_plan.raw_content_delta is not None:
        return SamplingOutputTextDeltaApplyPlan(
            item_id=text_delta_plan.item_id,
            raw_content_delta=text_delta_plan.raw_content_delta,
            thread_id=text_delta_plan.thread_id,
            turn_id=text_delta_plan.turn_id,
        )
    return SamplingOutputTextDeltaApplyPlan(
        item_id=text_delta_plan.item_id,
        thread_id=text_delta_plan.thread_id,
        turn_id=text_delta_plan.turn_id,
    )


def sampling_tool_call_input_delta_plan(
    active_tool_argument_diff_consumer: tuple[str, object] | None,
    *,
    call_id: str | None,
    delta: str,
    turn_context: object | None = None,
) -> SamplingToolCallInputDeltaPlan | None:
    if active_tool_argument_diff_consumer is None:
        return None
    if (
        not isinstance(active_tool_argument_diff_consumer, tuple)
        or len(active_tool_argument_diff_consumer) != 2
        or not isinstance(active_tool_argument_diff_consumer[0], str)
    ):
        raise TypeError("active_tool_argument_diff_consumer must be a (call_id, consumer) tuple or None")
    if call_id is not None and not isinstance(call_id, str):
        raise TypeError("call_id must be a string or None")
    _ensure_str(delta, "delta")

    active_call_id, consumer = active_tool_argument_diff_consumer
    effective_call_id = active_call_id if call_id is None else call_id
    if effective_call_id != active_call_id:
        return None
    consume_diff = getattr(consumer, "consume_diff", None)
    event = consume_diff(turn_context, effective_call_id, delta) if callable(consume_diff) else None
    return SamplingToolCallInputDeltaPlan(
        call_id=effective_call_id,
        delta=delta,
        event=event,
    )


def sampling_tool_call_input_delta_apply_plan(
    tool_delta_plan: SamplingToolCallInputDeltaPlan | None,
) -> SamplingToolCallInputDeltaApplyPlan | None:
    if tool_delta_plan is None:
        return None
    if not isinstance(tool_delta_plan, SamplingToolCallInputDeltaPlan):
        raise TypeError("tool_delta_plan must be a SamplingToolCallInputDeltaPlan or None")
    return SamplingToolCallInputDeltaApplyPlan(
        call_id=tool_delta_plan.call_id,
        delta=tool_delta_plan.delta,
        event_to_emit=tool_delta_plan.event,
        should_send_event=tool_delta_plan.event is not None,
    )


def sampling_reasoning_summary_delta_plan(
    active_item: TurnItem | None,
    *,
    delta: str,
    summary_index: int,
    active_item_is_streaming_to_client: bool,
    thread_id: str = "",
    turn_id: str = "",
) -> SamplingReasoningDeltaPlan | None:
    active_item = _streaming_active_item_or_none(active_item, active_item_is_streaming_to_client)
    if active_item is None:
        return None
    _ensure_str(delta, "delta")
    _ensure_non_negative_int(summary_index, "summary_index")
    return SamplingReasoningDeltaPlan(
        event_type="reasoning_content_delta",
        item_id=active_item.id(),
        delta=delta,
        summary_index=summary_index,
        thread_id=thread_id,
        turn_id=turn_id,
    )


def sampling_reasoning_summary_part_added_plan(
    active_item: TurnItem | None,
    *,
    summary_index: int,
    active_item_is_streaming_to_client: bool,
    thread_id: str = "",
    turn_id: str = "",
) -> SamplingReasoningDeltaPlan | None:
    active_item = _streaming_active_item_or_none(active_item, active_item_is_streaming_to_client)
    if active_item is None:
        return None
    _ensure_non_negative_int(summary_index, "summary_index")
    return SamplingReasoningDeltaPlan(
        event_type="agent_reasoning_section_break",
        item_id=active_item.id(),
        summary_index=summary_index,
        thread_id=thread_id,
        turn_id=turn_id,
    )


def sampling_reasoning_content_delta_plan(
    active_item: TurnItem | None,
    *,
    delta: str,
    content_index: int,
    active_item_is_streaming_to_client: bool,
    thread_id: str = "",
    turn_id: str = "",
) -> SamplingReasoningDeltaPlan | None:
    active_item = _streaming_active_item_or_none(active_item, active_item_is_streaming_to_client)
    if active_item is None:
        return None
    _ensure_str(delta, "delta")
    _ensure_non_negative_int(content_index, "content_index")
    return SamplingReasoningDeltaPlan(
        event_type="reasoning_raw_content_delta",
        item_id=active_item.id(),
        delta=delta,
        content_index=content_index,
        thread_id=thread_id,
        turn_id=turn_id,
    )


def sampling_reasoning_delta_apply_plan(
    reasoning_delta_plan: SamplingReasoningDeltaPlan | None,
) -> SamplingReasoningDeltaApplyPlan | None:
    if reasoning_delta_plan is None:
        return None
    if not isinstance(reasoning_delta_plan, SamplingReasoningDeltaPlan):
        raise TypeError("reasoning_delta_plan must be a SamplingReasoningDeltaPlan or None")
    event_type = reasoning_delta_plan.event_type
    if event_type == "reasoning_content_delta":
        if reasoning_delta_plan.delta is None or reasoning_delta_plan.summary_index is None:
            raise TypeError("reasoning_content_delta requires delta and summary_index")
        event_to_emit = {
            "type": event_type,
            "thread_id": reasoning_delta_plan.thread_id,
            "turn_id": reasoning_delta_plan.turn_id,
            "item_id": reasoning_delta_plan.item_id,
            "delta": reasoning_delta_plan.delta,
            "summary_index": reasoning_delta_plan.summary_index,
        }
    elif event_type == "agent_reasoning_section_break":
        if reasoning_delta_plan.summary_index is None:
            raise TypeError("agent_reasoning_section_break requires summary_index")
        event_to_emit = {
            "type": event_type,
            "item_id": reasoning_delta_plan.item_id,
            "summary_index": reasoning_delta_plan.summary_index,
        }
    elif event_type == "reasoning_raw_content_delta":
        if reasoning_delta_plan.delta is None or reasoning_delta_plan.content_index is None:
            raise TypeError("reasoning_raw_content_delta requires delta and content_index")
        event_to_emit = {
            "type": event_type,
            "thread_id": reasoning_delta_plan.thread_id,
            "turn_id": reasoning_delta_plan.turn_id,
            "item_id": reasoning_delta_plan.item_id,
            "delta": reasoning_delta_plan.delta,
            "content_index": reasoning_delta_plan.content_index,
        }
    else:
        raise ValueError(f"unsupported reasoning delta event type: {event_type}")
    return SamplingReasoningDeltaApplyPlan(
        event_type=event_type,
        item_id=reasoning_delta_plan.item_id,
        event_to_emit=event_to_emit,
    )


def sampling_assistant_text_flush_plan(
    active_item: TurnItem | None,
    *,
    assistant_message_stream_parsers: object,
    active_item_is_streaming_to_client: bool,
) -> SamplingAssistantTextFlushPlan | None:
    active_item = _streaming_active_item_or_none(active_item, active_item_is_streaming_to_client)
    if active_item is None or active_item.type != "AgentMessage":
        return None
    finish_item = getattr(assistant_message_stream_parsers, "finish_item", None)
    if not callable(finish_item):
        raise TypeError("assistant_message_stream_parsers must provide finish_item")
    item_id = active_item.id()
    return SamplingAssistantTextFlushPlan(
        item_id=item_id,
        parsed=finish_item(item_id),
    )


def sampling_assistant_text_flush_all_plan(
    *,
    assistant_message_stream_parsers: object,
) -> SamplingAssistantTextFlushAllPlan:
    drain_finished = getattr(assistant_message_stream_parsers, "drain_finished", None)
    if not callable(drain_finished):
        raise TypeError("assistant_message_stream_parsers must provide drain_finished")
    item_plans: list[SamplingAssistantTextFlushPlan] = []
    for item_id, parsed in drain_finished():
        _ensure_str(item_id, "item_id")
        item_plans.append(SamplingAssistantTextFlushPlan(item_id=item_id, parsed=parsed))
    return SamplingAssistantTextFlushAllPlan(tuple(item_plans))


def sampling_streamed_assistant_text_delta_plan(
    item_id: str,
    parsed: object,
    *,
    plan_mode: bool,
    thread_id: str = "",
    turn_id: str = "",
    started_agent_message_item_ids: object = (),
    leading_whitespace_by_item: object | None = None,
    plan_item_started: bool = False,
    plan_item_completed: bool = False,
    plan_item_id: str = "plan",
) -> SamplingStreamedAssistantTextDeltaPlan | None:
    _ensure_str(item_id, "item_id")
    _ensure_bool(plan_mode, "plan_mode")
    visible_text = _parsed_field(parsed, "visible_text", "")
    if visible_text is None:
        visible_text = ""
    _ensure_str(visible_text, "visible_text")
    citations = _parsed_str_sequence_field(parsed, "citations")
    plan_segments = _parsed_field(parsed, "plan_segments", ())
    if plan_segments is None:
        plan_segments = ()
    if _parsed_assistant_delta_is_empty(parsed, visible_text, citations, plan_segments):
        return None
    ignored_citations = bool(citations)
    if plan_mode:
        plan_segments_plan = None
        if plan_segments:
            plan_segments_plan = sampling_plan_segments_plan(
                item_id,
                plan_segments,
                started_agent_message_item_ids=started_agent_message_item_ids,
                leading_whitespace_by_item=leading_whitespace_by_item,
                plan_item_started=plan_item_started,
                plan_item_completed=plan_item_completed,
                plan_item_id=plan_item_id,
            )
        return SamplingStreamedAssistantTextDeltaPlan(
            item_id=item_id,
            plan_segments_plan=plan_segments_plan,
            citations=citations,
            ignored_citations=ignored_citations,
            thread_id=thread_id,
            turn_id=turn_id,
        )
    if visible_text == "":
        return None
    return SamplingStreamedAssistantTextDeltaPlan(
        item_id=item_id,
        visible_text_delta=visible_text,
        citations=citations,
        ignored_citations=ignored_citations,
        thread_id=thread_id,
        turn_id=turn_id,
    )


def sampling_output_item_done_transition_plan(
    active_item: TurnItem | None,
    *,
    active_item_is_streaming_to_client: bool,
    active_tool_argument_diff_consumer: tuple[str, object] | None = None,
    assistant_message_stream_parsers: object | None = None,
    thread_id: str = "",
    turn_id: str = "",
) -> SamplingOutputItemDoneTransitionPlan:
    if active_item is not None and not isinstance(active_item, TurnItem):
        raise TypeError("active_item must be a TurnItem or None")
    _ensure_bool(active_item_is_streaming_to_client, "active_item_is_streaming_to_client")
    finished_tool_input_event = _finish_tool_argument_diff_consumer_event(active_tool_argument_diff_consumer)
    previously_streamed_item = active_item if active_item_is_streaming_to_client else None
    assistant_text_flush_plan: SamplingAssistantTextFlushPlan | None = None
    if previously_streamed_item is not None and previously_streamed_item.type == "AgentMessage":
        if assistant_message_stream_parsers is None:
            raise TypeError("assistant_message_stream_parsers must provide finish_item")
        assistant_text_flush_plan = sampling_assistant_text_flush_plan(
            previously_streamed_item,
            assistant_message_stream_parsers=assistant_message_stream_parsers,
            active_item_is_streaming_to_client=True,
        )
    return SamplingOutputItemDoneTransitionPlan(
        previously_active_item=active_item,
        previously_streamed_item=previously_streamed_item,
        active_item_after=None,
        active_item_is_streaming_to_client_after=False,
        finished_tool_input_event=finished_tool_input_event,
        assistant_text_flush_plan=assistant_text_flush_plan,
        thread_id=thread_id,
        turn_id=turn_id,
    )


def sampling_metadata_event_plan(
    event_type: str,
    payload: object,
    *,
    server_model_warning_emitted: bool = False,
    model_verification_emitted: bool = False,
) -> SamplingMetadataEventPlan | None:
    _ensure_str(event_type, "event_type")
    _ensure_bool(server_model_warning_emitted, "server_model_warning_emitted")
    _ensure_bool(model_verification_emitted, "model_verification_emitted")
    if event_type == "server_model":
        _ensure_str(payload, "server_model")
        if server_model_warning_emitted:
            return None
        return SamplingMetadataEventPlan(
            event_type=event_type,
            payload=payload,
            should_maybe_warn_server_model_mismatch=True,
            should_mark_server_model_warning_if_emitted=True,
        )
    if event_type == "model_verifications":
        if model_verification_emitted:
            return None
        return SamplingMetadataEventPlan(
            event_type=event_type,
            payload=payload,
            should_emit_model_verification=True,
            should_mark_model_verification_emitted=True,
        )
    if event_type == "server_reasoning_included":
        _ensure_bool(payload, "server_reasoning_included")
        return SamplingMetadataEventPlan(
            event_type=event_type,
            payload=payload,
            should_set_server_reasoning_included=True,
        )
    if event_type == "rate_limits":
        return SamplingMetadataEventPlan(
            event_type=event_type,
            payload=payload,
            should_record_rate_limits=True,
            should_emit_token_count=True,
        )
    if event_type == "models_etag":
        _ensure_str(payload, "models_etag")
        return SamplingMetadataEventPlan(
            event_type=event_type,
            payload=payload,
            should_refresh_models_etag=True,
        )
    raise ValueError(f"unsupported sampling metadata event type: {event_type}")


def sampling_metadata_event_apply_plan(
    metadata_plan: SamplingMetadataEventPlan | None,
) -> SamplingMetadataEventApplyPlan | None:
    if metadata_plan is None:
        return None
    if not isinstance(metadata_plan, SamplingMetadataEventPlan):
        raise TypeError("metadata_plan must be a SamplingMetadataEventPlan or None")
    if metadata_plan.event_type == "server_model":
        return SamplingMetadataEventApplyPlan(
            event_type=metadata_plan.event_type,
            server_model_to_check=metadata_plan.payload if metadata_plan.should_maybe_warn_server_model_mismatch else None,
            should_mark_server_model_warning_if_emitted=metadata_plan.should_mark_server_model_warning_if_emitted,
        )
    if metadata_plan.event_type == "model_verifications":
        return SamplingMetadataEventApplyPlan(
            event_type=metadata_plan.event_type,
            model_verification_to_emit=metadata_plan.payload if metadata_plan.should_emit_model_verification else None,
            should_mark_model_verification_emitted=metadata_plan.should_mark_model_verification_emitted,
        )
    if metadata_plan.event_type == "server_reasoning_included":
        return SamplingMetadataEventApplyPlan(
            event_type=metadata_plan.event_type,
            server_reasoning_included=metadata_plan.payload if metadata_plan.should_set_server_reasoning_included else None,
        )
    if metadata_plan.event_type == "rate_limits":
        return SamplingMetadataEventApplyPlan(
            event_type=metadata_plan.event_type,
            rate_limits_to_record=metadata_plan.payload if metadata_plan.should_record_rate_limits else None,
            should_emit_token_count=metadata_plan.should_emit_token_count,
        )
    if metadata_plan.event_type == "models_etag":
        return SamplingMetadataEventApplyPlan(
            event_type=metadata_plan.event_type,
            models_etag_to_refresh=metadata_plan.payload if metadata_plan.should_refresh_models_etag else None,
        )
    raise ValueError(f"unsupported sampling metadata event type: {metadata_plan.event_type}")


def sampling_completed_event_plan(
    *,
    response_id: str,
    token_usage: object | None,
    end_turn: bool | None,
    state: SamplingOutputState,
    thread_id: str = "",
    turn_id: str = "",
) -> SamplingCompletedEventPlan:
    _ensure_str(response_id, "response_id")
    if end_turn is not None:
        _ensure_bool(end_turn, "end_turn")
    if not isinstance(state, SamplingOutputState):
        raise TypeError("state must be a SamplingOutputState")
    return SamplingCompletedEventPlan(
        response_id=response_id,
        token_usage=token_usage,
        needs_follow_up=state.needs_follow_up or end_turn is False,
        last_agent_message=state.last_agent_message,
        completed_response_id=response_id,
        thread_id=thread_id,
        turn_id=turn_id,
    )


def sampling_completed_event_apply_plan(
    completed_plan: SamplingCompletedEventPlan,
    *,
    assistant_message_stream_parsers: object | None = None,
) -> SamplingCompletedEventApplyPlan:
    if not isinstance(completed_plan, SamplingCompletedEventPlan):
        raise TypeError("completed_plan must be a SamplingCompletedEventPlan")
    flush_all_plan = None
    if completed_plan.should_flush_assistant_text_segments_all:
        if assistant_message_stream_parsers is None:
            raise TypeError("assistant_message_stream_parsers is required when flushing assistant text")
        flush_all_plan = sampling_assistant_text_flush_all_plan(
            assistant_message_stream_parsers=assistant_message_stream_parsers,
        )
    return SamplingCompletedEventApplyPlan(
        response_id=completed_plan.response_id,
        flush_all_plan=flush_all_plan,
        token_usage_to_record=completed_plan.token_usage,
        should_record_token_usage=completed_plan.should_record_token_usage,
        should_emit_token_count=completed_plan.should_emit_token_count,
        should_emit_turn_diff=completed_plan.should_emit_turn_diff,
        completed_response_id_after=completed_plan.completed_response_id,
        result_needs_follow_up=completed_plan.needs_follow_up,
        result_last_agent_message=completed_plan.last_agent_message,
        thread_id=completed_plan.thread_id,
        turn_id=completed_plan.turn_id,
    )


def sampling_stream_event_dispatch_plan(
    event_type: str,
    payload: object = None,
    *,
    state: SamplingOutputState | None = None,
    active_item: TurnItem | None = None,
    active_item_is_streaming_to_client: bool = False,
    active_tool_argument_diff_consumer: tuple[str, object] | None = None,
    assistant_message_stream_parsers: object | None = None,
    plan_mode: bool = False,
    defer_streamed_turn_items_for_contributors: bool = False,
    tool_runtime: object | None = None,
    call_id: str | None = None,
    delta: str | None = None,
    turn_context: object | None = None,
    thread_id: str = "",
    turn_id: str = "",
    summary_index: int | None = None,
    content_index: int | None = None,
    response_id: str | None = None,
    token_usage: object | None = None,
    end_turn: bool | None = None,
    server_model_warning_emitted: bool = False,
    model_verification_emitted: bool = False,
) -> SamplingStreamEventDispatchPlan:
    _ensure_str(event_type, "event_type")
    event_type = _normalized_sampling_stream_event_type(event_type)
    _ensure_bool(active_item_is_streaming_to_client, "active_item_is_streaming_to_client")
    _ensure_bool(plan_mode, "plan_mode")
    _ensure_bool(defer_streamed_turn_items_for_contributors, "defer_streamed_turn_items_for_contributors")
    if active_item is not None and not isinstance(active_item, TurnItem):
        raise TypeError("active_item must be a TurnItem or None")
    if state is not None and not isinstance(state, SamplingOutputState):
        raise TypeError("state must be a SamplingOutputState or None")

    if event_type == "created":
        return SamplingStreamEventDispatchPlan(event_type=event_type, no_op=True)
    if event_type == "output_item_done":
        if not isinstance(payload, ResponseItem):
            raise TypeError("output_item_done payload must be a ResponseItem")
        if assistant_message_stream_parsers is None:
            assistant_message_stream_parsers = _NoopAssistantMessageStreamParsers()
        return SamplingStreamEventDispatchPlan(
            event_type=event_type,
            output_item_done_transition_plan=sampling_output_item_done_transition_plan(
                active_item,
                active_item_is_streaming_to_client=active_item_is_streaming_to_client,
                active_tool_argument_diff_consumer=active_tool_argument_diff_consumer,
                assistant_message_stream_parsers=assistant_message_stream_parsers,
                thread_id=thread_id,
                turn_id=turn_id,
            ),
        )
    if event_type == "output_item_added":
        if not isinstance(payload, ResponseItem):
            raise TypeError("output_item_added payload must be a ResponseItem")
        return SamplingStreamEventDispatchPlan(
            event_type=event_type,
            output_item_added_plan=sampling_output_item_added_plan(
                payload,
                plan_mode=plan_mode,
                defer_streamed_turn_items_for_contributors=defer_streamed_turn_items_for_contributors,
                tool_runtime=tool_runtime,
                assistant_message_stream_parsers=assistant_message_stream_parsers,
            ),
        )
    if event_type == "output_text_delta":
        effective_delta = _coalesce_delta(delta, payload)
        return SamplingStreamEventDispatchPlan(
            event_type=event_type,
            output_text_delta_plan=sampling_output_text_delta_plan(
                active_item,
                effective_delta,
                active_item_is_streaming_to_client=active_item_is_streaming_to_client,
                plan_mode=plan_mode,
                thread_id=thread_id,
                turn_id=turn_id,
                assistant_message_stream_parsers=assistant_message_stream_parsers,
            ),
        )
    if event_type == "tool_call_input_delta":
        effective_delta = _coalesce_delta(delta, payload)
        if call_id is None:
            maybe_call_id = _payload_field(payload, "call_id")
            call_id = maybe_call_id if isinstance(maybe_call_id, str) else None
        return SamplingStreamEventDispatchPlan(
            event_type=event_type,
            tool_call_input_delta_plan=sampling_tool_call_input_delta_plan(
                active_tool_argument_diff_consumer,
                call_id=call_id,
                delta=effective_delta,
                turn_context=turn_context,
            ),
        )
    if event_type == "reasoning_summary_delta":
        effective_delta = _coalesce_delta(delta, payload)
        if summary_index is None:
            maybe_summary_index = _payload_field(payload, "summary_index")
            summary_index = maybe_summary_index if isinstance(maybe_summary_index, int) else None
        if summary_index is None:
            raise TypeError("summary_index is required for reasoning_summary_delta")
        return SamplingStreamEventDispatchPlan(
            event_type=event_type,
            reasoning_delta_plan=sampling_reasoning_summary_delta_plan(
                active_item,
                delta=effective_delta,
                summary_index=summary_index,
                active_item_is_streaming_to_client=active_item_is_streaming_to_client,
                thread_id=thread_id,
                turn_id=turn_id,
            ),
        )
    if event_type == "reasoning_summary_part_added":
        if summary_index is None:
            maybe_summary_index = _payload_field(payload, "summary_index")
            summary_index = maybe_summary_index if isinstance(maybe_summary_index, int) else None
        if summary_index is None:
            raise TypeError("summary_index is required for reasoning_summary_part_added")
        return SamplingStreamEventDispatchPlan(
            event_type=event_type,
            reasoning_delta_plan=sampling_reasoning_summary_part_added_plan(
                active_item,
                summary_index=summary_index,
                active_item_is_streaming_to_client=active_item_is_streaming_to_client,
                thread_id=thread_id,
                turn_id=turn_id,
            ),
        )
    if event_type == "reasoning_content_delta":
        effective_delta = _coalesce_delta(delta, payload)
        if content_index is None:
            maybe_content_index = _payload_field(payload, "content_index")
            content_index = maybe_content_index if isinstance(maybe_content_index, int) else None
        if content_index is None:
            raise TypeError("content_index is required for reasoning_content_delta")
        return SamplingStreamEventDispatchPlan(
            event_type=event_type,
            reasoning_delta_plan=sampling_reasoning_content_delta_plan(
                active_item,
                delta=effective_delta,
                content_index=content_index,
                active_item_is_streaming_to_client=active_item_is_streaming_to_client,
                thread_id=thread_id,
                turn_id=turn_id,
            ),
        )
    if event_type == "completed":
        if state is None:
            raise TypeError("state is required for completed")
        if response_id is None:
            response_id = _payload_field(payload, "response_id")
        if not isinstance(response_id, str):
            raise TypeError("response_id is required for completed")
        if token_usage is None:
            token_usage = _payload_field(payload, "token_usage")
        if end_turn is None:
            maybe_end_turn = _payload_field(payload, "end_turn")
            end_turn = maybe_end_turn if isinstance(maybe_end_turn, bool) else None
        return SamplingStreamEventDispatchPlan(
            event_type=event_type,
            completed_event_plan=sampling_completed_event_plan(
                response_id=response_id,
                token_usage=token_usage,
                end_turn=end_turn,
                state=state,
                thread_id=thread_id,
                turn_id=turn_id,
            ),
        )
    if event_type in {
        "server_model",
        "model_verifications",
        "server_reasoning_included",
        "rate_limits",
        "models_etag",
    }:
        return SamplingStreamEventDispatchPlan(
            event_type=event_type,
            metadata_event_plan=sampling_metadata_event_plan(
                event_type,
                payload,
                server_model_warning_emitted=server_model_warning_emitted,
                model_verification_emitted=model_verification_emitted,
            ),
        )
    raise ValueError(f"unsupported sampling stream event type: {event_type}")


def sampling_stream_event_apply_plan(
    dispatch_plan: SamplingStreamEventDispatchPlan,
    *,
    plan_mode: bool,
    state: SamplingOutputState | None = None,
    output_item_done_item: ResponseItem | None = None,
    output_item_done_result: OutputItemResult | None = None,
    has_pending_mailbox_items: bool = False,
    assistant_message_stream_parsers: object | None = None,
    memories_disable_on_external_context: bool = False,
    plan_item_id: str = "plan",
    plan_item_started: bool = False,
    plan_item_completed: bool = False,
    pending_agent_message_items: object | None = None,
    started_agent_message_item_ids: object = (),
    leading_whitespace_by_item: object | None = None,
) -> SamplingStreamEventApplyPlan:
    if not isinstance(dispatch_plan, SamplingStreamEventDispatchPlan):
        raise TypeError("dispatch_plan must be a SamplingStreamEventDispatchPlan")
    _ensure_bool(plan_mode, "plan_mode")
    if state is not None and not isinstance(state, SamplingOutputState):
        raise TypeError("state must be a SamplingOutputState or None")
    if dispatch_plan.no_op:
        return SamplingStreamEventApplyPlan(event_type=dispatch_plan.event_type, no_op=True)
    if dispatch_plan.output_item_done_transition_plan is not None:
        if output_item_done_item is None:
            raise TypeError("output_item_done_item is required for output_item_done apply")
        if state is None:
            raise TypeError("state is required for output_item_done apply")
        return SamplingStreamEventApplyPlan(
            event_type=dispatch_plan.event_type,
            output_item_done_apply_plan=sampling_output_item_done_apply_plan(
                output_item_done_item,
                dispatch_plan.output_item_done_transition_plan,
                plan_mode=plan_mode,
                state=state,
                output_result=output_item_done_result,
                has_pending_mailbox_items=has_pending_mailbox_items,
                memories_disable_on_external_context=memories_disable_on_external_context,
                plan_item_id=plan_item_id,
                plan_item_started=plan_item_started,
                plan_item_completed=plan_item_completed,
                pending_agent_message_items=pending_agent_message_items,
                started_agent_message_item_ids=started_agent_message_item_ids,
                leading_whitespace_by_item=leading_whitespace_by_item,
            ),
        )
    if dispatch_plan.output_item_added_plan is not None:
        return SamplingStreamEventApplyPlan(
            event_type=dispatch_plan.event_type,
            output_item_added_apply_plan=sampling_output_item_added_apply_plan(
                dispatch_plan.output_item_added_plan,
                plan_mode=plan_mode,
                assistant_message_stream_parsers=assistant_message_stream_parsers,
                started_agent_message_item_ids=started_agent_message_item_ids,
                leading_whitespace_by_item=leading_whitespace_by_item,
                plan_item_started=plan_item_started,
                plan_item_completed=plan_item_completed,
                plan_item_id=plan_item_id,
            ),
        )
    if dispatch_plan.output_text_delta_plan is not None:
        return SamplingStreamEventApplyPlan(
            event_type=dispatch_plan.event_type,
            output_text_delta_apply_plan=sampling_output_text_delta_apply_plan(
                dispatch_plan.output_text_delta_plan,
                plan_mode=plan_mode,
                assistant_message_stream_parsers=assistant_message_stream_parsers,
                started_agent_message_item_ids=started_agent_message_item_ids,
                leading_whitespace_by_item=leading_whitespace_by_item,
                plan_item_started=plan_item_started,
                plan_item_completed=plan_item_completed,
                plan_item_id=plan_item_id,
            ),
        )
    if dispatch_plan.tool_call_input_delta_plan is not None:
        return SamplingStreamEventApplyPlan(
            event_type=dispatch_plan.event_type,
            tool_call_input_delta_apply_plan=sampling_tool_call_input_delta_apply_plan(
                dispatch_plan.tool_call_input_delta_plan,
            ),
        )
    if dispatch_plan.reasoning_delta_plan is not None:
        return SamplingStreamEventApplyPlan(
            event_type=dispatch_plan.event_type,
            reasoning_delta_apply_plan=sampling_reasoning_delta_apply_plan(dispatch_plan.reasoning_delta_plan),
        )
    if dispatch_plan.completed_event_plan is not None:
        return SamplingStreamEventApplyPlan(
            event_type=dispatch_plan.event_type,
            completed_event_apply_plan=sampling_completed_event_apply_plan(
                dispatch_plan.completed_event_plan,
                assistant_message_stream_parsers=assistant_message_stream_parsers,
            ),
        )
    if dispatch_plan.metadata_event_plan is not None:
        return SamplingStreamEventApplyPlan(
            event_type=dispatch_plan.event_type,
            metadata_event_apply_plan=sampling_metadata_event_apply_plan(dispatch_plan.metadata_event_plan),
        )
    return SamplingStreamEventApplyPlan(event_type=dispatch_plan.event_type, no_op=True)


def sampling_plan_mode_assistant_done_plan(
    item: ResponseItem,
    *,
    previously_active_item: TurnItem | None = None,
    plan_item_id: str = "plan",
    plan_item_started: bool = False,
    plan_item_completed: bool = False,
    pending_agent_message_items: object | None = None,
    started_agent_message_item_ids: object = (),
    memories_disable_on_external_context: bool = False,
) -> SamplingPlanModeAssistantDonePlan:
    _ensure_response_item(item)
    if previously_active_item is not None and not isinstance(previously_active_item, TurnItem):
        raise TypeError("previously_active_item must be a TurnItem or None")
    _ensure_str(plan_item_id, "plan_item_id")
    _ensure_bool(plan_item_started, "plan_item_started")
    _ensure_bool(plan_item_completed, "plan_item_completed")
    _ensure_bool(memories_disable_on_external_context, "memories_disable_on_external_context")
    if item.type != "message" or item.role != "assistant":
        return SamplingPlanModeAssistantDonePlan(handled=False)

    proposed_plan_completion_plan = sampling_proposed_plan_completion_plan(
        item,
        plan_item_id=plan_item_id,
        plan_item_started=plan_item_started,
        plan_item_completed=plan_item_completed,
    )
    finalized = finalize_non_tool_response_item(item, True)
    facts = finalized.facts if finalized is not None else None
    turn_item_emit_plan = (
        sampling_plan_mode_turn_item_emit_plan(
            finalized.turn_item,
            previously_active_item=previously_active_item,
            pending_agent_message_items=pending_agent_message_items,
            started_agent_message_item_ids=started_agent_message_item_ids,
        )
        if finalized is not None
        else None
    )
    recording_plan = completed_response_item_recording_plan(
        item,
        True,
        facts,
        memories_disable_on_external_context=memories_disable_on_external_context,
    )
    last_agent_message = facts.last_agent_message if facts is not None else None
    is_agent_message = finalized is not None and finalized.turn_item.type == "AgentMessage"
    should_drop_empty = is_agent_message and last_agent_message is None
    return SamplingPlanModeAssistantDonePlan(
        handled=True,
        should_continue_loop=True,
        should_complete_plan_item_from_message=True,
        proposed_plan_completion_plan=proposed_plan_completion_plan,
        finalized_turn_item=finalized,
        turn_item_emit_plan=turn_item_emit_plan,
        recording_plan=recording_plan,
        last_agent_message=last_agent_message,
        should_update_last_agent_message=last_agent_message is not None,
        should_emit_agent_message_started_if_needed=is_agent_message and not should_drop_empty,
        should_emit_agent_message_completed=is_agent_message and not should_drop_empty,
        should_drop_empty_agent_message=should_drop_empty,
        previously_active_item=previously_active_item,
    )


def sampling_output_item_done_apply_plan(
    item: ResponseItem,
    transition_plan: SamplingOutputItemDoneTransitionPlan,
    *,
    plan_mode: bool,
    state: SamplingOutputState,
    output_result: OutputItemResult | None = None,
    has_pending_mailbox_items: bool = False,
    memories_disable_on_external_context: bool = False,
    plan_item_id: str = "plan",
    plan_item_started: bool = False,
    plan_item_completed: bool = False,
    pending_agent_message_items: object | None = None,
    started_agent_message_item_ids: object = (),
    leading_whitespace_by_item: object | None = None,
) -> SamplingOutputItemDoneApplyPlan:
    _ensure_response_item(item)
    if not isinstance(transition_plan, SamplingOutputItemDoneTransitionPlan):
        raise TypeError("transition_plan must be a SamplingOutputItemDoneTransitionPlan")
    _ensure_bool(plan_mode, "plan_mode")
    if not isinstance(state, SamplingOutputState):
        raise TypeError("state must be a SamplingOutputState")
    if output_result is not None and not isinstance(output_result, OutputItemResult):
        raise TypeError("output_result must be an OutputItemResult or None")
    _ensure_bool(has_pending_mailbox_items, "has_pending_mailbox_items")

    streamed_assistant_text_plan = None
    if transition_plan.assistant_text_flush_plan is not None:
        streamed_assistant_text_plan = sampling_streamed_assistant_text_delta_plan(
            transition_plan.assistant_text_flush_plan.item_id,
            transition_plan.assistant_text_flush_plan.parsed,
            plan_mode=plan_mode,
            thread_id=transition_plan.thread_id,
            turn_id=transition_plan.turn_id,
            started_agent_message_item_ids=started_agent_message_item_ids,
            leading_whitespace_by_item=leading_whitespace_by_item,
            plan_item_started=plan_item_started,
            plan_item_completed=plan_item_completed,
            plan_item_id=plan_item_id,
        )

    plan_mode_assistant_done_plan = None
    if plan_mode:
        plan_mode_assistant_done_plan = sampling_plan_mode_assistant_done_plan(
            item,
            previously_active_item=transition_plan.previously_streamed_item,
            plan_item_id=plan_item_id,
            plan_item_started=plan_item_started,
            plan_item_completed=plan_item_completed,
            pending_agent_message_items=pending_agent_message_items,
            started_agent_message_item_ids=started_agent_message_item_ids,
            memories_disable_on_external_context=memories_disable_on_external_context,
        )
        if plan_mode_assistant_done_plan.handled:
            return SamplingOutputItemDoneApplyPlan(
                transition_plan=transition_plan,
                streamed_assistant_text_plan=streamed_assistant_text_plan,
                plan_mode_assistant_done_plan=plan_mode_assistant_done_plan,
                should_continue_loop=True,
                preempt_for_mailbox_mail=sampling_item_preempts_for_mailbox_mail(item),
                completed_item=item,
            )

    if output_result is None:
        raise TypeError("output_result is required when output item done is not handled by plan mode")
    state_after = sampling_output_state_after_result(state, output_result)
    preempt_for_mailbox_mail = sampling_item_preempts_for_mailbox_mail(item)
    mailbox_preemption_plan = sampling_mailbox_preemption_plan(
        item,
        has_pending_mailbox_items=has_pending_mailbox_items,
        state=state_after,
    )
    return SamplingOutputItemDoneApplyPlan(
        transition_plan=transition_plan,
        streamed_assistant_text_plan=streamed_assistant_text_plan,
        plan_mode_assistant_done_plan=plan_mode_assistant_done_plan,
        should_continue_loop=False,
        preempt_for_mailbox_mail=preempt_for_mailbox_mail,
        output_result=output_result,
        state_after_output_result=state_after,
        mailbox_preemption_plan=mailbox_preemption_plan,
        completed_item=item,
    )


def sampling_plan_segments_plan(
    item_id: str,
    segments: object,
    *,
    started_agent_message_item_ids: object = (),
    leading_whitespace_by_item: object | None = None,
    plan_item_started: bool = False,
    plan_item_completed: bool = False,
    plan_item_id: str = "plan",
) -> SamplingPlanSegmentsPlan:
    _ensure_str(item_id, "item_id")
    _ensure_bool(plan_item_started, "plan_item_started")
    _ensure_bool(plan_item_completed, "plan_item_completed")
    _ensure_str(plan_item_id, "plan_item_id")
    started_items = _str_set(started_agent_message_item_ids, "started_agent_message_item_ids")
    leading = _str_dict(leading_whitespace_by_item or {}, "leading_whitespace_by_item")
    actions: list[SamplingPlanSegmentAction] = []
    current_plan_started = plan_item_started

    for segment_type, delta in _normalized_plan_segments(segments):
        if segment_type == "normal":
            if delta == "":
                continue
            has_non_whitespace = any(not ch.isspace() for ch in delta)
            if not has_non_whitespace and item_id not in started_items:
                leading[item_id] = leading.get(item_id, "") + delta
                continue
            effective_delta = delta
            if item_id not in started_items and item_id in leading:
                effective_delta = leading.pop(item_id) + delta
            actions.append(SamplingPlanSegmentAction("emit_pending_agent_message_start", item_id))
            actions.append(SamplingPlanSegmentAction("agent_message_delta", item_id, effective_delta))
        elif segment_type == "proposed_plan_start":
            if not plan_item_completed and not current_plan_started:
                current_plan_started = True
                actions.append(SamplingPlanSegmentAction("start_plan_item", plan_item_id))
        elif segment_type == "proposed_plan_delta":
            if not plan_item_completed:
                if not current_plan_started:
                    current_plan_started = True
                    actions.append(SamplingPlanSegmentAction("start_plan_item", plan_item_id))
                if delta != "":
                    actions.append(SamplingPlanSegmentAction("plan_delta", plan_item_id, delta))
        elif segment_type == "proposed_plan_end":
            continue
        else:
            raise ValueError(f"unsupported plan segment type: {segment_type}")

    return SamplingPlanSegmentsPlan(
        actions=tuple(actions),
        leading_whitespace_by_item_after=tuple(sorted(leading.items())),
        plan_item_started_after=current_plan_started,
        plan_item_completed_after=plan_item_completed,
    )


def sampling_proposed_plan_completion_plan(
    item: ResponseItem,
    *,
    plan_item_id: str,
    plan_item_started: bool,
    plan_item_completed: bool,
) -> SamplingProposedPlanCompletionPlan | None:
    _ensure_response_item(item)
    _ensure_str(plan_item_id, "plan_item_id")
    _ensure_bool(plan_item_started, "plan_item_started")
    _ensure_bool(plan_item_completed, "plan_item_completed")
    if item.type != "message" or item.role != "assistant":
        return None
    raw_text = raw_assistant_output_text_from_item(item) or ""
    plan_text = _extract_proposed_plan_text(raw_text)
    if plan_text is None:
        return None
    plan_text = _strip_citations(plan_text)
    if plan_item_completed:
        return SamplingProposedPlanCompletionPlan(
            plan_item_id=plan_item_id,
            plan_text=plan_text,
            should_start_plan_item=False,
            should_complete_plan_item=False,
            plan_item_started_after=plan_item_started,
            plan_item_completed_after=True,
        )
    return SamplingProposedPlanCompletionPlan(
        plan_item_id=plan_item_id,
        plan_text=plan_text,
        should_start_plan_item=not plan_item_started,
        should_complete_plan_item=plan_item_started or not plan_item_completed,
        plan_item_started_after=True,
        plan_item_completed_after=True,
    )


def sampling_pending_agent_message_start_plan(
    item_id: str,
    *,
    pending_agent_message_items: object | None = None,
    started_agent_message_item_ids: object = (),
) -> SamplingPendingAgentMessageStartPlan | None:
    _ensure_str(item_id, "item_id")
    pending = _turn_item_dict(pending_agent_message_items or {}, "pending_agent_message_items")
    started = _str_set(started_agent_message_item_ids, "started_agent_message_item_ids")
    if item_id in started:
        return None
    item = pending.pop(item_id, None)
    if item is None:
        return None
    started.add(item_id)
    return SamplingPendingAgentMessageStartPlan(
        item_id=item_id,
        turn_item_to_start=item,
        started_agent_message_item_ids_after=tuple(sorted(started)),
        pending_agent_message_item_ids_after=tuple(sorted(pending)),
    )


def sampling_plan_mode_agent_message_emit_plan(
    agent_message: AgentMessageItem,
    *,
    pending_agent_message_items: object | None = None,
    started_agent_message_item_ids: object = (),
) -> SamplingPlanModeAgentMessageEmitPlan:
    if not isinstance(agent_message, AgentMessageItem):
        raise TypeError("agent_message must be an AgentMessageItem")
    item_id = agent_message.id
    text = "".join(content.text for content in agent_message.content)
    pending = _turn_item_dict(pending_agent_message_items or {}, "pending_agent_message_items")
    started = _str_set(started_agent_message_item_ids, "started_agent_message_item_ids")
    if text.strip() == "":
        pending.pop(item_id, None)
        started.discard(item_id)
        return SamplingPlanModeAgentMessageEmitPlan(
            item_id=item_id,
            text=text,
            should_drop_empty_agent_message=True,
            started_agent_message_item_ids_after=tuple(sorted(started)),
            pending_agent_message_item_ids_after=tuple(sorted(pending)),
        )

    pending_start_plan = sampling_pending_agent_message_start_plan(
        item_id,
        pending_agent_message_items=pending,
        started_agent_message_item_ids=started,
    )
    if pending_start_plan is not None:
        pending = {
            key: value
            for key, value in pending.items()
            if key in set(pending_start_plan.pending_agent_message_item_ids_after)
        }
        started = set(pending_start_plan.started_agent_message_item_ids_after)

    fallback_start_item: TurnItem | None = None
    if item_id not in started:
        fallback_start_item = TurnItem.agent_message(
            AgentMessageItem(
                id=item_id,
                content=(),
                phase=None,
                memory_citation=None,
            )
        )
        started.add(item_id)
        pending.pop(item_id, None)

    started.discard(item_id)
    return SamplingPlanModeAgentMessageEmitPlan(
        item_id=item_id,
        text=text,
        pending_start_plan=pending_start_plan,
        fallback_start_item=fallback_start_item,
        should_emit_completed=True,
        started_agent_message_item_ids_after=tuple(sorted(started)),
        pending_agent_message_item_ids_after=tuple(sorted(pending)),
    )


def sampling_plan_mode_turn_item_emit_plan(
    turn_item: TurnItem,
    *,
    previously_active_item: TurnItem | None = None,
    pending_agent_message_items: object | None = None,
    started_agent_message_item_ids: object = (),
) -> SamplingPlanModeTurnItemEmitPlan:
    if not isinstance(turn_item, TurnItem):
        raise TypeError("turn_item must be a TurnItem")
    if previously_active_item is not None and not isinstance(previously_active_item, TurnItem):
        raise TypeError("previously_active_item must be a TurnItem or None")
    if turn_item.type == "AgentMessage":
        agent_message = turn_item.item
        if not isinstance(agent_message, AgentMessageItem):
            raise TypeError("AgentMessage turn items must contain AgentMessageItem")
        return SamplingPlanModeTurnItemEmitPlan(
            turn_item=turn_item,
            agent_message_plan=sampling_plan_mode_agent_message_emit_plan(
                agent_message,
                pending_agent_message_items=pending_agent_message_items,
                started_agent_message_item_ids=started_agent_message_item_ids,
            ),
        )
    return SamplingPlanModeTurnItemEmitPlan(
        turn_item=turn_item,
        should_emit_started=previously_active_item is None,
        should_emit_completed=True,
    )


def sampling_in_flight_tool_result_plan(
    result: object,
    *,
    memories_disable_on_external_context: bool = False,
) -> SamplingInFlightToolResultPlan:
    _ensure_bool(memories_disable_on_external_context, "memories_disable_on_external_context")
    if isinstance(result, BaseException):
        return SamplingInFlightToolResultPlan(
            error_message=f"in-flight tool future failed during drain: {result}",
            should_error_or_panic=True,
        )
    if not isinstance(result, ResponseInputItem):
        raise TypeError("result must be a ResponseInputItem or an exception")
    response_item = response_input_to_response_item(result)
    if response_item is None:
        raise ValueError("in-flight tool result could not be converted to a response item")
    return SamplingInFlightToolResultPlan(
        response_item=response_item,
        should_record_conversation_item=True,
        should_mark_thread_memory_mode_polluted=memories_disable_on_external_context
        and response_item_may_include_external_context(response_item),
    )


def _finish_tool_argument_diff_consumer_event(
    active_tool_argument_diff_consumer: tuple[str, object] | None,
) -> object | None:
    if active_tool_argument_diff_consumer is None:
        return None
    if (
        not isinstance(active_tool_argument_diff_consumer, tuple)
        or len(active_tool_argument_diff_consumer) != 2
        or not isinstance(active_tool_argument_diff_consumer[0], str)
    ):
        raise TypeError("active_tool_argument_diff_consumer must be a (call_id, consumer) tuple or None")
    finish = getattr(active_tool_argument_diff_consumer[1], "finish", None)
    if not callable(finish):
        return None
    try:
        return finish()
    except Exception:
        return None


def _extract_proposed_plan_text(text: str) -> str | None:
    _ensure_str(text, "text")
    return _tag_body(text, "proposed_plan")


def _parsed_field(parsed: object, name: str, default: object) -> object:
    if isinstance(parsed, dict):
        return parsed.get(name, default)
    return getattr(parsed, name, default)


def _payload_field(payload: object, name: str) -> object | None:
    if isinstance(payload, dict):
        return payload.get(name)
    return getattr(payload, name, None)


_SAMPLING_STREAM_EVENT_TYPE_ALIASES = {
    "response.created": "created",
    "response.output_item.done": "output_item_done",
    "response.output_item.added": "output_item_added",
    "response.output_text.delta": "output_text_delta",
    "response.custom_tool_call_input.delta": "tool_call_input_delta",
    "response.reasoning_summary_text.delta": "reasoning_summary_delta",
    "response.reasoning_summary_part.added": "reasoning_summary_part_added",
    "response.reasoning_text.delta": "reasoning_content_delta",
    "response.completed": "completed",
}


def _normalized_sampling_stream_event_type(event_type: str) -> str:
    return _SAMPLING_STREAM_EVENT_TYPE_ALIASES.get(event_type, event_type)


def _coalesce_delta(delta: str | None, payload: object) -> str:
    if delta is None:
        delta = _payload_field(payload, "delta")
    _ensure_str(delta, "delta")
    return delta


class AssistantMessageStreamParsers:
    """Per-item assistant text parsers for citation and proposed-plan markup."""

    def __init__(self, plan_mode: bool = False) -> None:
        _ensure_bool(plan_mode, "plan_mode")
        self._plan_mode = plan_mode
        self._parsers_by_item: dict[str, _AssistantTextStreamParser] = {}

    def _parser(self, item_id: str) -> "_AssistantTextStreamParser":
        _ensure_str(item_id, "item_id")
        parser = self._parsers_by_item.get(item_id)
        if parser is None:
            parser = _AssistantTextStreamParser(self._plan_mode)
            self._parsers_by_item[item_id] = parser
        return parser

    def seed_item_text(self, item_id: str, text: str) -> dict[str, object]:
        _ensure_str(text, "text")
        if text == "":
            return _empty_assistant_text_chunk()
        return self._parser(item_id).push_str(text)

    def parse_delta(self, item_id: str, delta: str) -> dict[str, object]:
        _ensure_str(delta, "delta")
        return self._parser(item_id).push_str(delta)

    def finish_item(self, item_id: str) -> dict[str, object]:
        _ensure_str(item_id, "item_id")
        parser = self._parsers_by_item.pop(item_id, None)
        if parser is None:
            return _empty_assistant_text_chunk()
        return parser.finish()

    def drain_finished(self) -> tuple[tuple[str, dict[str, object]], ...]:
        parsers = self._parsers_by_item
        self._parsers_by_item = {}
        return tuple((item_id, parser.finish()) for item_id, parser in parsers.items())


class _AssistantTextStreamParser:
    def __init__(self, plan_mode: bool) -> None:
        self._plan_mode = plan_mode
        self._citations = _CitationStreamParser()
        self._plan = _ProposedPlanStreamParser()

    def push_str(self, chunk: str) -> dict[str, object]:
        citation_chunk = self._citations.push_str(chunk)
        parsed = self._parse_visible_text(citation_chunk["visible_text"])
        parsed["citations"] = citation_chunk["citations"]
        return parsed

    def finish(self) -> dict[str, object]:
        citation_chunk = self._citations.finish()
        parsed = self._parse_visible_text(citation_chunk["visible_text"])
        if self._plan_mode:
            tail = self._plan.finish()
            parsed["visible_text"] += tail["visible_text"]
            parsed["plan_segments"] = tuple(parsed["plan_segments"]) + tuple(tail["plan_segments"])
        parsed["citations"] = citation_chunk["citations"]
        return parsed

    def _parse_visible_text(self, visible_text: str) -> dict[str, object]:
        if not self._plan_mode:
            return {"visible_text": visible_text, "citations": (), "plan_segments": ()}
        plan_chunk = self._plan.push_str(visible_text)
        return {
            "visible_text": plan_chunk["visible_text"],
            "citations": (),
            "plan_segments": plan_chunk["plan_segments"],
        }


class _CitationStreamParser:
    def __init__(self) -> None:
        self._pending = ""
        self._inside = False
        self._content = ""

    def push_str(self, chunk: str) -> dict[str, object]:
        text = self._pending + chunk
        self._pending = ""
        visible: list[str] = []
        citations: list[str] = []
        position = 0
        while position < len(text):
            if self._inside:
                end = text.find(CITATION_CLOSE, position)
                if end == -1:
                    suffix_start = _hidden_tag_suffix_start(text, position, CITATION_CLOSE)
                    self._content += text[position:suffix_start]
                    self._pending = text[suffix_start:]
                    return _assistant_citation_chunk("".join(visible), citations)
                self._content += text[position:end]
                citations.append(self._content)
                self._content = ""
                self._inside = False
                position = end + len(CITATION_CLOSE)
                continue

            start = text.find(CITATION_OPEN, position)
            if start != -1:
                visible.append(text[position:start])
                self._inside = True
                position = start + len(CITATION_OPEN)
                continue

            suffix_start = _hidden_tag_suffix_start(text, position, CITATION_OPEN)
            visible.append(text[position:suffix_start])
            self._pending = text[suffix_start:]
            break
        return _assistant_citation_chunk("".join(visible), citations)

    def finish(self) -> dict[str, object]:
        if self._inside:
            citation = self._content
            if self._pending:
                citation += self._pending
            self._pending = ""
            self._content = ""
            self._inside = False
            return _assistant_citation_chunk("", [citation])
        pending = self._pending
        self._pending = ""
        return _assistant_citation_chunk(pending, [])


class _ProposedPlanStreamParser:
    def __init__(self) -> None:
        self._pending = ""
        self._inside = False

    def push_str(self, chunk: str) -> dict[str, object]:
        self._pending += chunk
        visible: list[str] = []
        segments: list[tuple[str, str]] = []
        while self._pending:
            line_end = self._line_end_index(self._pending)
            if line_end is None:
                if self._pending_still_possible_tag():
                    break
                self._emit_text(self._pending, visible, segments)
                self._pending = ""
                break
            line = self._pending[:line_end]
            self._pending = self._pending[line_end:]
            self._process_line(line, visible, segments)
        return {"visible_text": "".join(visible), "plan_segments": tuple(segments)}

    def finish(self) -> dict[str, object]:
        visible: list[str] = []
        segments: list[tuple[str, str]] = []
        if self._pending:
            if self._inside and _line_without_newline_matches_tag(self._pending, PROPOSED_PLAN_CLOSE):
                segments.append(("proposed_plan_end", ""))
                self._inside = False
            elif not self._inside and _line_without_newline_matches_tag(self._pending, PROPOSED_PLAN_OPEN):
                segments.append(("proposed_plan_start", ""))
                segments.append(("proposed_plan_end", ""))
            else:
                self._emit_text(self._pending, visible, segments)
            self._pending = ""
        if self._inside:
            segments.append(("proposed_plan_end", ""))
            self._inside = False
        return {"visible_text": "".join(visible), "plan_segments": tuple(segments)}

    @staticmethod
    def _line_end_index(text: str) -> int | None:
        newline = text.find("\n")
        if newline == -1:
            return None
        return newline + 1

    def _pending_still_possible_tag(self) -> bool:
        if self._inside:
            return PROPOSED_PLAN_CLOSE.startswith(self._pending)
        return PROPOSED_PLAN_OPEN.startswith(self._pending) or self._pending == PROPOSED_PLAN_OPEN

    def _process_line(
        self,
        line: str,
        visible: list[str],
        segments: list[tuple[str, str]],
    ) -> None:
        if self._inside:
            if _line_matches_tag(line, PROPOSED_PLAN_CLOSE):
                segments.append(("proposed_plan_end", ""))
                self._inside = False
            else:
                segments.append(("proposed_plan_delta", line))
            return
        if _line_matches_tag(line, PROPOSED_PLAN_OPEN):
            segments.append(("proposed_plan_start", ""))
            self._inside = True
            return
        self._emit_text(line, visible, segments)

    def _emit_text(
        self,
        text: str,
        visible: list[str],
        segments: list[tuple[str, str]],
    ) -> None:
        if self._inside:
            segments.append(("proposed_plan_delta", text))
        else:
            visible.append(text)
            segments.append(("normal", text))


def _hidden_tag_suffix_start(text: str, start: int, tag_open: str) -> int:
    max_len = min(len(tag_open) - 1, len(text) - start)
    for length in range(max_len, 0, -1):
        suffix = text[len(text) - length :]
        if tag_open.startswith(suffix):
            return len(text) - length
    return len(text)


def _line_matches_tag(line: str, tag: str) -> bool:
    return line in {f"{tag}\n", f"{tag}\r\n"}


def _line_without_newline_matches_tag(line: str, tag: str) -> bool:
    return line == tag or line == f"{tag}\r"


def _assistant_citation_chunk(visible_text: str, citations: Sequence[str]) -> dict[str, object]:
    return {"visible_text": visible_text, "citations": tuple(citations)}


def _empty_assistant_text_chunk() -> dict[str, object]:
    return {"visible_text": "", "citations": (), "plan_segments": ()}


class _NoopAssistantMessageStreamParsers:
    def finish_item(self, item_id: str) -> object:
        _ensure_str(item_id, "item_id")
        return _empty_assistant_text_chunk()


def _parsed_str_sequence_field(parsed: object, name: str) -> tuple[str, ...]:
    value = _parsed_field(parsed, name, ())
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a list or tuple of strings")
    values = tuple(value)
    for item in values:
        _ensure_str(item, f"{name} item")
    return values


def _parsed_assistant_delta_is_empty(
    parsed: object,
    visible_text: str,
    citations: tuple[str, ...],
    plan_segments: object,
) -> bool:
    is_empty = _parsed_field(parsed, "is_empty", None)
    if callable(is_empty):
        return bool(is_empty())
    if isinstance(is_empty, bool):
        return is_empty
    return visible_text == "" and not citations and not plan_segments


def _normalized_plan_segments(segments: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(segments, (list, tuple)):
        raise TypeError("segments must be a list or tuple")
    normalized: list[tuple[str, str]] = []
    for segment in segments:
        if isinstance(segment, str):
            normalized.append((segment, ""))
        elif isinstance(segment, dict):
            segment_type = segment.get("type")
            delta = segment.get("delta", "")
            _ensure_str(segment_type, "segment type")
            _ensure_str(delta, "segment delta")
            normalized.append((segment_type, delta))
        elif isinstance(segment, tuple):
            if len(segment) == 1:
                segment_type, delta = segment[0], ""
            elif len(segment) == 2:
                segment_type, delta = segment
            else:
                raise TypeError("segment tuples must have one or two elements")
            _ensure_str(segment_type, "segment type")
            _ensure_str(delta, "segment delta")
            normalized.append((segment_type, delta))
        else:
            raise TypeError("segments must contain strings, tuples, or mappings")
    return tuple(normalized)


def _str_set(value: object, name: str) -> set[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise TypeError(f"{name} must be an iterable of strings")
    result: set[str] = set()
    for item in value:
        _ensure_str(item, name)
        result.add(item)
    return result


def _str_dict(value: object, name: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be a mapping of strings to strings")
    result: dict[str, str] = {}
    for key, item in value.items():
        _ensure_str(key, f"{name} key")
        _ensure_str(item, f"{name} value")
        result[key] = item
    return result


def _turn_item_dict(value: object, name: str) -> dict[str, TurnItem]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be a mapping of strings to TurnItem values")
    result: dict[str, TurnItem] = {}
    for key, item in value.items():
        _ensure_str(key, f"{name} key")
        if not isinstance(item, TurnItem):
            raise TypeError(f"{name} values must be TurnItem values")
        result[key] = item
    return result


def _streaming_active_item_or_none(
    active_item: TurnItem | None,
    active_item_is_streaming_to_client: bool,
) -> TurnItem | None:
    if active_item is not None and not isinstance(active_item, TurnItem):
        raise TypeError("active_item must be a TurnItem or None")
    _ensure_bool(active_item_is_streaming_to_client, "active_item_is_streaming_to_client")
    if active_item is None or not active_item_is_streaming_to_client:
        return None
    return active_item


def _agent_message_turn_item_with_text(turn_item: TurnItem, text: str) -> TurnItem:
    agent_message = turn_item.item
    if not isinstance(agent_message, AgentMessageItem):
        return turn_item
    return TurnItem.agent_message(
        replace(
            agent_message,
            content=(AgentMessageContent.text_content(text),),
        )
    )


async def handle_output_item_done(
    ctx: HandleOutputCtx,
    item: ResponseItem,
    previously_active_item: TurnItem | None = None,
) -> OutputItemResult:
    """Handle a completed model output item like Rust ``handle_output_item_done``."""

    if not isinstance(ctx, HandleOutputCtx):
        raise TypeError("ctx must be a HandleOutputCtx")
    _ensure_response_item(item)
    if previously_active_item is not None and not isinstance(previously_active_item, TurnItem):
        raise TypeError("previously_active_item must be a TurnItem or None")

    plan_mode = _turn_context_plan_mode(ctx.turn_context)
    try:
        call = ToolRouter.build_tool_call(item)
    except Exception as exc:
        return await _handle_tool_router_error(ctx, item, exc)

    if call is not None:
        lifecycle_plan = tool_call_lifecycle_plan(call, getattr(ctx.sess, "conversation_id", None))
        await _accept_mailbox_delivery_for_current_turn(ctx)
        await _emit_tool_call_lifecycle(ctx, lifecycle_plan)
        await record_completed_response_item(ctx.sess, ctx.turn_context, item)
        tool_future = _tool_future(ctx, call)
        return OutputItemResult(needs_follow_up=lifecycle_plan.needs_follow_up, tool_future=tool_future)

    unexpected_output = unexpected_tool_output_plan(item)
    if unexpected_output is not None:
        await _emit_unexpected_tool_output(ctx, unexpected_output)
        if unexpected_output.records_completed_response_item:
            await record_completed_response_item(ctx.sess, ctx.turn_context, item)
        return OutputItemResult(needs_follow_up=unexpected_output.needs_follow_up)

    finalized = await finalize_non_tool_response_item_with_contributors(
        ctx.sess,
        ctx.turn_context,
        ctx.turn_store,
        item,
        plan_mode,
    )
    if finalized is not None:
        if previously_active_item is None:
            await _emit_turn_item_started(ctx, _started_turn_item(finalized.turn_item))
        await _emit_turn_item_completed(ctx, finalized.turn_item)
        await record_completed_response_item_with_finalized_facts(ctx.sess, ctx.turn_context, item, finalized.facts)
        return OutputItemResult(last_agent_message=finalized.facts.last_agent_message)

    await record_completed_response_item(ctx.sess, ctx.turn_context, item)
    return OutputItemResult()


async def record_completed_response_item(sess: object, turn_context: object, item: ResponseItem) -> None:
    await record_completed_response_item_with_finalized_facts(sess, turn_context, item, None)


async def record_completed_response_item_with_finalized_facts(
    sess: object,
    turn_context: object,
    item: ResponseItem,
    finalized_facts: FinalizedTurnItemFacts | None,
) -> None:
    recording_plan = completed_response_item_recording_plan(
        item,
        _turn_context_plan_mode(turn_context),
        finalized_facts,
        memories_disable_on_external_context=_turn_context_memories_disable_on_external_context(turn_context),
    )
    recorder = getattr(sess, "record_conversation_items", None)
    if callable(recorder):
        await _maybe_await(recorder(turn_context, [item]))
    if recording_plan.defer_mailbox_delivery_to_next_turn:
        input_queue = getattr(sess, "input_queue", None)
        defer = getattr(input_queue, "defer_mailbox_delivery_to_next_turn", None)
        if callable(defer):
            await _maybe_await(defer(getattr(sess, "active_turn", None), getattr(turn_context, "sub_id", None)))
    await _apply_completed_response_item_memory_side_effects(sess, turn_context, recording_plan)


async def _handle_tool_router_error(ctx: HandleOutputCtx, item: ResponseItem, error: Exception) -> OutputItemResult:
    function_error = _coerce_function_call_error(error)
    plan = tool_call_error_handling_plan(function_error)
    if plan.fatal_message is not None:
        raise RuntimeError(plan.fatal_message)
    if plan.records_completed_response_item:
        await record_completed_response_item(ctx.sess, ctx.turn_context, item)
    if plan.response_item is not None:
        recorder = getattr(ctx.sess, "record_conversation_items", None)
        if callable(recorder):
            await _maybe_await(recorder(ctx.turn_context, [plan.response_item]))
    return OutputItemResult(needs_follow_up=plan.needs_follow_up)


def _ensure_str(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")


def _ensure_pathlike(value: object, name: str) -> None:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a path-like value")


def _ensure_bool(value: object, name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool")


def _ensure_non_negative_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _ensure_response_item(item: object) -> None:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")


def _event_type_and_payload(event: object) -> tuple[str | None, object]:
    if isinstance(event, dict):
        event_type = event.get("type")
        payload = event.get("payload", event)
    else:
        event_type = getattr(event, "type", None)
        payload = getattr(event, "payload", event)
    return (event_type if isinstance(event_type, str) else None, payload)


def _payload_get(payload: object, key: str) -> object:
    if isinstance(payload, dict):
        return payload.get(key)
    return getattr(payload, key, None)


def _turn_context_plan_mode(turn_context: object) -> bool:
    collaboration_mode = getattr(turn_context, "collaboration_mode", None)
    mode = getattr(collaboration_mode, "mode", collaboration_mode)
    value = getattr(mode, "value", mode)
    return str(value).lower() == "plan"


def _turn_context_memories_disable_on_external_context(turn_context: object) -> bool:
    config = getattr(turn_context, "config", None)
    memories = getattr(config, "memories", None)
    if memories is not None and hasattr(memories, "disable_on_external_context"):
        return bool(getattr(memories, "disable_on_external_context"))
    return bool(getattr(config, "memories_disable_on_external_context", False))


def _turn_item_contributors(sess: object) -> tuple[object, ...]:
    explicit = getattr(sess, "turn_item_contributors", None)
    if callable(explicit):
        explicit = explicit()
    if explicit is not None:
        return tuple(explicit)
    services = getattr(sess, "services", None)
    extensions = getattr(services, "extensions", None)
    getter = getattr(extensions, "turn_item_contributors", None)
    if callable(getter):
        return tuple(getter())
    return ()


def _thread_extension_data(sess: object) -> object | None:
    services = getattr(sess, "services", None)
    return getattr(services, "thread_extension_data", getattr(sess, "thread_extension_data", None))


def _run_turn_item_contributor(
    contributor: object,
    thread_extension_data: object | None,
    turn_store: object | None,
    item: TurnItem,
) -> object:
    contribute = getattr(contributor, "contribute", None)
    if callable(contribute):
        return contribute(thread_extension_data, turn_store, item)
    if callable(contributor):
        return contributor(item)
    return None


def _create_tool_argument_diff_consumer(tool_runtime: object | None, name: str) -> object | None:
    create_diff_consumer = getattr(tool_runtime, "create_diff_consumer", None)
    if not callable(create_diff_consumer):
        return None
    return create_diff_consumer(ToolName.plain(name))


async def _emit_tool_call_lifecycle(ctx: HandleOutputCtx, plan: ToolCallLifecyclePlan) -> None:
    emitter = getattr(ctx.sess, "record_tool_call_lifecycle", None)
    if callable(emitter):
        await _maybe_await(emitter(ctx.turn_context, plan))


async def _emit_unexpected_tool_output(ctx: HandleOutputCtx, plan: UnexpectedToolOutputPlan) -> None:
    emitter = getattr(ctx.sess, "record_unexpected_tool_output", None)
    if callable(emitter):
        await _maybe_await(emitter(ctx.turn_context, plan))


async def _apply_completed_response_item_memory_side_effects(
    sess: object,
    turn_context: object,
    recording_plan: CompletedResponseItemRecordingPlan,
) -> None:
    sub_id = getattr(turn_context, "sub_id", None)
    if recording_plan.mark_thread_memory_mode_polluted:
        marker = getattr(sess, "mark_thread_memory_mode_polluted", None)
        if callable(marker):
            await _maybe_await(marker(sub_id))
        else:
            services = getattr(sess, "services", None)
            state_db = getattr(services, "state_db", None)
            marker = getattr(state_db, "mark_thread_memory_mode_polluted", None)
            if callable(marker):
                thread_id = getattr(turn_context, "thread_id", getattr(sess, "thread_id", None))
                await _maybe_await(marker(thread_id))

    if recording_plan.memory_citation is not None:
        has_memory_citation = await _record_stage1_output_usage_for_memory_citation(sess, recording_plan.memory_citation)
        if not has_memory_citation:
            return
        recorder = getattr(sess, "record_memory_citation_for_turn", None)
        if callable(recorder):
            await _maybe_await(recorder(sub_id))


async def _record_stage1_output_usage_for_memory_citation(sess: object, memory_citation: object) -> bool:
    thread_ids = _thread_ids_from_memory_citation(memory_citation)
    if not thread_ids:
        return True
    services = getattr(sess, "services", None)
    state_db = getattr(services, "state_db", None)
    memories = getattr(state_db, "memories", None)
    if callable(memories):
        memories = memories()
    recorder = getattr(memories, "record_stage1_output_usage", None)
    if callable(recorder):
        await _maybe_await(recorder(thread_ids))
    return True


def _thread_ids_from_memory_citation(memory_citation: object) -> tuple[str, ...]:
    rollout_ids = getattr(memory_citation, "rollout_ids", None)
    if rollout_ids is None and isinstance(memory_citation, dict):
        rollout_ids = memory_citation.get("rolloutIds", memory_citation.get("rollout_ids"))
    if rollout_ids is None:
        return ()
    if isinstance(rollout_ids, str):
        return (rollout_ids,)
    if not isinstance(rollout_ids, (list, tuple)):
        return ()
    return tuple(rollout_id for rollout_id in rollout_ids if isinstance(rollout_id, str))


def _started_turn_item(turn_item: TurnItem) -> TurnItem:
    if turn_item.type != "ImageGeneration":
        return turn_item
    image = turn_item.item
    if isinstance(image, ImageGenerationItem):
        return TurnItem.image_generation(
            replace(
                image,
                status="in_progress",
                revised_prompt=None,
                result="",
                saved_path=None,
            )
        )
    return turn_item


async def _accept_mailbox_delivery_for_current_turn(ctx: HandleOutputCtx) -> None:
    input_queue = getattr(ctx.sess, "input_queue", None)
    accept = getattr(input_queue, "accept_mailbox_delivery_for_current_turn", None)
    if callable(accept):
        await _maybe_await(accept(getattr(ctx.sess, "active_turn", None), getattr(ctx.turn_context, "sub_id", None)))


def _tool_future(ctx: HandleOutputCtx, call: object) -> object | None:
    runtime = ctx.tool_runtime
    handler = getattr(runtime, "handle_tool_call", None)
    if not callable(handler):
        return None
    cancellation = _child_cancellation_token(ctx.cancellation_token)
    return handler(call, cancellation)


def _child_cancellation_token(cancellation_token: object | None) -> object | None:
    child_token = getattr(cancellation_token, "child_token", None)
    if callable(child_token):
        return child_token()
    return cancellation_token


async def _emit_turn_item_started(ctx: HandleOutputCtx, turn_item: TurnItem) -> None:
    emitter = getattr(ctx.sess, "emit_turn_item_started", None)
    if callable(emitter):
        await _maybe_await(emitter(ctx.turn_context, turn_item))


async def _emit_turn_item_completed(ctx: HandleOutputCtx, turn_item: TurnItem) -> None:
    emitter = getattr(ctx.sess, "emit_turn_item_completed", None)
    if callable(emitter):
        await _maybe_await(emitter(ctx.turn_context, turn_item))


def _coerce_function_call_error(error: Exception) -> FunctionCallError:
    if isinstance(error, FunctionCallError):
        return error
    kind = getattr(error, "kind", None)
    message = getattr(error, "message", str(error))
    if kind == "fatal":
        return FunctionCallError.fatal(message)
    if kind == "respond_to_model":
        return FunctionCallError.respond_to_model(message)
    raise error


async def _maybe_await(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "AssistantMessageStreamParsers",
    "CompletedResponseItemRecordingPlan",
    "FinalizedTurnItem",
    "FinalizedTurnItemFacts",
    "GENERATED_IMAGE_ARTIFACTS_DIR",
    "HandleOutputCtx",
    "OutputItemResult",
    "SamplingMailboxPreemptionPlan",
    "SamplingOutputItemAddedPlan",
    "SamplingOutputItemAddedApplyPlan",
    "SamplingOutputTextDeltaPlan",
    "SamplingOutputTextDeltaApplyPlan",
    "SamplingAssistantTextFlushPlan",
    "SamplingAssistantTextFlushAllPlan",
    "SamplingStreamedAssistantTextDeltaPlan",
    "SamplingOutputItemDoneTransitionPlan",
    "SamplingMetadataEventPlan",
    "SamplingMetadataEventApplyPlan",
    "SamplingCompletedEventPlan",
    "SamplingCompletedEventApplyPlan",
    "SamplingStreamEventDispatchPlan",
    "SamplingStreamEventApplyPlan",
    "SamplingPlanModeAssistantDonePlan",
    "SamplingPlanSegmentAction",
    "SamplingPlanSegmentsPlan",
    "SamplingProposedPlanCompletionPlan",
    "SamplingPendingAgentMessageStartPlan",
    "SamplingPlanModeAgentMessageEmitPlan",
    "SamplingPlanModeTurnItemEmitPlan",
    "SamplingInFlightToolResultPlan",
    "SamplingOutputState",
    "SamplingReasoningDeltaPlan",
    "SamplingReasoningDeltaApplyPlan",
    "SamplingToolCallInputDeltaPlan",
    "SamplingToolCallInputDeltaApplyPlan",
    "ToolCallErrorHandlingPlan",
    "ToolCallLifecyclePlan",
    "UnexpectedToolOutputPlan",
    "apply_turn_item_contributors",
    "completed_item_defers_mailbox_delivery_to_next_turn",
    "completed_response_item_recording_plan",
    "finalize_non_tool_response_item",
    "finalize_non_tool_response_item_with_contributors",
    "finalized_turn_item_facts",
    "function_call_error_output_result",
    "function_call_error_to_response_input",
    "agent_message_text",
    "handle_output_item_done",
    "handle_non_tool_response_item",
    "handle_non_tool_response_item_with_contributors",
    "image_generation_artifact_path",
    "get_last_assistant_message_from_turn",
    "last_assistant_message_from_item",
    "memory_citation_from_response_item",
    "raw_assistant_output_text_from_item",
    "realtime_text_for_event",
    "response_input_to_response_item",
    "response_item_may_include_external_context",
    "record_completed_response_item",
    "record_completed_response_item_with_finalized_facts",
    "sampling_item_preempts_for_mailbox_mail",
    "sampling_mailbox_preemption_plan",
    "sampling_output_item_added_plan",
    "sampling_output_item_added_apply_plan",
    "sampling_output_item_done_transition_plan",
    "sampling_output_text_delta_plan",
    "sampling_output_text_delta_apply_plan",
    "sampling_output_state_after_result",
    "sampling_assistant_text_flush_plan",
    "sampling_assistant_text_flush_all_plan",
    "sampling_streamed_assistant_text_delta_plan",
    "sampling_completed_event_plan",
    "sampling_completed_event_apply_plan",
    "sampling_stream_event_dispatch_plan",
    "sampling_metadata_event_plan",
    "sampling_metadata_event_apply_plan",
    "sampling_stream_event_apply_plan",
    "sampling_plan_mode_assistant_done_plan",
    "sampling_plan_segments_plan",
    "sampling_proposed_plan_completion_plan",
    "sampling_pending_agent_message_start_plan",
    "sampling_plan_mode_agent_message_emit_plan",
    "sampling_plan_mode_turn_item_emit_plan",
    "sampling_in_flight_tool_result_plan",
    "sampling_reasoning_content_delta_plan",
    "sampling_reasoning_delta_apply_plan",
    "sampling_reasoning_summary_delta_plan",
    "sampling_reasoning_summary_part_added_plan",
    "sampling_tool_call_input_delta_plan",
    "sampling_tool_call_input_delta_apply_plan",
    "save_image_generation_result",
    "strip_hidden_assistant_markup",
    "tool_call_error_handling_plan",
    "tool_call_lifecycle_plan",
    "unexpected_tool_output_plan",
]
