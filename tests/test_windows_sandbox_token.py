from __future__ import annotations

import os

import pytest

from pycodex.windows_sandbox import (
    LocalSid,
    WindowsSandboxTokenError,
    create_readonly_token_with_caps_and_user_from,
    create_readonly_token_with_caps_from,
    get_current_token_for_restriction,
    is_token_restricted,
)


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires Windows token APIs")


def test_local_sid_rejects_invalid_sid_string() -> None:
    # Rust owner: codex-windows-sandbox::token::LocalSid::from_string.
    with pytest.raises(WindowsSandboxTokenError, match="invalid SID string"):
        LocalSid("not-a-sid")


def test_current_token_can_be_restricted_with_capability_sid() -> None:
    # Rust owner: codex-windows-sandbox::token::create_token_with_caps_from.
    with get_current_token_for_restriction() as base:
        with LocalSid("S-1-5-21-100-200-300-400") as capability:
            with create_readonly_token_with_caps_from(base, [capability]) as restricted:
                assert is_token_restricted(restricted)


def test_restricted_token_requires_at_least_one_capability_sid() -> None:
    with get_current_token_for_restriction() as base:
        with pytest.raises(WindowsSandboxTokenError, match="no capability SIDs"):
            create_readonly_token_with_caps_from(base, [])


def test_elevated_variant_includes_token_user_restricting_sid() -> None:
    # Rust owner: token::create_readonly_token_with_caps_and_user_from.
    with get_current_token_for_restriction() as base:
        with LocalSid("S-1-5-21-100-200-300-999") as capability:
            with create_readonly_token_with_caps_and_user_from(base, [capability]) as restricted:
                assert is_token_restricted(restricted)
