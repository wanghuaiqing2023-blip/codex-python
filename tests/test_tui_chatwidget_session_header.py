"""Parity tests for codex-rs/tui/src/chatwidget/session_header.rs."""

from pycodex.tui.chatwidget.session_header import SessionHeader


def test_new_stores_model_text():
    header = SessionHeader.new("gpt-5-codex")

    assert header.model == "gpt-5-codex"


def test_set_model_replaces_changed_model_text():
    header = SessionHeader.new("gpt-5-codex")

    header.set_model("gpt-5")

    assert header.model == "gpt-5"


def test_set_model_is_noop_for_same_model_text():
    header = SessionHeader.new("gpt-5-codex")

    header.set_model("gpt-5-codex")

    assert header.model == "gpt-5-codex"
