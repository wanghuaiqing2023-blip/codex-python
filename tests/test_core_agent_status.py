from __future__ import annotations

import unittest

from pycodex.core import agent_status_from_event, agent_status_is_final, is_final
from pycodex.protocol import (
    AgentStatus,
    ErrorEvent,
    EventMsg,
    TurnAbortReason,
    TurnAbortedEvent,
    TurnCompleteEvent,
    TurnStartedEvent,
)


class AgentStatusTests(unittest.TestCase):
    def test_agent_status_from_turn_started(self) -> None:
        event = EventMsg.with_payload(
            "task_started",
            TurnStartedEvent(turn_id="turn-1", model_context_window=None),
        )

        self.assertEqual(agent_status_from_event(event), AgentStatus.running())

    def test_agent_status_from_turn_complete(self) -> None:
        event = EventMsg.with_payload(
            "task_complete",
            TurnCompleteEvent(turn_id="turn-1", last_agent_message="done"),
        )

        self.assertEqual(agent_status_from_event(event), AgentStatus.completed("done"))

    def test_agent_status_from_legacy_mapping_aliases(self) -> None:
        event = {"type": "turn_complete", "turn_id": "turn-1", "last_agent_message": "legacy done"}

        self.assertEqual(agent_status_from_event(event), AgentStatus.completed("legacy done"))

    def test_agent_status_from_interrupted_and_budget_abort(self) -> None:
        for reason in (TurnAbortReason.INTERRUPTED, TurnAbortReason.BUDGET_LIMITED):
            event = EventMsg.with_payload(
                "turn_aborted",
                TurnAbortedEvent(turn_id="turn-1", reason=reason),
            )
            self.assertEqual(agent_status_from_event(event), AgentStatus.interrupted())

    def test_agent_status_from_non_interrupting_abort(self) -> None:
        event = EventMsg.with_payload(
            "turn_aborted",
            TurnAbortedEvent(turn_id="turn-1", reason=TurnAbortReason.REVIEW_ENDED),
        )

        self.assertEqual(agent_status_from_event(event), AgentStatus.errored("ReviewEnded"))

    def test_agent_status_from_error_and_shutdown(self) -> None:
        self.assertEqual(
            agent_status_from_event(EventMsg.with_payload("error", ErrorEvent("boom"))),
            AgentStatus.errored("boom"),
        )
        self.assertEqual(
            agent_status_from_event(EventMsg.with_payload("shutdown_complete")),
            AgentStatus.shutdown(),
        )

    def test_agent_status_ignores_unrelated_events(self) -> None:
        self.assertIsNone(agent_status_from_event(EventMsg.with_payload("agent_message", {"message": "hello"})))

    def test_agent_status_is_final(self) -> None:
        self.assertFalse(agent_status_is_final(AgentStatus.pending_init()))
        self.assertFalse(agent_status_is_final("running"))
        self.assertFalse(is_final(AgentStatus.interrupted()))
        self.assertTrue(agent_status_is_final(AgentStatus.completed(None)))
        self.assertTrue(agent_status_is_final({"errored": "boom"}))
        self.assertTrue(agent_status_is_final("shutdown"))


if __name__ == "__main__":
    unittest.main()
