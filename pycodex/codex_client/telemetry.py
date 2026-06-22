"""Request telemetry interface for the Rust ``codex-client`` port.

Rust source:
- ``codex/codex-rs/codex-client/src/telemetry.rs``
"""

from __future__ import annotations

from typing import Protocol
from typing import runtime_checkable

from .error import TransportError


@runtime_checkable
class RequestTelemetry(Protocol):
    """Structural equivalent of Rust ``RequestTelemetry``.

    Rust accepts any ``Send + Sync`` implementor with ``on_request``. Python
    mirrors the call contract structurally and leaves concrete recording to
    core/session telemetry owners.
    """

    def on_request(
        self,
        attempt: int,
        status: int | None,
        error: TransportError | None,
        duration: float,
    ) -> None:
        """Record one API request attempt."""
