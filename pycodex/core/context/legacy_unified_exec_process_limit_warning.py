from __future__ import annotations

from .fragment import ContextualUserFragmentBase


class LegacyUnifiedExecProcessLimitWarning(ContextualUserFragmentBase):
    @classmethod
    def matches_text(cls, text: str) -> bool:
        return text.strip().startswith(
            "Warning: The maximum number of unified exec processes you can keep open is"
        )


__all__ = ["LegacyUnifiedExecProcessLimitWarning"]
