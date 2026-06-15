"""Parity tests for Rust ``codex-tui::shimmer``.

Rust source: ``codex/codex-rs/tui/src/shimmer.rs``.
"""

import pycodex.tui.shimmer as shimmer_module
from pycodex.tui.color import blend
from pycodex.tui.shimmer import ShimmerStyle, color_for_level, shimmer_spans


def test_shimmer_spans_empty_text_returns_empty_vec() -> None:
    assert shimmer_spans("") == []


def test_shimmer_spans_emits_one_span_per_character() -> None:
    spans = shimmer_spans("abc", elapsed_seconds=0.0)
    assert [span.content for span in spans] == ["a", "b", "c"]
    assert all(isinstance(span.style, ShimmerStyle) for span in spans)


def test_shimmer_sweep_uses_padding_period_and_cosine_band() -> None:
    spans = shimmer_spans("abc", elapsed_seconds=10 / 23 * 2.0)
    assert [span.style for span in spans] == [
        ShimmerStyle(modifier="bold"),
        ShimmerStyle(modifier="bold"),
        ShimmerStyle(modifier="bold"),
    ]


def test_shimmer_sweep_repeats_every_two_seconds() -> None:
    # Rust: shimmer.rs uses elapsed_since_start() % 2.0 before mapping into the sweep period.
    first = shimmer_spans("abcd", elapsed_seconds=0.375)
    repeated = shimmer_spans("abcd", elapsed_seconds=2.375)

    assert [span.style for span in repeated] == [span.style for span in first]


def test_color_for_level_fallback_thresholds() -> None:
    assert color_for_level(0.0) == ShimmerStyle(modifier="dim")
    assert color_for_level(0.19) == ShimmerStyle(modifier="dim")
    assert color_for_level(0.2) == ShimmerStyle()
    assert color_for_level(0.59) == ShimmerStyle()
    assert color_for_level(0.6) == ShimmerStyle(modifier="bold")


def test_truecolor_shimmer_uses_bold_rgb_style() -> None:
    spans = shimmer_spans("x", elapsed_seconds=1.0, has_true_color=True)
    assert len(spans) == 1
    assert spans[0].style.modifier == "bold"
    assert spans[0].style.fg is not None


def test_truecolor_shimmer_uses_default_stdout_probe_when_not_injected(monkeypatch) -> None:
    # Rust: shimmer.rs checks supports_color::on_cached(Stream::Stdout) inside shimmer_spans.
    monkeypatch.setattr(shimmer_module, "supports_truecolor_stdout", lambda: True)

    assert shimmer_spans("x", elapsed_seconds=1.0)[0].style.modifier == "bold"


def test_truecolor_shimmer_blends_default_background_toward_foreground(monkeypatch) -> None:
    # Rust: shimmer.rs truecolor branch blends default_bg/default_fg with center-band intensity * 0.9.
    monkeypatch.setattr(shimmer_module, "default_fg", lambda: (10, 20, 30))
    monkeypatch.setattr(shimmer_module, "default_bg", lambda: (200, 210, 220))

    spans = shimmer_spans("x", elapsed_seconds=10 / 21 * 2.0, has_true_color=True)

    assert spans[0].style == ShimmerStyle(
        modifier="bold",
        fg=blend((200, 210, 220), (10, 20, 30), 0.9),
    )
