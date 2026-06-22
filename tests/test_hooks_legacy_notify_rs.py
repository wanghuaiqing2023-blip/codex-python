"""Rust-derived tests for ``codex-hooks/src/legacy_notify.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/legacy_notify.rs``

Rust tests mirrored:
- ``tests::test_user_notification``
- ``tests::legacy_notify_json_matches_historical_wire_shape``
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime
from datetime import timezone
from pathlib import PurePosixPath

from pycodex.hooks import HookEvent
from pycodex.hooks import HookEventAfterAgent
from pycodex.hooks import HookPayload
from pycodex.hooks import HookResult
from pycodex.hooks import HookResultKind
from pycodex.hooks import legacy_notify_json
from pycodex.hooks import notify_hook
from pycodex.protocol import ThreadId


def _payload(*, client: str | None = "codex-tui") -> HookPayload:
    return HookPayload(
        session_id=ThreadId.from_string("aaaaaaaa-1111-2222-3333-444455556666"),
        cwd=PurePosixPath("/Users/example/project"),
        client=client,
        triggered_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        hook_event=HookEvent.AfterAgent(
            HookEventAfterAgent(
                thread_id=ThreadId.from_string("b5f6c1c2-1111-2222-3333-444455556666"),
                turn_id="12345",
                input_messages=["Rename `foo` to `bar` and update the callsites."],
                last_assistant_message="Rename complete and verified `cargo build` succeeds.",
            )
        ),
    )


def test_user_notification_serializes_historical_wire_shape() -> None:
    # Rust crate/module/test: codex-hooks/src/legacy_notify.rs
    # tests::test_user_notification.
    # Contract: the legacy notification is kebab-case, internally tagged as
    # "agent-turn-complete", and preserves the historical field names.
    actual = json.loads(legacy_notify_json(_payload()))

    assert actual == {
        "type": "agent-turn-complete",
        "thread-id": "b5f6c1c2-1111-2222-3333-444455556666",
        "turn-id": "12345",
        "cwd": "/Users/example/project",
        "client": "codex-tui",
        "input-messages": ["Rename `foo` to `bar` and update the callsites."],
        "last-assistant-message": "Rename complete and verified `cargo build` succeeds.",
    }


def test_legacy_notify_json_matches_payload_after_agent_event() -> None:
    # Rust crate/module/test: codex-hooks/src/legacy_notify.rs
    # tests::legacy_notify_json_matches_historical_wire_shape.
    # Contract: legacy_notify_json projects HookPayload::AfterAgent into the
    # historical UserNotification::AgentTurnComplete JSON payload.
    serialized = legacy_notify_json(_payload())

    assert json.loads(serialized) == {
        "type": "agent-turn-complete",
        "thread-id": "b5f6c1c2-1111-2222-3333-444455556666",
        "turn-id": "12345",
        "cwd": "/Users/example/project",
        "client": "codex-tui",
        "input-messages": ["Rename `foo` to `bar` and update the callsites."],
        "last-assistant-message": "Rename complete and verified `cargo build` succeeds.",
    }


def test_legacy_notify_json_omits_absent_client() -> None:
    # Rust crate/module/source contract: codex-hooks/src/legacy_notify.rs
    # UserNotification::AgentTurnComplete marks client with
    # skip_serializing_if = "Option::is_none".
    actual = json.loads(legacy_notify_json(_payload(client=None)))

    assert "client" not in actual


def test_notify_hook_empty_argv_succeeds_without_spawn(monkeypatch) -> None:
    # Rust crate/module/source contract: codex-hooks/src/legacy_notify.rs
    # notify_hook returns HookResult::Success when command_from_argv returns None.
    def fail_popen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("empty argv should not spawn")

    monkeypatch.setattr(subprocess, "Popen", fail_popen)

    response = asyncio.run(notify_hook([]).execute(_payload()))

    assert response.hook_name == "legacy_notify"
    assert response.result == HookResult.Success()


def test_notify_hook_spawn_error_failed_continue(monkeypatch) -> None:
    # Rust crate/module/source contract: codex-hooks/src/legacy_notify.rs
    # notify_hook maps command.spawn() errors to HookResult::FailedContinue.
    def fail_popen(*_args: object, **_kwargs: object) -> None:
        raise OSError("boom")

    monkeypatch.setattr(subprocess, "Popen", fail_popen)

    response = asyncio.run(notify_hook(["notify-bin"]).execute(_payload()))

    assert response.hook_name == "legacy_notify"
    assert response.result.kind == HookResultKind.FAILED_CONTINUE
    assert isinstance(response.result.error, OSError)
