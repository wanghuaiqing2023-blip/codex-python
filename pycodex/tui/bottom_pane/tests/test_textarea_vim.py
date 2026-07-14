"""Rust source: codex/codex-rs/tui/src/bottom_pane/textarea/vim.rs."""

from pycodex.tui.bottom_pane.textarea.vim import (
    TextAreaVim,
    TextElement,
    VimMode,
    VimMotion,
    VimOperator,
    VimPending,
    VimTextObject,
    VimTextObjectScope,
    idx_range,
    split_word_pieces,
)


def test_vim_enum_variants_match_rust_module_boundary():
    assert [mode.name for mode in VimMode] == ["Normal", "Insert"]
    assert [operator.name for operator in VimOperator] == ["Delete", "Yank", "Change"]
    assert [motion.name for motion in VimMotion] == [
        "Left",
        "Right",
        "Up",
        "Down",
        "WordForward",
        "WordBackward",
        "WordEnd",
        "LineStart",
        "LineEnd",
    ]
    assert VimPending.None_().kind == "None"
    assert VimPending.Operator(VimOperator.Delete).operator is VimOperator.Delete
    assert VimPending.TextObject(VimOperator.Change, VimTextObjectScope.Inner).scope is VimTextObjectScope.Inner


def test_idx_range_extends_to_quote_width():
    assert idx_range(2, 8, '"') == range(2, 9)


def test_split_word_pieces_splits_separator_runs():
    assert split_word_pieces("hello-world") == [(0, "hello"), (5, "-"), (6, "world")]


def test_word_text_object_inner_and_around_small_word():
    area = TextAreaVim("alpha beta,gamma ", cursor_pos=len("alpha beta,"))

    assert area.text_object_range(VimTextObject.Word, VimTextObjectScope.Inner) == range(11, 16)
    assert area.text_object_range(VimTextObject.Word, VimTextObjectScope.Around) == range(11, 17)


def test_big_word_uses_non_whitespace_run_and_cursor_at_end():
    area = TextAreaVim("alpha beta,gamma", cursor_pos=len("alpha beta,gamma"))

    assert area.text_object_range(VimTextObject.BigWord, VimTextObjectScope.Inner) == range(6, 16)


def test_word_around_prefers_preceding_whitespace_when_no_following_whitespace():
    area = TextAreaVim("alpha beta", cursor_pos=len("alpha beta"))

    assert area.text_object_range(VimTextObject.Word, VimTextObjectScope.Around) == range(5, 10)


def test_paired_text_object_picks_smallest_pair_and_skips_elements():
    area = TextAreaVim("outer(inner(value))", cursor_pos=len("outer(inner("))

    assert area.text_object_range(VimTextObject.Parentheses, VimTextObjectScope.Inner) == range(12, 17)
    assert area.text_object_range(VimTextObject.Parentheses, VimTextObjectScope.Around) == range(11, 18)

    skipped = TextAreaVim("call([x])", cursor_pos=6, elements=[TextElement(range(4, 7))])
    assert skipped.text_object_range(VimTextObject.Brackets, VimTextObjectScope.Around) is None


def test_quoted_text_object_respects_current_line_and_escapes():
    area = TextAreaVim('one "two"\nthree "four"', cursor_pos=len('one "two"\nthree "fo'))

    assert area.text_object_range(VimTextObject.DoubleQuote, VimTextObjectScope.Inner) == range(18, 22)
    assert area.text_object_range(VimTextObject.DoubleQuote, VimTextObjectScope.Around) == range(17, 23)

    escaped = TextAreaVim(r'one "two" plain', cursor_pos=len(r'one "two'))
    assert escaped.text_object_range(VimTextObject.DoubleQuote, VimTextObjectScope.Inner) is None
