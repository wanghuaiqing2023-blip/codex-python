import unittest

from pycodex.cli import UpdateAction, update_available_raw_lines


class UpdateNoticeTests(unittest.TestCase):
    def test_raw_lines_include_update_command_when_action_is_known(self) -> None:
        self.assertEqual(
            update_available_raw_lines("9.9.9", UpdateAction.BREW_UPGRADE, current_version="1.2.3"),
            [
                "Update available!",
                "1.2.3 -> 9.9.9",
                "Run brew upgrade --cask codex to update.",
                "",
                "See full release notes:",
                "https://github.com/openai/codex/releases/latest",
            ],
        )

    def test_raw_lines_fall_back_to_install_options_without_action(self) -> None:
        self.assertEqual(
            update_available_raw_lines("9.9.9", None, current_version="1.2.3"),
            [
                "Update available!",
                "1.2.3 -> 9.9.9",
                "See https://github.com/openai/codex for installation options.",
                "",
                "See full release notes:",
                "https://github.com/openai/codex/releases/latest",
            ],
        )


if __name__ == "__main__":
    unittest.main()
