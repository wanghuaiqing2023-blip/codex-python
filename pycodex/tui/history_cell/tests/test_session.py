"""Parity tests for codex-rs/tui/src/history_cell/session.rs."""

from pathlib import Path

from pycodex.protocol.models import ManagedFileSystemPermissions, NetworkSandboxPolicy
from pycodex.protocol.models import PermissionProfile as ProtocolPermissionProfile
from pycodex.tui.chatwidget.permission_popups import PermissionProfile
from pycodex.tui.history_cell.session import (
    SESSION_HEADER_MAX_INNER_WIDTH,
    SessionHeaderHistoryCell,
    TooltipHistoryCell,
    card_inner_width,
    has_yolo_permissions,
    line_text,
    new_session_info,
    padded_emoji,
    run_terminal_startup_notices_from_runtime,
    run_terminal_startup_notices_render,
    terminal_startup_notice_lines,
    with_border,
    with_border_with_inner_width,
)


def texts(lines):
    return [line_text(line) for line in lines]


def test_card_inner_width_matches_rust_boundary() -> None:
    assert card_inner_width(3, SESSION_HEADER_MAX_INNER_WIDTH) is None
    assert card_inner_width(4, SESSION_HEADER_MAX_INNER_WIDTH) == 0
    assert card_inner_width(100, 56) == 56
    assert card_inner_width(20, 56) == 16


def test_with_border_uses_widest_content_and_forced_width() -> None:
    assert texts(with_border(["abc"])) == ["╭─────╮", "│ abc │", "╰─────╯"]
    assert texts(with_border_with_inner_width(["abc"], 5)) == [
        "╭───────╮",
        "│ abc   │",
        "╰───────╯",
    ]


def test_padded_emoji_adds_hair_space() -> None:
    assert padded_emoji("!") == "!\u200a"


def test_tooltip_history_cell_display_and_raw_lines() -> None:
    cell = TooltipHistoryCell.new("try /status", ".")

    assert texts(cell.display_lines(80)) == ["  Tip: try /status"]
    assert texts(cell.raw_lines()) == ["Tip: try /status"]


def test_terminal_startup_notice_lines_strip_tip_markdown_and_dedupe_warnings() -> None:
    # Rust crate/module:
    # - codex-tui::history_cell::session::TooltipHistoryCell
    # - codex-tui::chatwidget warning history cells
    # Contract: terminal startup notices own the visible scrollback text shape
    # outside the runner, preserving tooltip copy and warning de-duplication.
    assert terminal_startup_notice_lines(
        "Try **/status** or __/model__.",
        ["MCP startup incomplete", "MCP startup incomplete", "Another warning"],
    ) == (
        "\u2022 Tip: Try /status or /model.",
        "\u2022 MCP startup incomplete",
        "\u2022 Another warning",
    )


def test_run_terminal_startup_notices_render_uses_runtime_providers_and_writers() -> None:
    # Rust owner: history_cell/session.rs owns startup tooltip history cells.
    # The terminal runner should provide runtime sources and history writers,
    # while this boundary shapes notices and inserts the separating blank line.
    class Runtime:
        tooltip = "Try **/status**."
        warnings = ["MCP startup incomplete", "MCP startup incomplete"]

    writes: list[str] = []
    blank_lines: list[str] = []

    notices = run_terminal_startup_notices_render(
        Runtime(),
        startup_tooltip=lambda runtime: runtime.tooltip,
        startup_warnings=lambda runtime: runtime.warnings,
        write_history_cell=writes.append,
        write_blank_line=lambda: blank_lines.append("blank"),
    )

    assert notices == (
        "\u2022 Tip: Try /status.",
        "\u2022 MCP startup incomplete",
    )
    assert writes == list(notices)
    assert blank_lines == ["blank"]


def test_run_terminal_startup_notices_render_skips_blank_line_without_notices() -> None:
    writes: list[str] = []
    blank_lines: list[str] = []

    notices = run_terminal_startup_notices_render(
        object(),
        startup_tooltip=lambda _: None,
        startup_warnings=lambda _: [],
        write_history_cell=writes.append,
        write_blank_line=lambda: blank_lines.append("blank"),
    )

    assert notices == ()
    assert writes == []
    assert blank_lines == []


def test_run_terminal_startup_notices_from_runtime_uses_canonical_providers(monkeypatch) -> None:
    # Rust owner: history_cell/session.rs owns startup notice shaping.  The
    # terminal runner should not import runtime tooltip/warning providers.
    from pycodex.tui import runtime_projection

    class Runtime:
        pass

    monkeypatch.setattr(runtime_projection, "_runtime_startup_tooltip", lambda runtime: "Try **/model**.")
    monkeypatch.setattr(
        runtime_projection,
        "_runtime_startup_warnings",
        lambda runtime: ("warning one", "warning one"),
    )

    writes: list[str] = []
    blanks: list[str] = []

    notices = run_terminal_startup_notices_from_runtime(
        Runtime(),
        write_history_cell=writes.append,
        write_blank_line=lambda: blanks.append("blank"),
    )

    assert notices == ("\u2022 Tip: Try /model.", "\u2022 warning one")
    assert writes == list(notices)
    assert blanks == ["blank"]


def test_session_header_raw_lines_include_reasoning_and_yolo() -> None:
    cell = SessionHeaderHistoryCell.new("gpt-5", "high", True, Path("/tmp"), "1.2.3")
    cell.with_yolo_mode(True)

    raw = texts(cell.raw_lines())

    assert raw[0] == "OpenAI Codex (v1.2.3)"
    assert raw[1] == "model: gpt-5 high"
    assert raw[2].startswith("directory: ")
    assert raw[3] == "permissions: YOLO mode"
    rendered = "\n".join(texts(cell.display_lines(80)))
    assert "OpenAI Codex" in rendered
    assert "/model to change" in rendered
    assert "YOLO mode" in rendered


def test_has_yolo_permissions_matches_approval_and_profile_rules() -> None:
    # Rust crate/module: codex-tui::history_cell::session.
    # Rust tests: yolo_mode_includes_managed_full_access_profiles and
    # yolo_mode_excludes_external_sandbox_profiles.
    assert has_yolo_permissions("Never", "Disabled") is True
    assert has_yolo_permissions("never", {"file_system": "unrestricted", "network": "enabled"}) is True
    assert has_yolo_permissions("never", PermissionProfile.disabled()) is True
    assert has_yolo_permissions("never", ProtocolPermissionProfile.disabled()) is True
    assert (
        has_yolo_permissions(
            "never",
            ProtocolPermissionProfile.managed(
                ManagedFileSystemPermissions.unrestricted(),
                NetworkSandboxPolicy.ENABLED,
            ),
        )
        is True
    )
    assert has_yolo_permissions("on-request", "Disabled") is False
    assert has_yolo_permissions("never", {"file_system": "read_only", "network": "enabled"}) is False
    assert has_yolo_permissions("never", PermissionProfile.read_only(network_access=True)) is False
    assert has_yolo_permissions("never", ProtocolPermissionProfile.external(NetworkSandboxPolicy.ENABLED)) is False


def test_new_session_info_first_event_includes_help_lines() -> None:
    cell = new_session_info(
        {"cwd": ".", "show_tooltips": True},
        "gpt-5",
        {"model": "gpt-5", "approval_policy": "Never", "permission_profile": "Disabled"},
        True,
        "ignored",
        None,
        False,
    )

    rendered = "\n".join(texts(cell.display_lines(100)))

    assert "OpenAI Codex" in rendered
    assert "/init - create an AGENTS.md file" in rendered
    assert "Tip: ignored" not in rendered


def test_new_session_info_non_first_event_adds_tooltip_and_model_change() -> None:
    cell = new_session_info(
        {"cwd": ".", "show_tooltips": True},
        "gpt-4",
        {"model": "gpt-5", "approval_policy": "ask", "permission_profile": "read_only"},
        False,
        "use /model",
        None,
        True,
    )

    rendered = "\n".join(texts(cell.display_lines(120)))
    raw = "\n".join(texts(cell.raw_lines()))

    assert "Tip: use /model" in rendered
    assert "model changed:" in rendered
    assert "requested: gpt-4" in raw
    assert "used: gpt-5" in raw
