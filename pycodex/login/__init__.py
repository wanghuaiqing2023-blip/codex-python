"""Public login module for the Python port.

The upstream project exposes login functionality under ``codex-rs/login``.
In this port, the concrete implementation currently lives in
``pycodex.cli.login``; this module provides the expected
``pycodex.login`` import surface while the dedicated package is built out.
"""

from __future__ import annotations

from pycodex.cli import login as _login_impl

__all__ = [
    "AUTH_FILE",
    "AUTH_MODE_API_KEY",
    "AUTH_MODE_CHATGPT",
    "AUTH_MODE_CHATGPT_AUTH_TOKENS",
    "AUTH_MODE_AGENT_IDENTITY",
    "AuthDotJson",
    "auth_file_path",
    "delete_auth_file",
    "read_auth_json",
    "resolve_auth_mode",
    "run_chatgpt_login",
    "safe_format_key",
    "write_auth_json",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    return getattr(_login_impl, name)


def __dir__() -> list[str]:
    return sorted(__all__)
