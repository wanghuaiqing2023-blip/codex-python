from __future__ import annotations

import unittest

from pycodex.core.session_prefix import (
    format_subagent_context_line,
    format_subagent_notification_message,
)
from pycodex.protocol import AgentStatus


class SessionPrefixTests(unittest.TestCase):
    def test_format_subagent_notification_message_uses_context_fragment(self) -> None:
        self.assertEqual(
            format_subagent_notification_message("agent-a", AgentStatus.running()),
            '<subagent_notification>\n{"agent_path":"agent-a","status":"running"}\n</subagent_notification>',
        )

        self.assertEqual(
            format_subagent_notification_message("agent-b", {"completed": "done"}),
            '<subagent_notification>\n{"agent_path":"agent-b","status":{"completed":"done"}}\n</subagent_notification>',
        )

    def test_format_subagent_context_line_omits_empty_nickname_only(self) -> None:
        self.assertEqual(format_subagent_context_line("agent-a", None), "- agent-a")
        self.assertEqual(format_subagent_context_line("agent-a", ""), "- agent-a")
        self.assertEqual(format_subagent_context_line("agent-a", "builder"), "- agent-a: builder")
        self.assertEqual(format_subagent_context_line("agent-a", " "), "- agent-a:  ")


if __name__ == "__main__":
    unittest.main()
