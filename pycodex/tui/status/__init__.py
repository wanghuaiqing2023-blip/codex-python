"""Semantic package boundary for codex-rs/tui/src/status/mod.rs.

Rust's ``status`` module wires together account/card/helpers/rate_limits and
re-exports selected display helpers. Python mirrors those package-level exports
without marking the submodule behavior complete at this level.
"""

from __future__ import annotations

from .._porting import RustTuiModule
from .account import StatusAccountDisplay
from .card import (
    StatusHistoryHandle,
    new_status_output,
    new_status_output_with_rate_limits,
    new_status_output_with_rate_limits_handle,
)
from .helpers import (
    compose_agents_summary,
    format_directory_display,
    format_tokens_compact,
    plan_type_display_name,
)
from .rate_limits import (
    RateLimitSnapshotDisplay,
    RateLimitWindowDisplay,
    rate_limit_snapshot_display,
    rate_limit_snapshot_display_for_limit,
)


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="status",
    source="codex/codex-rs/tui/src/status/mod.rs",
)

STATUS_SUBMODULES = (
    "account",
    "card",
    "format",
    "helpers",
    "rate_limits",
    "remote_connection",
)


__all__ = [
    "RUST_MODULE",
    "RateLimitSnapshotDisplay",
    "RateLimitWindowDisplay",
    "STATUS_SUBMODULES",
    "StatusAccountDisplay",
    "StatusHistoryHandle",
    "compose_agents_summary",
    "format_directory_display",
    "format_tokens_compact",
    "new_status_output",
    "new_status_output_with_rate_limits",
    "new_status_output_with_rate_limits_handle",
    "plan_type_display_name",
    "rate_limit_snapshot_display",
    "rate_limit_snapshot_display_for_limit",
]
