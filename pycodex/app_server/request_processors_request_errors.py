"""Error helpers for ``request_processors/request_errors.rs``.

Rust keeps this helper inside the ``request_processors`` module tree. Python
uses a flat module name because ``request_processors.py`` already represents
the parent Rust module.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pycodex.protocol import CodexErr


def environment_selection_error_message(err: Any) -> str:
    """Mirror Rust's ``environment_selection_error_message``.

    ``CodexErr::InvalidRequest(message)`` returns the raw message so callers
    can wrap it as JSON-RPC invalid params/request text. Every other error uses
    its display string.
    """

    message = _invalid_request_message(err)
    return message if message is not None else str(err)


def _invalid_request_message(err: Any) -> str | None:
    if isinstance(err, CodexErr):
        if err.kind == "invalid_request":
            return err.message or ""
        return None

    kind = _field(err, "kind")
    if kind is None:
        kind = _field(err, "type")
    if _is_invalid_request_kind(kind):
        message = _field(err, "message")
        return "" if message is None else str(message)
    return None


def _is_invalid_request_kind(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value in {"InvalidRequest", "invalid_request", "invalidRequest"}


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


__all__ = ["environment_selection_error_message"]
