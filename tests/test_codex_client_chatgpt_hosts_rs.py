import unittest

from pycodex.codex_client import is_allowed_chatgpt_host


class CodexClientChatgptHostsRsTests(unittest.TestCase):
    def test_recognizes_chatgpt_hosts_without_suffix_tricks(self) -> None:
        # Rust crate/module/test: codex-client/src/chatgpt_hosts.rs
        # recognizes_chatgpt_hosts_without_suffix_tricks.
        for host in (
            "chatgpt.com",
            "foo.chatgpt.com",
            "staging.chatgpt.com",
            "chat.openai.com",
            "chatgpt-staging.com",
            "api.chatgpt-staging.com",
        ):
            with self.subTest(host=host):
                self.assertTrue(is_allowed_chatgpt_host(host))

        for host in (
            "evilchatgpt.com",
            "chatgpt.com.evil.example",
            "api.openai.com",
            "foo.chat.openai.com",
        ):
            with self.subTest(host=host):
                self.assertFalse(is_allowed_chatgpt_host(host))


if __name__ == "__main__":
    unittest.main()
