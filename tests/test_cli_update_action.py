import unittest

from pycodex.cli import UpdateAction, update_action_label


class UpdateActionTests(unittest.TestCase):
    def test_package_manager_update_commands(self) -> None:
        self.assertEqual(UpdateAction.NPM_GLOBAL_LATEST.command_args(), ("npm", ("install", "-g", "@openai/codex")))
        self.assertEqual(UpdateAction.NPM_GLOBAL_LATEST.command_str(), "npm install -g @openai/codex")
        self.assertEqual(UpdateAction.BUN_GLOBAL_LATEST.command_args(), ("bun", ("install", "-g", "@openai/codex")))
        self.assertEqual(UpdateAction.BUN_GLOBAL_LATEST.command_str(), "bun install -g @openai/codex")
        self.assertEqual(UpdateAction.BREW_UPGRADE.command_args(), ("brew", ("upgrade", "--cask", "codex")))
        self.assertEqual(UpdateAction.BREW_UPGRADE.command_str(), "brew upgrade --cask codex")

    def test_standalone_unix_reruns_latest_installer(self) -> None:
        self.assertEqual(
            UpdateAction.STANDALONE_UNIX.command_args(),
            (
                "sh",
                ("-c", "curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh"),
            ),
        )
        self.assertEqual(
            UpdateAction.STANDALONE_UNIX.command_str(),
            "sh -c 'curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh'",
        )

    def test_standalone_windows_reruns_latest_installer(self) -> None:
        self.assertEqual(
            UpdateAction.STANDALONE_WINDOWS.command_args(),
            (
                "powershell",
                (
                    "-ExecutionPolicy",
                    "Bypass",
                    "-c",
                    "$env:CODEX_NON_INTERACTIVE=1; irm https://chatgpt.com/codex/install.ps1 | iex",
                ),
            ),
        )
        self.assertEqual(
            UpdateAction.STANDALONE_WINDOWS.command_str(),
            "powershell -ExecutionPolicy Bypass -c '$env:CODEX_NON_INTERACTIVE=1; irm https://chatgpt.com/codex/install.ps1 | iex'",
        )

    def test_update_action_label_matches_doctor_labels(self) -> None:
        self.assertEqual(update_action_label(UpdateAction.NPM_GLOBAL_LATEST), "npm install -g @openai/codex")
        self.assertEqual(update_action_label(UpdateAction.BUN_GLOBAL_LATEST), "bun install -g @openai/codex")
        self.assertEqual(update_action_label(UpdateAction.BREW_UPGRADE), "brew upgrade --cask codex")
        self.assertEqual(update_action_label(UpdateAction.STANDALONE_UNIX), "standalone installer")
        self.assertEqual(update_action_label(UpdateAction.STANDALONE_WINDOWS), "standalone installer")
        self.assertEqual(update_action_label(None), "manual or unknown")


if __name__ == "__main__":
    unittest.main()
