from __future__ import annotations

import unittest

from pycodex.core.context import UserInstructions
from pycodex.core.thread_rollout_truncation import (
    USIZE_MAX,
    fork_turn_positions_in_rollout,
    initial_history_has_prior_user_turns,
    is_user_turn_boundary,
    truncate_rollout_before_nth_user_message_from_start,
    truncate_rollout_to_last_n_fork_turns,
    user_message_positions_in_rollout,
)
from pycodex.protocol import (
    AgentPath,
    EventMsg,
    InitialHistory,
    InterAgentCommunication,
    RolloutItem,
    ThreadRolledBackEvent,
)
from pycodex.protocol.models import ContentItem, ResponseItem


def user_msg(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.output_text(text),))


def assistant_msg(text: str) -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


def inter_agent_msg(text: str, trigger_turn: bool) -> ResponseItem:
    communication = InterAgentCommunication(
        author=AgentPath.root(),
        recipient=AgentPath.from_string("/root/worker"),
        other_recipients=(),
        content=text,
        trigger_turn=trigger_turn,
    )
    return ResponseItem.from_response_input_item(communication.to_response_input_item())


def response_item(item: ResponseItem) -> RolloutItem:
    return RolloutItem.response_item(item)


def rollback(num_turns: int) -> RolloutItem:
    return RolloutItem.event_msg(EventMsg.with_payload("thread_rolled_back", ThreadRolledBackEvent(num_turns)))


class ThreadRolloutTruncationTests(unittest.TestCase):
    def test_inter_agent_communication_round_trips_through_message_content(self) -> None:
        communication = InterAgentCommunication(
            author=AgentPath.root(),
            recipient=AgentPath.from_string("/root/worker"),
            other_recipients=(AgentPath.from_string("/root/reviewer"),),
            content="please continue",
            trigger_turn=True,
        )
        item = communication.to_response_input_item()

        self.assertEqual(item.role, "assistant")
        self.assertTrue(InterAgentCommunication.is_message_content(item.content))
        self.assertEqual(InterAgentCommunication.from_message_content(item.content), communication)
        self.assertIsNone(InterAgentCommunication.from_message_content((ContentItem.output_text("{"),)))

    def test_initial_history_detects_prior_user_turns(self) -> None:
        self.assertFalse(initial_history_has_prior_user_turns(InitialHistory.new()))
        self.assertTrue(
            initial_history_has_prior_user_turns(
                InitialHistory.forked((response_item(user_msg("feature request")),))
            )
        )

    def test_user_turn_boundary_ignores_contextual_user_fragments(self) -> None:
        contextual = UserInstructions(".", "always be brief").into_response_item()

        self.assertFalse(is_user_turn_boundary(contextual))
        self.assertTrue(is_user_turn_boundary(user_msg("real request")))
        self.assertTrue(is_user_turn_boundary(inter_agent_msg("worker instruction", trigger_turn=False)))

    def test_truncates_rollout_from_start_before_nth_real_user_message(self) -> None:
        contextual = response_item(UserInstructions(".", "persist").into_response_item())
        rollout = [
            contextual,
            response_item(user_msg("u1")),
            response_item(assistant_msg("a1")),
            response_item(assistant_msg("a2")),
            response_item(user_msg("u2")),
            response_item(assistant_msg("a3")),
        ]

        self.assertEqual(user_message_positions_in_rollout(rollout), [1, 4])
        self.assertEqual(
            truncate_rollout_before_nth_user_message_from_start(rollout, 1),
            rollout[:4],
        )
        self.assertEqual(
            truncate_rollout_before_nth_user_message_from_start(rollout, 2),
            rollout,
        )
        self.assertEqual(
            truncate_rollout_before_nth_user_message_from_start(rollout, USIZE_MAX),
            rollout,
        )

    def test_truncates_rollout_from_start_applies_thread_rollback_markers(self) -> None:
        rollout = [
            response_item(user_msg("u1")),
            response_item(assistant_msg("a1")),
            response_item(user_msg("u2")),
            response_item(assistant_msg("a2")),
            rollback(1),
            response_item(user_msg("u3")),
            response_item(assistant_msg("a3")),
            response_item(user_msg("u4")),
            response_item(assistant_msg("a4")),
        ]

        self.assertEqual(user_message_positions_in_rollout(rollout), [0, 5, 7])
        self.assertEqual(
            truncate_rollout_before_nth_user_message_from_start(rollout, 2),
            rollout[:7],
        )

    def test_truncates_rollout_to_last_n_fork_turns_counts_trigger_turn_messages(self) -> None:
        rollout = [
            response_item(user_msg("u1")),
            response_item(assistant_msg("a1")),
            response_item(inter_agent_msg("queued message", trigger_turn=False)),
            response_item(assistant_msg("a2")),
            response_item(inter_agent_msg("triggered task", trigger_turn=True)),
            response_item(assistant_msg("a3")),
            response_item(user_msg("u2")),
            response_item(assistant_msg("a4")),
        ]

        self.assertEqual(fork_turn_positions_in_rollout(rollout), [0, 4, 6])
        self.assertEqual(truncate_rollout_to_last_n_fork_turns(rollout, 2), rollout[4:])
        self.assertEqual(truncate_rollout_to_last_n_fork_turns(rollout, 0), [])

    def test_fork_turn_truncation_applies_rollback_to_instruction_turns(self) -> None:
        rollout = [
            response_item(user_msg("u1")),
            response_item(user_msg("u2")),
            response_item(inter_agent_msg("triggered task", trigger_turn=True)),
            response_item(assistant_msg("a1")),
            rollback(1),
            response_item(user_msg("u3")),
            response_item(assistant_msg("a2")),
        ]

        self.assertEqual(fork_turn_positions_in_rollout(rollout), [0, 1, 5])
        self.assertEqual(truncate_rollout_to_last_n_fork_turns(rollout, 2), rollout[1:])
        self.assertEqual(truncate_rollout_to_last_n_fork_turns(rollout, 1), rollout[5:])

    def test_rollout_mapping_payloads_are_supported(self) -> None:
        rollout = [
            response_item(user_msg("u1")).to_mapping(),
            response_item(assistant_msg("a1")).to_mapping(),
            rollback(1).to_mapping(),
            response_item(user_msg("u2")).to_mapping(),
        ]

        self.assertEqual(user_message_positions_in_rollout(rollout), [3])


if __name__ == "__main__":
    unittest.main()
