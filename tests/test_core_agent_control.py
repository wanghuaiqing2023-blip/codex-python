from __future__ import annotations

import unittest
from pathlib import Path

from pycodex.core import (
    ROOT_LAST_TASK_MESSAGE,
    agent_matches_prefix,
    default_agent_nickname_list,
    filter_forked_rollout_items,
    is_multi_agent_v2_usage_hint_message,
    keep_forked_rollout_item,
    render_input_preview,
    thread_spawn_depth,
    thread_spawn_parent_thread_id,
)
from pycodex.protocol import (
    AgentPath,
    CompactedItem,
    ContentItem,
    InterAgentCommunication,
    MessagePhase,
    Op,
    ResponseItem,
    RolloutItem,
    SessionSource,
    SubAgentSource,
    ThreadId,
    UserInput,
)


def message(role: str, text: str, phase: MessagePhase | None = None) -> ResponseItem:
    return ResponseItem.message(role, (ContentItem.input_text(text),), phase=phase)


class AgentControlPureHelpersTests(unittest.TestCase):
    def test_default_agent_nickname_list_filters_embedded_names(self) -> None:
        names = default_agent_nickname_list()

        self.assertEqual(names[:3], ["Euclid", "Archimedes", "Ptolemy"])
        self.assertIn("Jason", names)
        self.assertNotIn("", names)
        self.assertEqual(ROOT_LAST_TASK_MESSAGE, "Main thread")

    def test_keep_forked_rollout_item_keeps_system_developer_user_messages(self) -> None:
        for role in ("system", "developer", "user"):
            self.assertTrue(
                keep_forked_rollout_item(
                    RolloutItem.response_item(message(role, "keep")),
                    preserve_reference_context_item=False,
                )
            )

    def test_keep_forked_rollout_item_keeps_only_final_assistant_messages(self) -> None:
        self.assertTrue(
            keep_forked_rollout_item(
                RolloutItem.response_item(message("assistant", "final", MessagePhase.FINAL_ANSWER)),
                preserve_reference_context_item=False,
            )
        )
        self.assertFalse(
            keep_forked_rollout_item(
                RolloutItem.response_item(message("assistant", "commentary", MessagePhase.COMMENTARY)),
                preserve_reference_context_item=False,
            )
        )
        self.assertFalse(
            keep_forked_rollout_item(
                RolloutItem.response_item(ResponseItem.function_call("spawn_agent", "{}", "call-1")),
                preserve_reference_context_item=False,
            )
        )

    def test_keep_forked_rollout_item_turn_context_depends_on_fork_mode(self) -> None:
        turn_context = RolloutItem("turn_context", {"cwd": "."})

        self.assertTrue(keep_forked_rollout_item(turn_context, preserve_reference_context_item=True))
        self.assertFalse(keep_forked_rollout_item(turn_context, preserve_reference_context_item=False))

    def test_keep_forked_rollout_item_keeps_compacted_event_and_session_meta(self) -> None:
        self.assertTrue(
            keep_forked_rollout_item(
                RolloutItem.compacted(CompactedItem("compacted")),
                preserve_reference_context_item=False,
            )
        )
        self.assertTrue(keep_forked_rollout_item(RolloutItem("event_msg", {"type": "shutdown_complete"}), False))
        self.assertTrue(keep_forked_rollout_item(RolloutItem("session_meta", {}), False))

    def test_is_multi_agent_v2_usage_hint_message(self) -> None:
        hint = message("developer", "Subagent hint")
        other_role = message("user", "Subagent hint")
        multiple_items = ResponseItem.message(
            "developer",
            (ContentItem.input_text("Subagent hint"), ContentItem.input_text("extra")),
        )

        self.assertTrue(is_multi_agent_v2_usage_hint_message(hint, ["Subagent hint"]))
        self.assertFalse(is_multi_agent_v2_usage_hint_message(other_role, ["Subagent hint"]))
        self.assertFalse(is_multi_agent_v2_usage_hint_message(multiple_items, ["Subagent hint"]))
        self.assertFalse(is_multi_agent_v2_usage_hint_message(hint, ["Different"]))

    def test_filter_forked_rollout_items_filters_response_items_and_compacted_history(self) -> None:
        usage_hint = message("developer", "Subagent hint")
        assistant_final = message("assistant", "done", MessagePhase.FINAL_ANSWER)
        assistant_commentary = message("assistant", "working", MessagePhase.COMMENTARY)
        compacted = RolloutItem.compacted(
            CompactedItem(
                message="compacted",
                replacement_history=(usage_hint, assistant_final),
            )
        )

        filtered = filter_forked_rollout_items(
            [
                RolloutItem.response_item(usage_hint),
                RolloutItem.response_item(assistant_final),
                RolloutItem.response_item(assistant_commentary),
                compacted,
            ],
            preserve_reference_context_item=False,
            usage_hint_texts=["Subagent hint"],
        )

        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0].payload, assistant_final)
        compacted_payload = filtered[1].payload
        self.assertIsInstance(compacted_payload, CompactedItem)
        self.assertEqual(compacted_payload.replacement_history, (assistant_final,))

    def test_agent_matches_prefix(self) -> None:
        self.assertTrue(agent_matches_prefix("/root/researcher/worker", "/root"))
        self.assertTrue(agent_matches_prefix("/root/researcher/worker", "/root/researcher"))
        self.assertTrue(agent_matches_prefix("/root/researcher", "/root/researcher"))
        self.assertFalse(agent_matches_prefix("/root/researcher2", "/root/researcher"))
        self.assertFalse(agent_matches_prefix(None, "/root/researcher"))

    def test_thread_spawn_parent_thread_id_and_depth(self) -> None:
        parent = ThreadId.new()
        source = SessionSource.subagent(SubAgentSource.thread_spawn(parent_thread_id=parent, depth=2))

        self.assertEqual(thread_spawn_parent_thread_id(source), parent)
        self.assertEqual(thread_spawn_depth(source), 2)
        self.assertIsNone(thread_spawn_parent_thread_id(SessionSource.cli()))
        self.assertIsNone(thread_spawn_depth(SessionSource.cli()))

    def test_render_input_preview_for_user_input(self) -> None:
        op = Op.user_input(
            (
                UserInput.text_input("hello"),
                UserInput.image("data:image/png;base64,abc"),
                UserInput.local_image(Path("diagram.png")),
                UserInput.skill("docs", Path("skills/docs/SKILL.md")),
                UserInput.mention("plugin", "@plugin"),
            )
        )

        self.assertEqual(
            render_input_preview(op),
            "\n".join(
                [
                    "hello",
                    "[image]",
                    "[local_image:diagram.png]",
                    f"[skill:$docs]({Path('skills/docs/SKILL.md')})",
                    "[mention:$plugin](@plugin)",
                ]
            ),
        )

    def test_render_input_preview_for_inter_agent_communication_and_other_ops(self) -> None:
        communication = InterAgentCommunication(
            author=AgentPath.root(),
            recipient=AgentPath.from_string("/root/worker"),
            content="hello worker",
            trigger_turn=False,
        )

        self.assertEqual(render_input_preview(Op.inter_agent_communication(communication)), "hello worker")
        self.assertEqual(render_input_preview(Op.simple("shutdown")), "")


if __name__ == "__main__":
    unittest.main()
