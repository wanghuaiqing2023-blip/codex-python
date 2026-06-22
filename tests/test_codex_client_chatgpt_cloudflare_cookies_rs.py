"""Rust-derived tests for ``codex-client/src/chatgpt_cloudflare_cookies.rs``.

Rust crate: ``codex-client``
Rust module: ``src/chatgpt_cloudflare_cookies.rs``
"""

from __future__ import annotations

import unittest

from pycodex.codex_client import ChatGptCloudflareCookieStore
from pycodex.codex_client import is_allowed_cloudflare_cookie_name
from pycodex.codex_client import is_chatgpt_cookie_url
from pycodex.codex_client import with_chatgpt_cloudflare_cookie_store


CHATGPT_URL = "https://chatgpt.com/backend-api/codex/responses"
API_URL = "https://api.openai.com/v1/responses"


class Builder:
    def __init__(self) -> None:
        self.store = None

    def cookie_provider(self, store):
        self.store = store
        return self


class CodexClientChatgptCloudflareCookiesRsTests(unittest.TestCase):
    def test_stores_and_returns_cloudflare_cookies_for_chatgpt_hosts(self) -> None:
        store = ChatGptCloudflareCookieStore()

        store.set_cookies(
            [
                "_cfuvid=visitor; Path=/; Secure; HttpOnly",
                "cf_clearance=clearance; Path=/; Secure; HttpOnly",
            ],
            CHATGPT_URL,
        )

        cookies = sorted((store.cookies(CHATGPT_URL) or "").split("; "))
        self.assertEqual(cookies, ["_cfuvid=visitor", "cf_clearance=clearance"])

    def test_ignores_non_chatgpt_cookies(self) -> None:
        store = ChatGptCloudflareCookieStore()

        store.set_cookies(["_cfuvid=visitor; Path=/; Secure; HttpOnly"], API_URL)

        self.assertIsNone(store.cookies(API_URL))

    def test_ignores_non_cloudflare_cookies_for_chatgpt_hosts(self) -> None:
        store = ChatGptCloudflareCookieStore()

        store.set_cookies(
            ["__Secure-next-auth.session-token=secret; Path=/; Secure; HttpOnly"],
            CHATGPT_URL,
        )

        self.assertIsNone(store.cookies(CHATGPT_URL))

    def test_ignores_mixed_non_cloudflare_cookies_for_chatgpt_hosts(self) -> None:
        store = ChatGptCloudflareCookieStore()

        store.set_cookies(
            [
                "_cfuvid=visitor; Path=/; Secure; HttpOnly",
                "chatgpt_session=secret; Path=/; Secure; HttpOnly",
            ],
            CHATGPT_URL,
        )

        self.assertEqual(store.cookies(CHATGPT_URL), "_cfuvid=visitor")

    def test_does_not_return_chatgpt_cloudflare_cookies_for_other_hosts(self) -> None:
        store = ChatGptCloudflareCookieStore()

        store.set_cookies(["_cfuvid=visitor; Path=/; Secure; HttpOnly"], CHATGPT_URL)

        self.assertIsNone(store.cookies(API_URL))

    def test_rejects_plain_http_chatgpt_cookie_urls(self) -> None:
        store = ChatGptCloudflareCookieStore()
        http_url = "http://chatgpt.com/backend-api/codex/responses"

        store.set_cookies(["_cfuvid=visitor; Path=/; Secure; HttpOnly"], http_url)

        self.assertIsNone(store.cookies(http_url))
        self.assertIsNone(store.cookies(CHATGPT_URL))

    def test_only_allows_https_urls(self) -> None:
        self.assertFalse(
            is_chatgpt_cookie_url("http://chatgpt.com/backend-api/codex/responses")
        )
        self.assertFalse(
            is_chatgpt_cookie_url("wss://chatgpt.com/backend-api/codex/responses")
        )

    def test_allows_only_known_cloudflare_cookie_names(self) -> None:
        for name in [
            "__cf_bm",
            "__cflb",
            "__cfruid",
            "__cfseq",
            "__cfwaitingroom",
            "_cfuvid",
            "cf_clearance",
            "cf_ob_info",
            "cf_use_ob",
            "cf_chl_rc_i",
        ]:
            self.assertTrue(is_allowed_cloudflare_cookie_name(name), name)

        for name in [
            "__Secure-next-auth.session-token",
            "chatgpt_session",
            "oai-auth-token",
            "not_cf_clearance",
        ]:
            self.assertFalse(is_allowed_cloudflare_cookie_name(name), name)

    def test_with_chatgpt_cloudflare_cookie_store_attaches_shared_store(self) -> None:
        builder = Builder()

        returned = with_chatgpt_cloudflare_cookie_store(builder)

        self.assertIs(returned, builder)
        self.assertIsNotNone(builder.store)


if __name__ == "__main__":
    unittest.main()
