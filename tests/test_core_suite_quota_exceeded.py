
"""Parity test for Rust core/tests/suite/quota_exceeded.rs."""

from __future__ import annotations

import pytest

from pycodex.core.http_transport import _codex_err_from_responses_payload
from pycodex.core.session.turn.runtime import _send_terminal_error_event
from pycodex.protocol import CodexErr


class Session:
    def __init__(self) -> None:
        self.events = []

    async def send_event(self, turn_context, event) -> None:
        self.events.append((turn_context, event))


@pytest.mark.asyncio
async def test_quota_exceeded_emits_single_error_event() -> None:
    """Rust test: quota_exceeded_emits_single_error_event."""

    payload = {
        "type": "response.failed",
        "response": {
            "id": "resp-1",
            "error": {
                "code": "insufficient_quota",
                "message": "You exceeded your current quota, please check your plan and billing details.",
            },
        },
    }
    error = _codex_err_from_responses_payload(payload)
    assert isinstance(error, CodexErr)
    assert error.kind == "quota_exceeded"

    session = Session()
    turn_context = object()
    await _send_terminal_error_event(session, turn_context, error)

    error_events = [event for _turn, event in session.events if event.type == "error"]
    assert len(error_events) == 1
    assert error_events[0].payload.message == "Quota exceeded. Check your plan and billing details."
    assert error_events[0].payload.codex_error_info.type == "usage_limit_exceeded"
