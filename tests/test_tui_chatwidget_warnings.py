"""Parity tests for codex-rs/tui/src/chatwidget/warnings.rs."""

from pycodex.tui.chatwidget.warnings import (
    FALLBACK_MODEL_METADATA_WARNING_PREFIX,
    FALLBACK_MODEL_METADATA_WARNING_SUFFIX,
    WarningDisplayState,
    fallback_model_metadata_warning_slug,
)


def fallback_warning(slug: str) -> str:
    return f"{FALLBACK_MODEL_METADATA_WARNING_PREFIX}{slug}{FALLBACK_MODEL_METADATA_WARNING_SUFFIX}"


def test_fallback_model_metadata_warning_slug_extracts_inner_slug():
    assert fallback_model_metadata_warning_slug(fallback_warning("gpt-5-codex")) == "gpt-5-codex"


def test_fallback_model_metadata_warning_slug_requires_exact_prefix_and_suffix():
    assert fallback_model_metadata_warning_slug("Model metadata for `gpt-5-codex`") is None
    assert fallback_model_metadata_warning_slug("other warning") is None


def test_should_display_deduplicates_fallback_metadata_warnings_by_slug():
    state = WarningDisplayState()
    warning = fallback_warning("gpt-5-codex")

    assert state.should_display(warning) is True
    assert state.should_display(warning) is False


def test_should_display_tracks_distinct_fallback_slugs_independently():
    state = WarningDisplayState()

    assert state.should_display(fallback_warning("gpt-5-codex")) is True
    assert state.should_display(fallback_warning("o4-mini")) is True
    assert state.should_display(fallback_warning("gpt-5-codex")) is False


def test_should_display_always_displays_non_fallback_warnings():
    state = WarningDisplayState()

    assert state.should_display("network is offline") is True
    assert state.should_display("network is offline") is True
