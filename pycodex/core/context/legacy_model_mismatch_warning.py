from __future__ import annotations

from .fragment import ContextualUserFragmentBase


class LegacyModelMismatchWarning(ContextualUserFragmentBase):
    @classmethod
    def matches_text(cls, text: str) -> bool:
        return text.strip().startswith(
            "Warning: Your account was flagged for potentially high-risk cyber activity"
        )


__all__ = ["LegacyModelMismatchWarning"]
