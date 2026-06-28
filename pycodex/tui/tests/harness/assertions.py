"""Assertions for TUI virtual-terminal scenario tests."""

from __future__ import annotations


def assert_text_present(text: str, needle: str) -> None:
    assert needle in text, f"expected {needle!r} in terminal output:\n{text}"


def assert_no_duplicate(text: str, needle: str) -> None:
    count = text.count(needle)
    assert count == 1, f"expected {needle!r} once, found {count} times in:\n{text}"


def assert_status_ready(text: str) -> None:
    assert "status: Ready" not in text, f"unexpected Python-only idle status row in:\n{text}"


def assert_status_working(text: str) -> None:
    assert_text_present(text, "Working")
