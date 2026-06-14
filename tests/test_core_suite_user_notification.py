import json
from datetime import datetime, timezone

from pycodex.hooks import HookEvent, HookEventAfterAgent, HookPayload, legacy_notify_json


def test_summarize_context_three_requests_and_instructions(tmp_path):
    # Rust: core/tests/suite/user_notification.rs::summarize_context_three_requests_and_instructions.
    payload = HookPayload(
        session_id="session-1",
        cwd=tmp_path,
        client="codex-tui",
        triggered_at=datetime(2026, 6, 11, 8, 17, 0, tzinfo=timezone.utc),
        hook_event=HookEvent.AfterAgent(
            HookEventAfterAgent(
                thread_id="thread-1",
                turn_id="turn-1",
                input_messages=["hello world"],
                last_assistant_message="Done",
            )
        ),
    )

    notify_payload = json.loads(legacy_notify_json(payload))

    assert notify_payload["type"] == "agent-turn-complete"
    assert notify_payload["input-messages"] == ["hello world"]
    assert notify_payload["last-assistant-message"] == "Done"
