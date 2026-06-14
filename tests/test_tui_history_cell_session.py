"""Parity tests for codex-rs/tui/src/history_cell/session.rs."""

from pathlib import Path

from pycodex.tui.history_cell.session import (
    SESSION_HEADER_MAX_INNER_WIDTH,
    SessionHeaderHistoryCell,
    TooltipHistoryCell,
    card_inner_width,
    has_yolo_permissions,
    line_text,
    new_session_info,
    padded_emoji,
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
    assert texts(with_border(["abc"])) == ["+-----+", "|abc |", "+-----+"]
    assert texts(with_border_with_inner_width(["abc"], 5)) == [
        "+-------+",
        "|abc   |",
        "+-------+",
    ]


def test_padded_emoji_adds_hair_space() -> None:
    assert padded_emoji("!") == "!\u200a"


def test_tooltip_history_cell_display_and_raw_lines() -> None:
    cell = TooltipHistoryCell.new("try /status", ".")

    assert texts(cell.display_lines(80)) == ["  Tip: try /status"]
    assert texts(cell.raw_lines()) == ["Tip: try /status"]


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
    assert has_yolo_permissions("Never", "Disabled") is True
    assert has_yolo_permissions("never", {"file_system": "unrestricted", "network": "enabled"}) is True
    assert has_yolo_permissions("on-request", "Disabled") is False
    assert has_yolo_permissions("never", {"file_system": "read_only", "network": "enabled"}) is False


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
