"""Crate-root facade for Rust ``codex-cloud-tasks-client``.

Rust source: ``codex/codex-rs/cloud-tasks-client/src/lib.rs``.

The Rust crate root publicly re-exports the API value types plus ``HttpClient``.
Python keeps that import surface available while the concrete ``api.rs`` and
``http.rs`` runtime mappings are tracked as separate module work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from .api import ApplyOutcome
from .api import ApplyStatus
from .api import AttemptStatus
from .api import CloudBackend
from .api import CloudTaskError
from .api import CreatedTask
from .api import DiffSummary
from .api import Result
from .api import TaskId
from .api import TaskListPage
from .api import TaskStatus
from .api import TaskSummary
from .api import TaskText
from .api import TurnAttempt
from .http import HttpClient


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "ApplyOutcome",
    "ApplyStatus",
    "AttemptStatus",
    "CloudBackend",
    "CloudTaskError",
    "CreatedTask",
    "DiffSummary",
    "HttpClient",
    "Result",
    "TaskId",
    "TaskListPage",
    "TaskStatus",
    "TaskSummary",
    "TaskText",
    "TurnAttempt",
]
