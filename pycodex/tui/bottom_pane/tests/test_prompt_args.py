"""Parity tests for Rust ``codex-tui::bottom_pane::prompt_args``."""

from pycodex.tui.bottom_pane.prompt_args import parse_slash_name


def test_parse_slash_name_rejects_non_slash_and_empty_name() -> None:
    # Rust contract: no leading slash or empty name returns None.
    assert parse_slash_name("model fast") is None
    assert parse_slash_name("") is None
    assert parse_slash_name("/") is None
    assert parse_slash_name("/  rest") is None


def test_parse_slash_name_splits_name_and_left_trims_rest() -> None:
    # Rust contract: parse `/name <rest>`, trim only leading whitespace from rest.
    assert parse_slash_name("/model gpt-5") == ("model", "gpt-5", 7)
    assert parse_slash_name("/model   gpt-5  ") == ("model", "gpt-5  ", 9)
    assert parse_slash_name("/clear") == ("clear", "", 6)


def test_parse_slash_name_uses_utf8_byte_offset() -> None:
    # Rust returns a byte index, not a Unicode scalar/character index.
    assert parse_slash_name("/模型  参数") == ("模型", "参数", len("/模型  ".encode("utf-8")))


def test_parse_slash_name_treats_unicode_whitespace_as_separator() -> None:
    assert parse_slash_name("/model\tfast") == ("model", "fast", 7)
    assert parse_slash_name("/model\u3000fast") == ("model", "fast", len("/model\u3000".encode("utf-8")))
