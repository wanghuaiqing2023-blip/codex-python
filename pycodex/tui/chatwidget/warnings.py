"""Semantic port of codex-rs/tui/src/chatwidget/warnings.rs."""

from __future__ import annotations

from dataclasses import dataclass, field

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::warnings",
    source="codex/codex-rs/tui/src/chatwidget/warnings.rs",
)

FALLBACK_MODEL_METADATA_WARNING_PREFIX = "Model metadata for `"
FALLBACK_MODEL_METADATA_WARNING_SUFFIX = (
    "` not found. Defaulting to fallback metadata; this can degrade performance and cause issues."
)


@dataclass
class WarningDisplayState:
    """Tracks fallback model metadata warnings that have already been shown."""

    fallback_model_metadata_slugs: set[str] = field(default_factory=set)

    def should_display(self, message: str) -> bool:
        slug = fallback_model_metadata_warning_slug(message)
        if slug is None:
            return True
        if slug in self.fallback_model_metadata_slugs:
            return False
        self.fallback_model_metadata_slugs.add(slug)
        return True


def fallback_model_metadata_warning_slug(message: str) -> str | None:
    if not message.startswith(FALLBACK_MODEL_METADATA_WARNING_PREFIX):
        return None
    if not message.endswith(FALLBACK_MODEL_METADATA_WARNING_SUFFIX):
        return None
    return message[
        len(FALLBACK_MODEL_METADATA_WARNING_PREFIX) : -len(FALLBACK_MODEL_METADATA_WARNING_SUFFIX)
    ]


__all__ = [
    "FALLBACK_MODEL_METADATA_WARNING_PREFIX",
    "FALLBACK_MODEL_METADATA_WARNING_SUFFIX",
    "RUST_MODULE",
    "WarningDisplayState",
    "fallback_model_metadata_warning_slug",
]
