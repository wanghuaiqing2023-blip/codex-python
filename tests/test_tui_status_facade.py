"""Parity tests for Rust ``codex-tui::status`` facade.

Rust source: ``codex/codex-rs/tui/src/status/mod.rs``.
"""

from pycodex.tui import status
from pycodex.tui.status import account, card, helpers, rate_limits


def test_status_parent_facade_reexports_rust_items() -> None:
    """Rust ``mod.rs`` declares status submodules and selected ``pub(crate) use`` exports."""

    assert status.RUST_MODULE.module == "status"
    assert status.RUST_MODULE.source == "codex/codex-rs/tui/src/status/mod.rs"
    assert status.STATUS_SUBMODULES == (
        "account",
        "card",
        "format",
        "helpers",
        "rate_limits",
        "remote_connection",
    )

    assert status.StatusAccountDisplay is account.StatusAccountDisplay
    assert status.StatusHistoryHandle is card.StatusHistoryHandle
    assert status.new_status_output is card.new_status_output
    assert status.new_status_output_with_rate_limits is card.new_status_output_with_rate_limits
    assert status.new_status_output_with_rate_limits_handle is card.new_status_output_with_rate_limits_handle
    assert status.compose_agents_summary is helpers.compose_agents_summary
    assert status.format_directory_display is helpers.format_directory_display
    assert status.format_tokens_compact is helpers.format_tokens_compact
    assert status.plan_type_display_name is helpers.plan_type_display_name
    assert status.RateLimitSnapshotDisplay is rate_limits.RateLimitSnapshotDisplay
    assert status.RateLimitWindowDisplay is rate_limits.RateLimitWindowDisplay
    assert status.rate_limit_snapshot_display is rate_limits.rate_limit_snapshot_display
    assert status.rate_limit_snapshot_display_for_limit is rate_limits.rate_limit_snapshot_display_for_limit
