"""Port of Rust ``codex-client::chatgpt_hosts``.

Rust source:
- ``codex/codex-rs/codex-client/src/chatgpt_hosts.rs``
"""

from __future__ import annotations


_EXACT_HOSTS = frozenset(
    (
        "chatgpt.com",
        "chat.openai.com",
        "chatgpt-staging.com",
    )
)
_SUBDOMAIN_SUFFIXES = (
    ".chatgpt.com",
    ".chatgpt-staging.com",
)


def is_allowed_chatgpt_host(host: str) -> bool:
    """Return whether ``host`` is a first-party ChatGPT host allowed by Rust."""

    return host in _EXACT_HOSTS or any(host.endswith(suffix) for suffix in _SUBDOMAIN_SUFFIXES)


__all__ = [
    "is_allowed_chatgpt_host",
]
