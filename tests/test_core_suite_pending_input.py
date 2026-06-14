
"""Parity tests for Rust core/tests/suite/pending_input.rs.

These tests derive from the Rust pending-input suite and exercise the
Python turn runtime behavior contract around queued user input, queued
agent-mail-like response items, model continuations, and mid-turn compaction.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pycodex.core.client import ModelClient
from pycodex.core.session.turn.runtime import run_user_turn_sampling_from_session
from pycodex.protocol import ContentItem, ResponseItem, UserInput
from tests.test_core_turn_runtime import PendingInputQueue, Router, Session


class _State:
    def __init__(self) -> None:
        self.recent_tokens = None
        self.compact_calls: list[list[ResponseItem]] = []


class _ModelInfo:
    slug = "gpt-test"
    supports_reasoning_summaries = False
    support_verbosity = False

    @staticmethod
    def service_tier_for_request(service_tier):
        return service_tier


_PROVIDER = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
_MODEL_INFO = _ModelInfo()
_CLIENT = ModelClient(session_id="session", thread_id="thread", installation_id="install")


def _input_items(request):
    return request.request_plan.request["input"]


def _input_texts(request) -> list[str]:
    texts: list[str] = []
    for item in _input_items(request):
        if item.type != "message":
            continue
        for content in item.content:
            text = getattr(content, "text", None)
            if text is not None:
                texts.append(text)
    return texts


def _assistant_message(text: str) -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


def _user_message(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def _reasoning_item(text: str = "thinking") -> ResponseItem:
    return ResponseItem.reasoning("reasoning-1", summary=(text,))


async def _run_turn(sampler, *, state: _State | None = None) -> tuple[list[object], _State]:
    state = state or _State()
    session = Session()
    session.input_queue = PendingInputQueue()
    session.model_client = _CLIENT
    session.model_info = _MODEL_INFO
    session.provider = _PROVIDER

    token_statuses = []
    if state.recent_tokens is not None:
        token_statuses = [
            SimpleNamespace(token_limit_reached=False),
            SimpleNamespace(token_limit_reached=True),
            SimpleNamespace(token_limit_reached=False),
        ]

    async def auto_compact_token_status(_turn_context):
        if token_statuses:
            return token_statuses.pop(0)
        return SimpleNamespace(token_limit_reached=False)

    async def run_auto_compact(turn_context, *, initial_context_injection, reason, phase):
        state.compact_calls.append((turn_context, initial_context_injection, reason, phase))

    session.auto_compact_token_status = auto_compact_token_status
    session.run_auto_compact = run_auto_compact

    outputs = await run_user_turn_sampling_from_session(
        session,
        (UserInput.text_input("first prompt"),),
        _CLIENT,
        _PROVIDER,
        _MODEL_INFO,
        sampler,
        built_tools=lambda _sess, _turn: Router(),
    )
    return outputs, state


@pytest.mark.asyncio
async def test_injected_user_input_triggers_follow_up_request_with_deltas():
    # Rust: injected_user_input_triggers_follow_up_request_with_deltas.
    requests = []
    queued = False

    async def sampler(request):
        nonlocal queued
        requests.append(request)
        if not queued:
            queued = True
            request.session.input_queue.items.append(UserInput.text_input("second prompt"))
            return [_assistant_message("partial answer")]
        return [_assistant_message("follow-up answer")]

    await _run_turn(sampler)

    assert len(requests) == 2
    assert _input_texts(requests[0])[-1] == "first prompt"
    assert _input_texts(requests[1])[-1] == "second prompt"


@pytest.mark.asyncio
async def test_queued_inter_agent_mail_triggers_follow_up_after_reasoning_item():
    # Rust: queued_inter_agent_mail_triggers_follow_up_after_reasoning_item.
    requests = []
    queued_mail = _user_message("child agent update")

    async def sampler(request):
        requests.append(request)
        if len(requests) == 1:
            request.session.input_queue.items.append({"type": "response_item", "item": queued_mail})
            return [_reasoning_item("model reasoning before mail")]
        return [_assistant_message("mail handled")]

    await _run_turn(sampler)

    assert len(requests) == 2
    assert _input_texts(requests[0])[-1] == "first prompt"
    assert _input_items(requests[1])[-1] == queued_mail


@pytest.mark.asyncio
async def test_queued_inter_agent_mail_triggers_follow_up_after_commentary_message_item():
    # Rust: queued_inter_agent_mail_triggers_follow_up_after_commentary_message_item.
    requests = []
    queued_mail = _user_message("commentary child update")

    async def sampler(request):
        requests.append(request)
        if len(requests) == 1:
            request.session.input_queue.items.append({"type": "response_item", "item": queued_mail})
            return [_assistant_message("commentary before mail")]
        return [_assistant_message("mail handled")]

    await _run_turn(sampler)

    assert len(requests) == 2
    assert _input_texts(requests[0])[-1] == "first prompt"
    assert _input_items(requests[1])[-1] == queued_mail


@pytest.mark.asyncio
async def test_user_input_does_not_preempt_after_reasoning_item():
    # Rust: user_input_does_not_preempt_after_reasoning_item.
    requests = []

    async def sampler(request):
        requests.append(request)
        if len(requests) == 1:
            request.session.input_queue.items.append(UserInput.text_input("queued steer"))
            return SimpleNamespace(response_items=(_reasoning_item(),), stream_events=({"type": "completed", "response_id": "r1", "end_turn": False},))
        if len(requests) == 2:
            return [_assistant_message("model continuation finished")]
        return [_assistant_message("queued steer handled")]

    await _run_turn(sampler)

    assert len(requests) == 3
    assert "queued steer" not in _input_texts(requests[1])
    assert _input_texts(requests[2])[-1] == "queued steer"


@pytest.mark.asyncio
async def test_steered_user_input_waits_for_model_continuation_after_mid_turn_compact():
    # Rust: steered_user_input_waits_for_model_continuation_after_mid_turn_compact.
    requests = []
    state = _State()
    state.recent_tokens = {"input_tokens": 6000}

    async def sampler(request):
        requests.append(request)
        if len(requests) == 1:
            request.session.input_queue.items.append(UserInput.text_input("pending steer"))
            return SimpleNamespace(response_items=(_assistant_message("needs continuation"),), stream_events=({"type": "completed", "response_id": "r1", "end_turn": False},))
        if len(requests) == 2:
            return [_assistant_message("continuation after compact")]
        return [_assistant_message("steer handled")]

    _, state = await _run_turn(sampler, state=state)

    assert len(requests) == 3
    assert state.compact_calls
    assert "pending steer" not in _input_texts(requests[1])
    assert _input_texts(requests[2])[-1] == "pending steer"


@pytest.mark.asyncio
async def test_steered_user_input_follows_compact_when_only_the_steer_needs_follow_up():
    # Rust: steered_user_input_follows_compact_when_only_the_steer_needs_follow_up.
    requests = []
    state = _State()
    state.recent_tokens = {"input_tokens": 6000}

    async def sampler(request):
        requests.append(request)
        if len(requests) == 1:
            request.session.input_queue.items.append(UserInput.text_input("pending steer"))
            return [_assistant_message("turn complete before steer")]
        return [_assistant_message("steer handled")]

    _, state = await _run_turn(sampler, state=state)

    assert len(requests) == 2
    assert state.compact_calls
    assert state.compact_calls[0][2:] == ("context_limit", "mid_turn")
    assert _input_texts(requests[1])[-1] == "pending steer"


@pytest.mark.asyncio
async def test_steered_user_input_waits_when_tool_output_triggers_compact_before_next_request():
    # Rust: steered_user_input_waits_when_tool_output_triggers_compact_before_next_request.
    requests = []
    state = _State()
    state.recent_tokens = {"input_tokens": 6000}

    async def sampler(request):
        requests.append(request)
        if len(requests) == 1:
            request.session.input_queue.items.append(UserInput.text_input("pending steer"))
            return SimpleNamespace(response_items=(_assistant_message("tool output consumed; continue"),), stream_events=({"type": "completed", "response_id": "r1", "end_turn": False},))
        if len(requests) == 2:
            return [_assistant_message("model continuation after tool compact")]
        return [_assistant_message("steer handled")]

    _, state = await _run_turn(sampler, state=state)

    assert len(requests) == 3
    assert state.compact_calls
    assert "pending steer" not in _input_texts(requests[1])
    assert _input_texts(requests[2])[-1] == "pending steer"
