"""Semantic port of codex-rs/tui/src/chatwidget/review.rs."""

from __future__ import annotations

from dataclasses import dataclass, field

from .._porting import RustTuiModule
from ..auto_review_denials import RecentAutoReviewDenials
from ..token_usage import TokenUsageInfo


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::review",
    source="codex/codex-rs/tui/src/chatwidget/review.rs",
)


@dataclass(frozen=True)
class PreReviewTokenInfoSnapshot:
    """Tri-state model for Rust ``Option<Option<TokenUsageInfo>>``."""

    captured: bool = False
    token_info: TokenUsageInfo | None = None

    @classmethod
    def not_captured(cls) -> "PreReviewTokenInfoSnapshot":
        return cls(captured=False, token_info=None)

    @classmethod
    def captured_value(
        cls,
        token_info: TokenUsageInfo | None,
    ) -> "PreReviewTokenInfoSnapshot":
        return cls(captured=True, token_info=token_info)

    @property
    def is_none(self) -> bool:
        return not self.captured

    @property
    def is_some_none(self) -> bool:
        return self.captured and self.token_info is None

    @property
    def is_some_some(self) -> bool:
        return self.captured and self.token_info is not None


@dataclass
class ReviewState:
    """Code-review flow state for ChatWidget."""

    recent_auto_review_denials: RecentAutoReviewDenials = field(
        default_factory=RecentAutoReviewDenials
    )
    is_review_mode: bool = False
    pre_review_token_info: PreReviewTokenInfoSnapshot = field(
        default_factory=PreReviewTokenInfoSnapshot.not_captured
    )


__all__ = [
    "PreReviewTokenInfoSnapshot",
    "RUST_MODULE",
    "ReviewState",
]
