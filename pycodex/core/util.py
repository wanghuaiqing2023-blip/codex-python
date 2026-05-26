"""Utility helpers ported from ``core/src/util.rs``."""

from __future__ import annotations

from datetime import timedelta
import logging
from pathlib import Path
import random
from typing import Any

INITIAL_DELAY_MS = 200
BACKOFF_FACTOR = 2.0
FEEDBACK_TAGS_LOGGER_NAME = "feedback_tags"


def feedback_tags(**tags: Any) -> dict[str, Any]:
    """Emit feedback tag metadata through the standard logging module."""

    normalized = dict(tags)
    logging.getLogger(FEEDBACK_TAGS_LOGGER_NAME).info(
        "feedback_tags",
        extra={"feedback_tags": normalized},
    )
    return normalized


def emit_feedback_auth_recovery_tags(
    auth_recovery_mode: str,
    auth_recovery_phase: str,
    auth_recovery_outcome: str,
    auth_request_id: str | None,
    auth_cf_ray: str | None,
    auth_error: str | None,
    auth_error_code: str | None,
) -> dict[str, Any]:
    return feedback_tags(
        auth_recovery_mode=auth_recovery_mode,
        auth_recovery_phase=auth_recovery_phase,
        auth_recovery_outcome=auth_recovery_outcome,
        auth_401_request_id=auth_request_id or "",
        auth_401_cf_ray=auth_cf_ray or "",
        auth_401_error=auth_error or "",
        auth_401_error_code=auth_error_code or "",
    )


def backoff(attempt: int, *, jitter: float | None = None) -> timedelta:
    if attempt < 0:
        raise ValueError("attempt must be non-negative")

    exp = BACKOFF_FACTOR ** max(attempt - 1, 0)
    base = int(INITIAL_DELAY_MS * exp)
    multiplier = random.uniform(0.9, 1.1) if jitter is None else jitter
    return timedelta(milliseconds=int(base * multiplier))


def error_or_panic(message: object, *, debug_assertions: bool | None = None) -> None:
    text = str(message)
    should_panic = __debug__ if debug_assertions is None else debug_assertions
    if should_panic:
        raise RuntimeError(text)
    logging.getLogger(__name__).error(text)


def resolve_path(base: Path | str, path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return Path(base) / candidate


def normalize_thread_name(name: str) -> str | None:
    trimmed = str(name).strip()
    if not trimmed:
        return None
    return trimmed


__all__ = [
    "BACKOFF_FACTOR",
    "FEEDBACK_TAGS_LOGGER_NAME",
    "INITIAL_DELAY_MS",
    "backoff",
    "emit_feedback_auth_recovery_tags",
    "error_or_panic",
    "feedback_tags",
    "normalize_thread_name",
    "resolve_path",
]
