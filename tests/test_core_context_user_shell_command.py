import unittest
from datetime import timedelta

from pycodex.core.context import UserShellCommand
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class ContextUserShellCommandTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/user_shell_command.rs

    def test_detects_user_shell_command_text_variants(self) -> None:
        # Rust test: codex-rs/core/src/user_shell_command_tests.rs
        # `detects_user_shell_command_text_variants`
        self.assertTrue(
            UserShellCommand.matches_text(
                "<user_shell_command>\necho hi\n</user_shell_command>"
            )
        )
        self.assertFalse(UserShellCommand.matches_text("echo hi"))

    def test_user_shell_command_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = UserShellCommand.new(
            "python -m unittest",
            0,
            timedelta(milliseconds=25),
            "OK\n",
        )

        body = (
            "\n<command>\n"
            "python -m unittest\n"
            "</command>\n"
            "<result>\n"
            "Exit code: 0\n"
            "Duration: 0.0250 seconds\n"
            "Output:\n"
            "OK\n"
            "\n</result>\n"
        )
        rendered = f"<user_shell_command>{body}</user_shell_command>"

        self.assertEqual(fragment.role(), "user")
        self.assertEqual(fragment.markers(), ("<user_shell_command>", "</user_shell_command>"))
        self.assertEqual(fragment.type_markers(), ("<user_shell_command>", "</user_shell_command>"))
        self.assertEqual(fragment.body(), body)
        self.assertEqual(fragment.render(), rendered)
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("user", (ContentItem.input_text(rendered),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("user", (ContentItem.input_text(rendered),)),
        )


if __name__ == "__main__":
    unittest.main()
