import asyncio
import unittest
from types import SimpleNamespace

from pycodex.core.session.runtime import InMemoryInputQueue
from pycodex.core.state.turn import MailboxDeliveryPhase, TurnState
from pycodex.protocol import InterAgentCommunication, MessagePhase, ResponseItem


class InMemoryInputQueueMailboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_input_queue_drains_mailbox_in_delivery_order(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust test: input_queue_drains_mailbox_in_delivery_order
        queue = InMemoryInputQueue()
        mail_one = InterAgentCommunication("/root", "/root/worker", "one", False)
        mail_two = InterAgentCommunication("/root/worker", "/root", "two", False)

        await queue.enqueue_mailbox_communication(mail_one)
        await queue.enqueue_mailbox_communication(mail_two)

        self.assertTrue(await queue.has_pending_mailbox_items())
        self.assertEqual(
            await queue.drain_mailbox_input_items(),
            (
                ResponseItem.from_response_input_item(mail_one.to_response_input_item()),
                ResponseItem.from_response_input_item(mail_two.to_response_input_item()),
            ),
        )
        self.assertFalse(await queue.has_pending_mailbox_items())

    async def test_input_queue_tracks_pending_trigger_turn_mail(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust test: input_queue_tracks_pending_trigger_turn_mail
        queue = InMemoryInputQueue()

        await queue.enqueue_mailbox_communication(InterAgentCommunication("/root", "/root/worker", "queued", False))
        self.assertFalse(await queue.has_trigger_turn_mailbox_items())

        await queue.enqueue_mailbox_communication(InterAgentCommunication("/root", "/root/worker", "wake", True))
        self.assertTrue(await queue.has_trigger_turn_mailbox_items())

    async def test_input_queue_notifies_mailbox_subscribers(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust test: input_queue_notifies_mailbox_subscribers
        queue = InMemoryInputQueue()
        subscriber = await queue.subscribe_mailbox()

        await queue.enqueue_mailbox_communication(InterAgentCommunication("/root", "/root/worker", "one", False))

        await asyncio.wait_for(subscriber.changed(), timeout=1)
        self.assertFalse(subscriber.has_changed())

    async def test_subscribe_mailbox_marks_changed_when_mail_already_pending(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: subscribe_mailbox pending mail branch
        queue = InMemoryInputQueue()
        await queue.enqueue_mailbox_communication(InterAgentCommunication("/root", "/root/worker", "one", False))

        subscriber = await queue.subscribe_mailbox()

        self.assertTrue(subscriber.has_changed())
        await asyncio.wait_for(subscriber.changed(), timeout=1)

    async def test_input_queue_accepts_mapping_mail_and_preserves_commentary_phase(self) -> None:
        # Rust crate: codex-core / codex-protocol
        # Rust module: session::input_queue plus InterAgentCommunication::to_response_input_item
        queue = InMemoryInputQueue()

        await queue.enqueue_mailbox_communication(
            {
                "author": "/root",
                "recipient": "/root/worker",
                "other_recipients": [],
                "content": "hello",
                "trigger_turn": True,
            }
        )

        drained = await queue.drain_mailbox_input_items()

        self.assertEqual(len(drained), 1)
        self.assertEqual(drained[0].role, "assistant")
        self.assertEqual(drained[0].phase, MessagePhase.COMMENTARY)
        self.assertIn('"content":"hello"', drained[0].content[0].text)

    async def test_extend_pending_input_for_turn_state_preserves_order(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: extend_pending_input_for_turn_state / take_pending_input_for_turn_state
        queue = InMemoryInputQueue()
        turn_state = TurnState()

        await queue.extend_pending_input_for_turn_state(turn_state, ["one"])
        await queue.extend_pending_input_for_turn_state(turn_state, ["two", "three"])

        self.assertEqual(await queue.take_pending_input_for_turn_state(turn_state), ("one", "two", "three"))
        self.assertEqual(await queue.take_pending_input_for_turn_state(turn_state), ())

    async def test_extend_pending_input_and_accept_mailbox_delivery_for_turn_state(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: extend_pending_input_and_accept_mailbox_delivery_for_turn_state
        queue = InMemoryInputQueue()
        turn_state = TurnState(mailbox_delivery_phase=MailboxDeliveryPhase.NEXT_TURN)

        await queue.extend_pending_input_and_accept_mailbox_delivery_for_turn_state(turn_state, ["item"])

        self.assertEqual(await queue.take_pending_input_for_turn_state(turn_state), ("item",))
        self.assertTrue(turn_state.accepts_mailbox_delivery_for_current_turn())

    async def test_accept_mailbox_delivery_for_turn_state_without_pending_input(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: accept_mailbox_delivery_for_turn_state
        queue = InMemoryInputQueue()
        turn_state = TurnState(mailbox_delivery_phase=MailboxDeliveryPhase.NEXT_TURN)

        await queue.accept_mailbox_delivery_for_turn_state(turn_state)

        self.assertEqual(turn_state.mailbox_delivery_phase, MailboxDeliveryPhase.CURRENT_TURN)

    async def test_turn_state_pending_input_can_use_existing_items_holder(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Contract: Python keeps compatibility with Rust's pending_input.items shape.
        queue = InMemoryInputQueue()
        turn_state = TurnState(pending_input=SimpleNamespace(items=["existing"]))

        await queue.extend_pending_input_for_turn_state(turn_state, ["new"])

        self.assertEqual(await queue.take_pending_input_for_turn_state(turn_state), ("existing", "new"))

    async def test_get_pending_input_merges_turn_pending_then_mailbox_for_current_turn(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: get_pending_input
        queue = InMemoryInputQueue()
        turn_state = TurnState(pending_input=SimpleNamespace(items=["turn-item"]))
        active_turn = SimpleNamespace(turn_state=turn_state)
        mail = InterAgentCommunication("/root", "/root/worker", "mail", False)
        await queue.enqueue_mailbox_communication(mail)

        pending = await queue.get_pending_input(active_turn)

        self.assertEqual(pending[0], "turn-item")
        self.assertEqual(pending[1], ResponseItem.from_response_input_item(mail.to_response_input_item()))
        self.assertFalse(await queue.has_pending_mailbox_items())
        self.assertEqual(await queue.take_pending_input_for_turn_state(turn_state), ())

    async def test_get_pending_input_defers_mailbox_when_turn_does_not_accept_delivery(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: get_pending_input
        queue = InMemoryInputQueue()
        turn_state = TurnState(
            pending_input=SimpleNamespace(items=["turn-item"]),
            mailbox_delivery_phase=MailboxDeliveryPhase.NEXT_TURN,
        )
        active_turn = SimpleNamespace(turn_state=turn_state)
        await queue.enqueue_mailbox_communication(InterAgentCommunication("/root", "/root/worker", "mail", False))

        self.assertEqual(await queue.get_pending_input(active_turn), ("turn-item",))
        self.assertTrue(await queue.has_pending_mailbox_items())

    async def test_has_pending_input_respects_mailbox_delivery_phase(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: has_pending_input
        queue = InMemoryInputQueue()
        current_turn = SimpleNamespace(turn_state=TurnState())
        next_turn = SimpleNamespace(turn_state=TurnState(mailbox_delivery_phase=MailboxDeliveryPhase.NEXT_TURN))

        self.assertFalse(await queue.has_pending_input(current_turn))
        await queue.enqueue_mailbox_communication(InterAgentCommunication("/root", "/root/worker", "mail", False))

        self.assertTrue(await queue.has_pending_input(current_turn))
        self.assertFalse(await queue.has_pending_input(next_turn))

    async def test_get_pending_input_without_active_turn_merges_legacy_items_and_mailbox(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: get_pending_input active_turn None branch
        queue = InMemoryInputQueue()
        queue.items.append("legacy-item")
        mail = InterAgentCommunication("/root", "/root/worker", "mail", False)
        await queue.enqueue_mailbox_communication(mail)

        pending = await queue.get_pending_input(None)

        self.assertEqual(pending[0], "legacy-item")
        self.assertEqual(pending[1], ResponseItem.from_response_input_item(mail.to_response_input_item()))
        self.assertFalse(await queue.has_pending_input(None))

    async def test_turn_state_for_sub_id_matches_active_turn_task_context(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: turn_state_for_sub_id
        queue = InMemoryInputQueue()
        turn_state = TurnState()
        active_turn = SimpleNamespace(
            task=SimpleNamespace(turn_context=SimpleNamespace(sub_id="sub-1")),
            turn_state=turn_state,
        )

        self.assertIs(await queue.turn_state_for_sub_id(active_turn, "sub-1"), turn_state)
        self.assertIsNone(await queue.turn_state_for_sub_id(active_turn, "sub-2"))
        self.assertIsNone(await queue.turn_state_for_sub_id(None, "sub-1"))

    async def test_clear_pending_clears_waiters_and_pending_input(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: clear_pending
        queue = InMemoryInputQueue()
        turn_state = TurnState(pending_input=SimpleNamespace(items=["pending"]))
        turn_state.pending_approvals["approval"] = object()
        turn_state.pending_user_input["input"] = object()
        active_turn = SimpleNamespace(turn_state=turn_state)

        await queue.clear_pending(active_turn)

        self.assertEqual(turn_state.pending_approvals, {})
        self.assertEqual(turn_state.pending_user_input, {})
        self.assertEqual(turn_state.pending_input.items, [])

    async def test_defer_mailbox_delivery_to_next_turn_only_when_sub_id_matches_and_no_pending_input(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: defer_mailbox_delivery_to_next_turn
        queue = InMemoryInputQueue()
        turn_state = TurnState()
        active_turn = SimpleNamespace(
            task=SimpleNamespace(turn_context=SimpleNamespace(sub_id="sub-1")),
            turn_state=turn_state,
        )

        await queue.defer_mailbox_delivery_to_next_turn(active_turn, "sub-2")
        self.assertEqual(turn_state.mailbox_delivery_phase, MailboxDeliveryPhase.CURRENT_TURN)

        await queue.defer_mailbox_delivery_to_next_turn(active_turn, "sub-1")
        self.assertEqual(turn_state.mailbox_delivery_phase, MailboxDeliveryPhase.NEXT_TURN)

    async def test_defer_mailbox_delivery_to_next_turn_keeps_current_turn_when_pending_input_exists(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: defer_mailbox_delivery_to_next_turn pending-input guard
        queue = InMemoryInputQueue()
        turn_state = TurnState(pending_input=SimpleNamespace(items=["pending"]))
        active_turn = SimpleNamespace(
            task=SimpleNamespace(turn_context=SimpleNamespace(sub_id="sub-1")),
            turn_state=turn_state,
        )

        await queue.defer_mailbox_delivery_to_next_turn(active_turn, "sub-1")

        self.assertEqual(turn_state.mailbox_delivery_phase, MailboxDeliveryPhase.CURRENT_TURN)

    async def test_accept_mailbox_delivery_for_current_turn_requires_matching_sub_id(self) -> None:
        # Rust crate: codex-core
        # Rust module: session::input_queue
        # Rust item: accept_mailbox_delivery_for_current_turn
        queue = InMemoryInputQueue()
        turn_state = TurnState(mailbox_delivery_phase=MailboxDeliveryPhase.NEXT_TURN)
        active_turn = SimpleNamespace(
            task=SimpleNamespace(turn_context=SimpleNamespace(sub_id="sub-1")),
            turn_state=turn_state,
        )

        await queue.accept_mailbox_delivery_for_current_turn(active_turn, "sub-2")
        self.assertEqual(turn_state.mailbox_delivery_phase, MailboxDeliveryPhase.NEXT_TURN)

        await queue.accept_mailbox_delivery_for_current_turn(active_turn, "sub-1")
        self.assertEqual(turn_state.mailbox_delivery_phase, MailboxDeliveryPhase.CURRENT_TURN)


if __name__ == "__main__":
    unittest.main()
