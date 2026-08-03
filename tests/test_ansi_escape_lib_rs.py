from pycodex.ansi_escape import Line, Text, ansi_escape, ansi_escape_line, expand_tabs


def test_expand_tabs_replaces_each_tab_with_four_spaces():
    # Rust: codex-ansi-escape/src/lib.rs expand_tabs replaces every tab with four spaces.
    assert expand_tabs("1\tcontent\tend") == "1    content    end"
    assert expand_tabs("plain") == "plain"


def test_ansi_escape_strips_sgr_and_preserves_rendered_lines():
    # Rust: ansi_escape delegates ANSI parsing to ansi-to-tui and returns rendered Text lines.
    text = ansi_escape("\x1b[31mRED\x1b[0m\nplain")
    assert isinstance(text, Text)
    assert [line.text for line in text.lines] == ["RED", "plain"]
    assert text.plain() == "RED\nplain"


def test_ansi_escape_preserves_sgr_style_roles_for_ratatui_consumers():
    # Rust ansi-to-tui keeps SGR style on returned ratatui spans; /diff relies
    # on that contract when Git emits colorized unified diff lines.
    text = ansi_escape("\x1b[31mdeleted\x1b[0m \x1b[38;5;2madded\x1b[0m")

    assert [(span.text, span.style.fg) for span in text.lines[0].spans] == [
        ("deleted", "red"),
        (" ", None),
        ("added", 2),
    ]


def test_ansi_escape_strips_osc_sequences_and_expands_tabs():
    # Rust: ansi_escape normalizes tabs before parsing ANSI content.
    text = ansi_escape("title\x1b]0;ignored\x07\tbody")
    assert [line.text for line in text.lines] == ["title    body"]


def test_ansi_escape_empty_input_returns_single_empty_line():
    assert ansi_escape("").lines == [Line("")]


def test_ansi_escape_line_returns_first_rendered_line():
    # Rust: ansi_escape_line warns on multiple lines and returns the first line.
    assert ansi_escape_line("\tfirst\nsecond").text == "    first"
