"""Rust-derived tests for ``codex-hooks/src/types.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/types.rs``

Rust test mirrored:
- ``hook_payload_serializes_stable_wire_shape``
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime
from datetime import timezone
from pathlib import PurePosixPath

from pycodex.hooks import Hook
from pycodex.hooks import HookEvent
from pycodex.hooks import HookEventAfterAgent
from pycodex.hooks import HookPayload
from pycodex.hooks import HookResult


class HooksTypesRsTests(unittest.TestCase):
    def test_hook_payload_serializes_stable_wire_shape(self) -> None:
        # Rust crate/module/test: codex-hooks/src/types.rs
        # tests::hook_payload_serializes_stable_wire_shape.
        # Contract: HookPayload serializes with snake_case field names,
        # second-precision UTC timestamps, no absent client field, and a
        # nested internally-tagged hook_event object.
        payload = HookPayload(
            session_id="session-1",
            cwd=PurePosixPath("/tmp"),
            client=None,
            triggered_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            hook_event=HookEvent.AfterAgent(
                HookEventAfterAgent(
                    thread_id="thread-1",
                    turn_id="turn-1",
                    input_messages=["hello"],
                    last_assistant_message="hi",
                )
            ),
        )

        self.assertEqual(
            payload.to_mapping(),
            {
                "session_id": "session-1",
                "cwd": "/tmp",
                "triggered_at": "2025-01-01T00:00:00Z",
                "hook_event": {
                    "event_type": "after_agent",
                    "thread_id": "thread-1",
                    "turn_id": "turn-1",
                    "input_messages": ["hello"],
                    "last_assistant_message": "hi",
                },
            },
        )

    def test_hook_result_abort_and_default_hook_execute(self) -> None:
        # Rust crate/module: codex-hooks/src/types.rs
        # Contract: only FailedAbort aborts operation; Hook::default has name
        # "default" and returns HookResult::Success from execute().
        self.assertFalse(HookResult.Success().should_abort_operation())
        self.assertFalse(HookResult.FailedContinue("soft").should_abort_operation())
        self.assertTrue(HookResult.FailedAbort("hard").should_abort_operation())

        payload = HookPayload(
            session_id="session-1",
            cwd=PurePosixPath("/tmp"),
            client=None,
            triggered_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            hook_event=HookEvent.AfterAgent(
                HookEventAfterAgent("thread-1", "turn-1", [], None)
            ),
        )
        response = asyncio.run(Hook().execute(payload))

        self.assertEqual(response.hook_name, "default")
        self.assertEqual(response.result, HookResult.Success())


if __name__ == "__main__":
    unittest.main()
