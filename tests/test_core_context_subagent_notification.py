import unittest

from pycodex.core.context import SubagentNotification, is_standard_contextual_user_text
from pycodex.protocol import AgentStatus, ContentItem, ResponseInputItem, ResponseItem


class SubagentNotificationTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/subagent_notification.rs

    def test_subagent_notification_matches_marked_text_and_standard_context_registration(self) -> None:
        rendered = '<subagent_notification>\n{"agent_path":"agent-a","status":"running"}\n</subagent_notification>'

        self.assertTrue(SubagentNotification.matches_text(rendered))
        self.assertTrue(SubagentNotification.matches_text(f"  {rendered.upper()}\n"))
        self.assertTrue(is_standard_contextual_user_text(rendered))
        self.assertFalse(SubagentNotification.matches_text('{"agent_path":"agent-a","status":"running"}'))

    def test_subagent_notification_running_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = SubagentNotification.new("agent-a", AgentStatus.running())
        expected_body = '\n{"agent_path":"agent-a","status":"running"}\n'
        expected_render = f"<subagent_notification>{expected_body}</subagent_notification>"

        self.assertEqual(fragment.role(), "user")
        self.assertEqual(
            fragment.markers(),
            ("<subagent_notification>", "</subagent_notification>"),
        )
        self.assertEqual(
            fragment.type_markers(),
            ("<subagent_notification>", "</subagent_notification>"),
        )
        self.assertEqual(fragment.body(), expected_body)
        self.assertEqual(fragment.render(), expected_render)
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("user", (ContentItem.input_text(expected_render),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("user", (ContentItem.input_text(expected_render),)),
        )

    def test_subagent_notification_completed_matches_rust_json_shape(self) -> None:
        fragment = SubagentNotification.new("agent-b", AgentStatus.completed("done"))
        expected_body = '\n{"agent_path":"agent-b","status":{"completed":"done"}}\n'

        self.assertEqual(fragment.body(), expected_body)
        self.assertEqual(
            fragment.render(),
            f"<subagent_notification>{expected_body}</subagent_notification>",
        )


if __name__ == "__main__":
    unittest.main()
