"""Parity tests for codex-rs/tui/src/history_cell/notices.rs."""

from pycodex.tui.history_cell.notices import (
    CODEX_REPO_URL,
    RELEASE_NOTES_URL,
    TRUSTED_ACCESS_FOR_CYBER_URL,
    UpdateAvailableHistoryCell,
    line_text,
    new_cyber_policy_error_event,
    new_deprecation_notice,
    new_error_event,
    new_info_event,
    new_warning_event,
)


class UpdateAction:
    def command_str(self) -> str:
        return "brew upgrade codex"


def texts(lines):
    return [line_text(line) for line in lines]


def test_update_available_raw_lines_with_command_action() -> None:
    cell = UpdateAvailableHistoryCell.new("9.9.9", UpdateAction())

    raw = texts(cell.raw_lines())

    assert raw[0] == "Update available!"
    assert raw[1].endswith(" -> 9.9.9")
    assert raw[2] == "Run brew upgrade codex to update."
    assert raw[3:] == ["", "See full release notes:", RELEASE_NOTES_URL]


def test_update_available_raw_lines_without_action_uses_repo_url() -> None:
    cell = UpdateAvailableHistoryCell.new("9.9.9", None)

    assert f"See {CODEX_REPO_URL} for installation options." in texts(cell.raw_lines())
    display_links = cell.display_hyperlink_lines(80)
    destinations = [link.destination for line in display_links for link in line.hyperlinks]
    assert RELEASE_NOTES_URL in destinations


def test_warning_event_is_prefixed_wrapped_cell() -> None:
    cell = new_warning_event("Careful now")

    assert texts(cell.display_lines(80)) == ["! Careful now"]
    assert texts(cell.raw_lines()) == ["Careful now"]


def test_cyber_policy_notice_raw_and_hyperlinks() -> None:
    cell = new_cyber_policy_error_event()

    raw = texts(cell.raw_lines())
    assert raw[0] == "This chat was flagged for possible cybersecurity risk"
    assert "Trusted Access for Cyber program" in raw[1]
    assert raw[2] == TRUSTED_ACCESS_FOR_CYBER_URL

    destinations = [
        link.destination
        for line in cell.display_hyperlink_lines(100)
        for link in line.hyperlinks
    ]
    assert TRUSTED_ACCESS_FOR_CYBER_URL in destinations


def test_deprecation_notice_raw_lines_split_details() -> None:
    cell = new_deprecation_notice("Old flag", "line one\nline two")

    assert texts(cell.raw_lines()) == ["Old flag", "line one", "line two"]
    assert texts(cell.display_lines(80))[0] == "! Old flag"


def test_info_and_error_events_are_plain_cells() -> None:
    info = new_info_event("Saved", "hint")
    error = new_error_event("Boom")

    assert texts(info.display_lines(80)) == ["\u2022 Saved hint"]
    assert texts(info.raw_lines()) == ["\u2022 Saved hint"]
    # Fixed Rust: history_cell::notices::new_error_event uses a black square
    # and U+200A HAIR SPACE before the message.
    assert texts(error.display_lines(80)) == ["\u25a0\u200aBoom"]
