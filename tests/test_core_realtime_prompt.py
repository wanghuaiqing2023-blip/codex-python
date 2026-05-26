from __future__ import annotations

import unittest

from pycodex.core import (
    DEFAULT_USER_FIRST_NAME,
    PROMPT_UNSET,
    USER_FIRST_NAME_PLACEHOLDER,
    current_user_first_name,
    prepare_realtime_backend_prompt,
)


class RealtimePromptTests(unittest.TestCase):
    def test_prepare_realtime_backend_prompt_prefers_config_override(self) -> None:
        self.assertEqual(
            prepare_realtime_backend_prompt("prompt from request", "prompt from config"),
            "prompt from config",
        )

    def test_prepare_realtime_backend_prompt_ignores_blank_config_override(self) -> None:
        self.assertEqual(
            prepare_realtime_backend_prompt("prompt from request", "   "),
            "prompt from request",
        )

    def test_prepare_realtime_backend_prompt_uses_request_prompt(self) -> None:
        self.assertEqual(
            prepare_realtime_backend_prompt("prompt from request"),
            "prompt from request",
        )

    def test_prepare_realtime_backend_prompt_preserves_empty_request_prompt(self) -> None:
        self.assertEqual(prepare_realtime_backend_prompt(""), "")
        self.assertEqual(prepare_realtime_backend_prompt(None), "")

    def test_prepare_realtime_backend_prompt_renders_default(self) -> None:
        prompt = prepare_realtime_backend_prompt(PROMPT_UNSET)

        self.assertTrue(prompt.startswith("## Identity, tone, and role"))
        self.assertIn("You are Codex, an OpenAI general-purpose agentic assistant", prompt)
        self.assertIn("The user's name is ", prompt)
        self.assertNotIn(USER_FIRST_NAME_PLACEHOLDER, prompt)

    def test_prepare_realtime_backend_prompt_rejects_unexpected_prompt_type(self) -> None:
        with self.assertRaisesRegex(TypeError, "prompt must be"):
            prepare_realtime_backend_prompt(42)

    def test_current_user_first_name_prefers_real_name_then_user_name(self) -> None:
        self.assertEqual(current_user_first_name("Ada Lovelace", "cli-user"), "Ada")
        self.assertEqual(current_user_first_name("   ", "Grace Hopper"), "Grace")
        self.assertEqual(current_user_first_name("", ""), DEFAULT_USER_FIRST_NAME)


if __name__ == "__main__":
    unittest.main()
