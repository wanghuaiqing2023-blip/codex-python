import unittest
from types import SimpleNamespace

from pycodex.core.context import NetworkRuleSaved
from pycodex.core.goals import goal_token_delta_for_usage, should_ignore_goal_for_mode, validate_goal_budget
from pycodex.core.session.runtime import InMemoryInputQueue
from pycodex.core.state.turn import MailboxDeliveryPhase, TurnState
from pycodex.core.stream_events_utils import AssistantMessageStreamParsers
from pycodex.protocol import (
    InterAgentCommunication,
    ModeKind,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    ResponseItem,
    TokenUsage,
)


class CoreSessionRootParityTests(unittest.IsolatedAsyncioTestCase):
    def test_assistant_message_stream_parsers_seed_and_finish_like_session_tests(self) -> None:
        # Rust source: codex/codex-rs/core/src/session/tests.rs
        # Rust tests: assistant_message_stream_parsers_can_be_seeded_from_output_item_added_text,
        # assistant_message_stream_parsers_seed_buffered_prefix_stays_out_of_finish_tail,
        # assistant_message_stream_parsers_seed_plan_parser_across_added_and_delta_boundaries.
        parsers = AssistantMessageStreamParsers(plan_mode=True)

        first = parsers.seed_item_text("msg-1", "Intro\n<proposed")
        second = parsers.parse_delta("msg-1", "_plan>\n- step\n")
        finished = parsers.finish_item("msg-1")
        empty = parsers.finish_item("msg-1")

        self.assertEqual(first["visible_text"], "Intro\n")
        self.assertEqual(second["visible_text"], "")
        self.assertIn(("proposed_plan_start", ""), second["plan_segments"])
        self.assertIn(("proposed_plan_delta", "- step\n"), second["plan_segments"])
        self.assertIn(("proposed_plan_end", ""), finished["plan_segments"])
        self.assertEqual(empty, {"visible_text": "", "citations": (), "plan_segments": ()})

    def test_network_policy_saved_fragments_match_session_amendment_contract(self) -> None:
        # Rust source: codex/codex-rs/core/src/session/tests.rs
        # Rust tests: validated_network_policy_amendment_host_allows_normalized_match,
        # validated_network_policy_amendment_host_rejects_mismatch.
        allow = NetworkRuleSaved.new(NetworkPolicyAmendment("api.example.com", NetworkPolicyRuleAction.ALLOW))
        deny = NetworkRuleSaved.new(NetworkPolicyAmendment("blocked.example.com", NetworkPolicyRuleAction.DENY))

        self.assertEqual(allow.role(), "developer")
        self.assertEqual(allow.body(), "Allowed network rule saved in execpolicy (allowlist): api.example.com")
        self.assertEqual(deny.body(), "Denied network rule saved in execpolicy (denylist): blocked.example.com")
        self.assertEqual(allow.into_response_item().role, "developer")

    async def test_mailbox_delivery_deferral_and_reopen_match_session_boundaries(self) -> None:
        # Rust source: codex/codex-rs/core/src/session/tests.rs
        # Rust tests: queue_only_mailbox_mail_waits_for_next_turn_after_answer_boundary,
        # trigger_turn_mailbox_mail_waits_for_next_turn_after_answer_boundary,
        # steered_input_reopens_mailbox_delivery_for_current_turn,
        # tool_calls_reopen_mailbox_delivery_for_current_turn.
        queue = InMemoryInputQueue()
        turn_state = TurnState()
        active_turn = SimpleNamespace(
            task=SimpleNamespace(turn_context=SimpleNamespace(sub_id="turn-1")),
            turn_state=turn_state,
        )

        await queue.enqueue_mailbox_communication(InterAgentCommunication("/root", "/root/agent", "mail", True))
        await queue.defer_mailbox_delivery_to_next_turn(active_turn, "turn-1")
        self.assertEqual(turn_state.mailbox_delivery_phase, MailboxDeliveryPhase.NEXT_TURN)
        self.assertFalse(await queue.has_pending_input(active_turn))

        await queue.accept_mailbox_delivery_for_current_turn(active_turn, "turn-1")
        pending = await queue.get_pending_input(active_turn)

        self.assertEqual(turn_state.mailbox_delivery_phase, MailboxDeliveryPhase.CURRENT_TURN)
        self.assertEqual(len(pending), 1)
        self.assertIsInstance(pending[0], ResponseItem)
        self.assertFalse(await queue.has_pending_mailbox_items())

    def test_goal_accounting_helpers_match_session_goal_tests(self) -> None:
        # Rust source: codex/codex-rs/core/src/session/tests.rs
        # Rust tests: interrupt_accounts_active_goal_without_pausing,
        # usage_limit_runtime_stops_active_goal_and_prevents_idle_continuation,
        # completed_goal_accounts_current_turn_tokens_before_tool_response,
        # create_goal_tool_rejects_existing_goal/update_goal_tool_* cluster.
        self.assertTrue(should_ignore_goal_for_mode(ModeKind.PLAN))
        self.assertFalse(should_ignore_goal_for_mode(ModeKind.DEFAULT))
        validate_goal_budget(None)
        validate_goal_budget(1)
        with self.assertRaisesRegex(ValueError, "goal budgets must be positive"):
            validate_goal_budget(0)

        usage = TokenUsage(
            input_tokens=100,
            cached_input_tokens=20,
            output_tokens=50,
            reasoning_output_tokens=10,
        )
        self.assertEqual(goal_token_delta_for_usage(usage), 130)


if __name__ == "__main__":
    unittest.main()
