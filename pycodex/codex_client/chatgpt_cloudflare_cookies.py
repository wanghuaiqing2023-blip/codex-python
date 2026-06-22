"""ChatGPT Cloudflare cookie store for the Rust ``codex-client`` port.

Rust source:
- ``codex/codex-rs/codex-client/src/chatgpt_cloudflare_cookies.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

from .chatgpt_hosts import is_allowed_chatgpt_host


ALLOWED_CLOUDFLARE_COOKIE_NAMES = {
    "__cf_bm",
    "__cflb",
    "__cfruid",
    "__cfseq",
    "__cfwaitingroom",
    "_cfuvid",
    "cf_clearance",
    "cf_ob_info",
    "cf_use_ob",
}


@dataclass
class ChatGptCloudflareCookieStore:
    _cookies: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self._cookies is None:
            self._cookies = {}

    def set_cookies(self, cookie_headers: Iterable[str], url: str) -> None:
        if not is_chatgpt_cookie_url(url):
            return
        for header in cookie_headers:
            if not is_allowed_cloudflare_set_cookie_header(header):
                continue
            name = set_cookie_name(header)
            if name is None:
                continue
            value = _set_cookie_pair(header)
            if value is not None:
                self._cookies[name] = value

    def cookies(self, url: str) -> str | None:
        if not is_chatgpt_cookie_url(url):
            return None
        return only_cloudflare_cookies(
            "; ".join(f"{name}={value}" for name, value in self._cookies.items())
        )


SHARED_CHATGPT_CLOUDFLARE_COOKIE_STORE = ChatGptCloudflareCookieStore()


def with_chatgpt_cloudflare_cookie_store(builder):
    return builder.cookie_provider(SHARED_CHATGPT_CLOUDFLARE_COOKIE_STORE)


def is_chatgpt_cookie_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    if not parsed.hostname:
        return False
    return is_allowed_chatgpt_host(parsed.hostname)


def is_allowed_cloudflare_set_cookie_header(header: str) -> bool:
    name = set_cookie_name(header)
    return name is not None and is_allowed_cloudflare_cookie_name(name)


def set_cookie_name(header: str) -> str | None:
    if "=" not in header:
        return None
    name, _rest = header.split("=", 1)
    name = name.strip()
    return name or None


def only_cloudflare_cookies(header: str) -> str | None:
    cookies: list[str] = []
    for cookie in header.split(";"):
        cookie = cookie.strip()
        if "=" not in cookie:
            continue
        name, _value = cookie.split("=", 1)
        if is_allowed_cloudflare_cookie_name(name.strip()):
            cookies.append(cookie)
    return "; ".join(cookies) if cookies else None


def is_allowed_cloudflare_cookie_name(name: str) -> bool:
    return name in ALLOWED_CLOUDFLARE_COOKIE_NAMES or name.startswith("cf_chl_")


def _set_cookie_pair(header: str) -> str | None:
    first = header.split(";", 1)[0].strip()
    if "=" not in first:
        return None
    name, value = first.split("=", 1)
    if not name.strip():
        return None
    return value
