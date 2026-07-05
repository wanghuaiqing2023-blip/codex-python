from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from pycodex.tui.line_truncation import Span
from pycodex.tui.status.card import (
    CHATGPT_USAGE_URL,
    StatusContextWindowData,
    StatusHistoryCell,
    StatusRateLimitState,
    StatusTokenUsageData,
    TerminalStatusCardData,
    decorate_workspace_sandbox_label,
    format_model_provider,
    new_status_output_with_rate_limits_handle,
    sanitize_base_url,
    status_approval_label,
    status_permission_summary,
    status_permissions_label,
    run_terminal_status_card_from_runtime,
    run_terminal_status_card_render,
    terminal_status_card_data_from_runtime,
    terminal_status_card_lines,
    workspace_root_suffix,
)
from pycodex.tui.status.rate_limits import RateLimitSnapshotDisplay, RateLimitWindowDisplay, StatusRateLimitData
from pycodex.protocol.config_types import AskForApproval


def test_status_handle_finish_rate_limit_refresh_updates_shared_state() -> None:
    # Rust: StatusHistoryHandle::finish_rate_limit_refresh recomposes data and clears refreshing flag.
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    output, handle = new_status_output_with_rate_limits_handle(
        model_name="gpt-5",
        directory=Path("/repo"),
        rate_limits=[],
        now=now,
        refreshing_rate_limits=True,
    )
    snapshot = RateLimitSnapshotDisplay("codex", now, primary=RateLimitWindowDisplay(10.0, "soon", 300))

    handle.finish_rate_limit_refresh([snapshot], now)

    assert output.card.rate_limit_state.refreshing_rate_limits is False
    assert output.card.rate_limit_state.rate_limits.kind == "available"
    assert [row.label for row in output.card.rate_limit_state.rate_limits.rows] == ["5h limit"]


def test_terminal_status_card_lines_keep_scrollback_product_shape() -> None:
    # Rust crate/module:
    # - codex-tui::status::card::new_status_output_with_rate_limits_handle
    # Contract: /status owns the history-facing status surface; the terminal
    # scrollback path keeps its plain-text rendering shape in this module
    # rather than in the runner main loop.
    lines = terminal_status_card_lines(
        TerminalStatusCardData(
            version="0.1.0",
            model="gpt-5.4",
            reasoning_effort="high",
            directory="C:/repo",
            permissions="Read Only (never)",
            agents_summary="AGENTS.md",
            session_id="thread-1",
        )
    )

    assert lines == (
        "\u2022 /status",
        "  >_ OpenAI Codex (0.1.0)",
        "  Model: gpt-5.4 (reasoning high)",
        "  Directory: C:/repo",
        "  Permissions: Read Only (never)",
        "  Agents.md: AGENTS.md",
        "  Session: thread-1",
        "  Limits: data not available yet",
    )


def test_terminal_status_card_data_from_runtime_uses_runtime_providers() -> None:
    # Rust owner: codex-tui::status::card owns the history-facing /status
    # surface; terminal runtime should provide runtime callbacks, not assemble
    # the card fields itself.
    class Thread:
        thread_id = "thread-1"

    class Runtime:
        active_thread_runtime = Thread()

    data = terminal_status_card_data_from_runtime(
        Runtime(),
        display_version=lambda: "0.1.0",
        display_model=lambda runtime: "gpt-5.4",
        reasoning_effort=lambda runtime: "high",
        cwd=lambda runtime: "C:/repo",
        permissions_label=lambda runtime: "Read Only (never)",
        agents_summary=lambda runtime: "AGENTS.md",
    )

    assert data == TerminalStatusCardData(
        version="0.1.0",
        model="gpt-5.4",
        reasoning_effort="high",
        directory="C:/repo",
        permissions="Read Only (never)",
        agents_summary="AGENTS.md",
        session_id="thread-1",
    )


def test_run_terminal_status_card_render_writes_shaped_card() -> None:
    class Runtime:
        active_thread_runtime = object()

    written: list[str] = []

    data = run_terminal_status_card_render(
        Runtime(),
        display_version=lambda: "0.1.0",
        display_model=lambda runtime: "gpt-5.4",
        reasoning_effort=lambda runtime: None,
        cwd=lambda runtime: "C:/repo",
        permissions_label=lambda runtime: "Full Access",
        agents_summary=lambda runtime: "<none>",
        write_history_cell=written.append,
    )

    assert data.session_id == "<none>"
    assert written == [
        "\n".join(
            (
                "\u2022 /status",
                "  >_ OpenAI Codex (0.1.0)",
                "  Model: gpt-5.4",
                "  Directory: C:/repo",
                "  Permissions: Full Access",
                "  Agents.md: <none>",
                "  Session: <none>",
                "  Limits: data not available yet",
            )
        )
    ]


def test_run_terminal_status_card_from_runtime_uses_canonical_providers(monkeypatch) -> None:
    # Rust owner: status/card.rs owns the history-facing /status surface.  The
    # terminal runner should call this boundary instead of importing runtime
    # providers and assembling card fields itself.
    from pycodex.tui import textual_runtime

    class Thread:
        thread_id = "thread-runtime"

    class Runtime:
        active_thread_runtime = Thread()

    monkeypatch.setattr(textual_runtime, "_display_version", lambda: "0.2.0")
    monkeypatch.setattr(textual_runtime, "_runtime_display_model", lambda runtime: "runtime-model")
    monkeypatch.setattr(
        textual_runtime,
        "_runtime_header_reasoning_effort",
        lambda runtime: "medium",
    )
    monkeypatch.setattr(textual_runtime, "_runtime_cwd", lambda runtime: "C:/workspace/repo")
    monkeypatch.setattr(textual_runtime, "_runtime_permissions_label", lambda runtime: "Full Access")
    monkeypatch.setattr(textual_runtime, "_runtime_agents_summary", lambda runtime: "AGENTS.md")

    written: list[str] = []
    data = run_terminal_status_card_from_runtime(Runtime(), write_history_cell=written.append)

    assert data == TerminalStatusCardData(
        version="0.2.0",
        model="runtime-model",
        reasoning_effort="medium",
        directory="C:/workspace/repo",
        permissions="Full Access",
        agents_summary="AGENTS.md",
        session_id="thread-runtime",
    )
    assert written == ["\n".join(terminal_status_card_lines(data))]


def test_token_usage_and_context_window_spans_match_status_card_shape() -> None:
    # Rust: token_usage_spans and context_window_spans build total/input/output and context details.
    cell = StatusHistoryCell(
        model_name="gpt-5",
        token_usage=StatusTokenUsageData(
            total=1234,
            input=1000,
            output=234,
            context_window=StatusContextWindowData(88, 1200, 8000),
        ),
    )

    assert [span.content for span in cell.token_usage_spans()] == ["1.23K", " total ", " (", "1K", " input", " + ", "234", " output", ")"]
    assert [span.content for span in cell.context_window_spans() or ()] == ["88% left", " (", "1.2K", " used / ", "8K", ")"]


def test_rate_limit_lines_cover_missing_stale_and_narrow_window_rows() -> None:
    # Rust: rate_limit_lines chooses missing/stale warning copy and narrows window rows to summary.
    formatter = __import__("pycodex.tui.status.format", fromlist=["FieldFormatter"]).FieldFormatter.from_labels(["5h limit", "Warning", "Limits"])
    cell = StatusHistoryCell(model_name="gpt-5")

    missing = cell.rate_limit_lines(StatusRateLimitState(StatusRateLimitData.missing(), False), 80, formatter)
    assert "data not available yet" in "".join(span.content for span in missing[0].spans)

    refreshing_missing = cell.rate_limit_lines(StatusRateLimitState(StatusRateLimitData.missing(), True), 80, formatter)
    assert "refresh requested; run /status again shortly" in "".join(
        span.content for line in refreshing_missing for span in line.spans
    )

    stale = StatusRateLimitData.stale([RateLimitSnapshotDisplay("unused", datetime.now(timezone.utc)).primary])  # type: ignore[list-item]
    stale = StatusRateLimitData.stale([])
    stale_lines = cell.rate_limit_lines(StatusRateLimitState(stale, True), 80, formatter)
    assert "run /status again shortly" in "".join(span.content for span in stale_lines[-1].spans)

    rows = StatusRateLimitData.available([])
    assert "not available for this account" in "".join(span.content for span in cell.rate_limit_lines(StatusRateLimitState(rows), 80, formatter)[0].spans)


def test_permission_label_helpers_match_rust_branches() -> None:
    # Rust: status_permission_summary, workspace_root_suffix, status_permissions_label, status_approval_label.
    assert status_permission_summary("read-only (network access enabled)") == "read-only with network access"
    assert status_permission_summary("workspace-write") == "workspace"
    assert workspace_root_suffix(["/repo", "/tmp/extra"], "/repo") == " [/tmp/extra]"
    assert decorate_workspace_sandbox_label("workspace", " [/tmp/extra]") == "workspace [/tmp/extra]"
    assert status_approval_label("on-request", "auto-review", "on-request") == "auto-review"
    assert status_permissions_label("read-only", "enabled", "on-request", "read-only", "auto-review") == "Read Only (auto-review)"
    assert status_permissions_label("workspace-write", "enabled", "on-request", "workspace", "on-request", " [/tmp/extra]") == "Workspace [/tmp/extra] (on-request)"
    assert status_permissions_label("danger-full-access", "disabled", "never", "none", "never") == "Full Access"
    assert status_permissions_label("custom", "enabled", "on-request", "workspace", "on-request", " [/tmp/extra]") == "Profile custom (workspace [/tmp/extra], on-request)"


def test_permission_label_helpers_use_rust_enum_display_values() -> None:
    # Rust crate/module/test:
    # - codex-tui::status::card::status_permissions_label
    # - status/tests.rs::status_permissions_read_only_uses_approval_policy_display
    # Contract: AskForApproval is displayed through its kebab-case value, not
    # its debug/type representation.
    assert (
        status_permissions_label("read-only", "enabled", AskForApproval.NEVER, "read-only", AskForApproval.NEVER)
        == "Read Only (never)"
    )


def test_permission_label_helpers_cover_full_disk_managed_status_tests() -> None:
    # Rust crate/module/test:
    # - codex-tui::status::card
    # - status/tests.rs::status_permissions_full_disk_managed_with_network_is_danger_full_access
    # - status/tests.rs::status_permissions_full_disk_managed_without_network_is_external_sandbox
    # Contract: /status keeps custom managed full-disk profiles as Custom,
    # distinguishing network-enabled danger-full-access from external-sandbox.
    assert status_permissions_label(None, "enabled", "on-request", "danger-full-access", "on-request") == "Custom (danger-full-access, on-request)"
    assert status_permissions_label(None, "enabled", "on-request", "external-sandbox", "on-request") == "Custom (external-sandbox, on-request)"


def test_model_provider_and_base_url_sanitizing_match_rust_contract() -> None:
    # Rust: sanitize_base_url strips userinfo/query/fragment/trailing slash; default OpenAI provider hides row.
    class Provider:
        name = "OpenAI"
        def is_openai(self) -> bool:
            return True

    class Config:
        model_provider = Provider()
        model_provider_id = "openai"

    assert sanitize_base_url(" https://u:p@example.com:8443/path/?q=1#frag ") == "https://example.com:8443/path"
    assert sanitize_base_url("not a url") is None
    assert format_model_provider(Config(), None) is None
    assert format_model_provider(Config(), "https://api.example.com/v1/") == "OpenAI - https://api.example.com/v1"


def test_display_lines_include_usage_link_and_hyperlink_metadata() -> None:
    # Rust: display_hyperlink_lines marks CHATGPT_USAGE_URL when visible in status output.
    cell = StatusHistoryCell(model_name="gpt-5", show_chatgpt_usage_link=True)
    text = "\n".join("".join(span.content for span in line.spans) for line in cell.display_lines(120))
    hyperlink_rows = cell.display_hyperlink_lines(120)

    assert "OpenAI Codex" in text
    assert CHATGPT_USAGE_URL in text
    assert any(row["hyperlinks"] for row in hyperlink_rows)
