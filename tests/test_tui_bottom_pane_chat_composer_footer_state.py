"""Parity tests for Rust ``codex-tui::bottom_pane::chat_composer::footer_state``."""

from dataclasses import dataclass

from pycodex.tui.bottom_pane.chat_composer.footer_state import FooterState, Line, Span


def test_flash_visible_matches_rust_expiry_predicate() -> None:
    state = FooterState()

    assert state.flash_visible(now=10.0) is False
    state.show_flash(Line.from_text("Saved"), duration=5.0, now=10.0)

    assert state.flash_visible(now=14.999) is True
    assert state.flash_visible(now=15.0) is False


def test_show_flash_accepts_plain_text_and_stores_line() -> None:
    state = FooterState()

    state.show_flash("Hello", duration=1.0, now=2.0)

    assert state.flash is not None
    assert state.flash.line == Line.from_text("Hello")
    assert state.flash.expires_at == 3.0


def test_show_flash_replaces_existing_flash_and_preserves_line_spans() -> None:
    state = FooterState()
    first = Line.from_text("first")
    second = Line((Span("second", "bold"), Span(" line", "dim")))

    state.show_flash(first, duration=10.0, now=1.0)
    state.show_flash(second, duration=2.0, now=5.0)

    assert state.flash is not None
    assert state.flash.line is second
    assert state.flash.line.text == "second line"
    assert state.flash.line.spans == (Span("second", "bold"), Span(" line", "dim"))
    assert state.flash.expires_at == 7.0


def test_status_line_text_concatenates_span_content() -> None:
    state = FooterState(status_line_value=Line((Span("hello"), Span(" "), Span("world"))))

    assert state.status_line_text() == "hello world"


def test_status_line_text_handles_none_string_and_duck_typed_lines() -> None:
    @dataclass
    class ForeignSpan:
        content: str

    @dataclass
    class ForeignLine:
        spans: tuple[ForeignSpan, ...]

    assert FooterState().status_line_text() is None
    assert FooterState(status_line_value="ready").status_line_text() == "ready"
    assert FooterState(status_line_value=ForeignLine((ForeignSpan("a"), ForeignSpan("b")))).status_line_text() == "ab"


def test_footer_state_preserves_field_defaults_and_mutability() -> None:
    state = FooterState()

    assert state.esc_backtrack_hint is False
    assert state.use_shift_enter_hint is False
    assert state.hint_override is None
    assert state.plan_mode_nudge_visible is False
    assert state.status_line_enabled is False
    state.hint_override = [("Esc", "cancel")]
    assert state.hint_override == [("Esc", "cancel")]
