from __future__ import annotations

from . import CONTEXTUAL_USER_FRAGMENT_TYPES, FragmentRegistrationProxy


CONTEXTUAL_USER_FRAGMENTS = tuple(
    FragmentRegistrationProxy.new(fragment_type)
    for fragment_type in CONTEXTUAL_USER_FRAGMENT_TYPES
)
STANDARD_CONTEXTUAL_USER_FRAGMENTS = CONTEXTUAL_USER_FRAGMENTS


def is_standard_contextual_user_text(text: str) -> bool:
    return any(fragment.matches_text(text) for fragment in CONTEXTUAL_USER_FRAGMENTS)


__all__ = [
    "CONTEXTUAL_USER_FRAGMENTS",
    "STANDARD_CONTEXTUAL_USER_FRAGMENTS",
    "is_standard_contextual_user_text",
]
