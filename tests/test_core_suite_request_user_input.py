import asyncio
import json

import pytest

from pycodex.core.codex_delegate import CancellationToken, await_user_input_with_cancel
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.core.tools.handlers.request_user_input import (
    RequestUserInputHandler,
    request_user_input_available_modes,
)
from pycodex.protocol import ModeKind
from pycodex.protocol.request_user_input import (
    RequestUserInputAnswer,
    RequestUserInputQuestion,
    RequestUserInputQuestionOption,
    RequestUserInputResponse,
)


def _request_args_json() -> str:
    return json.dumps(
        {
            "questions": [
                {
                    "id": "confirm_path",
                    "header": "Confirm",
                    "question": "Proceed with the plan?",
                    "options": [
                        {
                            "label": "Yes (Recommended)",
                            "description": "Continue the current plan.",
                        },
                        {
                            "label": "No",
                            "description": "Stop and revisit the approach.",
                        },
                    ],
                }
            ]
        }
    )


def _answer() -> RequestUserInputResponse:
    return RequestUserInputResponse(
        {"confirm_path": RequestUserInputAnswer(("yes",))}
    )


def _run_handler(mode: ModeKind, *, default_mode_enabled: bool = False):
    captured = {}

    def callback(call_id, args):
        captured["call_id"] = call_id
        captured["args"] = args
        return _answer()

    handler = RequestUserInputHandler(
        available_modes=request_user_input_available_modes(
            default_mode_enabled=default_mode_enabled
        ),
        request_callback=callback,
    )
    output = handler.handle(
        ToolPayload.function(_request_args_json()),
        call_id="user-input-call",
        mode=mode,
    )
    return output, captured


def test_request_user_input_round_trip_resolves_pending():
    # Rust: codex/codex-rs/core/tests/suite/request_user_input.rs
    # Test: request_user_input_round_trip_resolves_pending.
    output, captured = _run_handler(ModeKind.PLAN)

    assert captured["call_id"] == "user-input-call"
    assert captured["args"].questions[0].is_other is True
    assert json.loads(output.into_text()) == {
        "answers": {"confirm_path": {"answers": ["yes"]}}
    }


def test_request_user_input_interrupt_emits_deferred_token_count():
    # Rust: request_user_input_interrupt_emits_deferred_token_count.
    # The Rust end-to-end test also checks delayed TokenCount emission. The local
    # behavior boundary is that cancellation resolves the pending input with an
    # empty answer and notifies the parent session so the turn can continue/abort.
    notified = []

    class ParentSession:
        async def notify_user_input_response(self, sub_id, response):
            notified.append((sub_id, response))

    async def never_returns():
        await asyncio.sleep(60)

    async def scenario():
        token = CancellationToken()
        task = asyncio.create_task(
            await_user_input_with_cancel(
                never_returns(),
                ParentSession(),
                "turn-1",
                token,
            )
        )
        await asyncio.sleep(0)
        token.cancel()
        return await task

    response = asyncio.run(scenario())

    assert response == RequestUserInputResponse({})
    assert notified == [("turn-1", RequestUserInputResponse({}))]


def test_request_user_input_rejected_in_execute_mode_alias():
    # Rust: request_user_input_rejected_in_execute_mode_alias.
    with pytest.raises(FunctionCallError) as err:
        _run_handler(ModeKind.EXECUTE)
    assert err.value.kind == "respond_to_model"
    assert "request_user_input is unavailable in Execute mode" in str(err.value)


def test_request_user_input_rejected_in_default_mode_by_default():
    # Rust: request_user_input_rejected_in_default_mode_by_default.
    with pytest.raises(FunctionCallError) as err:
        _run_handler(ModeKind.DEFAULT)
    assert err.value.kind == "respond_to_model"
    assert "request_user_input is unavailable in Default mode" in str(err.value)


def test_request_user_input_round_trip_in_default_mode_with_feature():
    # Rust: request_user_input_round_trip_in_default_mode_with_feature.
    output, captured = _run_handler(ModeKind.DEFAULT, default_mode_enabled=True)

    assert captured["args"].questions == (
        RequestUserInputQuestion(
            id="confirm_path",
            header="Confirm",
            question="Proceed with the plan?",
            is_other=True,
            options=(
                RequestUserInputQuestionOption(
                    "Yes (Recommended)",
                    "Continue the current plan.",
                ),
                RequestUserInputQuestionOption(
                    "No",
                    "Stop and revisit the approach.",
                ),
            ),
        ),
    )
    assert json.loads(output.into_text()) == {
        "answers": {"confirm_path": {"answers": ["yes"]}}
    }


def test_request_user_input_rejected_in_pair_mode_alias():
    # Rust: request_user_input_rejected_in_pair_mode_alias.
    with pytest.raises(FunctionCallError) as err:
        _run_handler(ModeKind.PAIR_PROGRAMMING)
    assert err.value.kind == "respond_to_model"
    assert "request_user_input is unavailable in Pair Programming mode" in str(err.value)
