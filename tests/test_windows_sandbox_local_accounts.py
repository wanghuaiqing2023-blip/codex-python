from __future__ import annotations

import string
import ctypes
import os

import pytest

from pycodex.windows_sandbox.local_accounts import random_password


def test_random_password_meets_fixed_setup_strength_shape() -> None:
    # Rust owner: setup_main::win::sandbox_users::random_password.
    password = random_password()
    assert len(password) == 24
    assert any(char in string.ascii_uppercase for char in password)
    assert any(char in string.ascii_lowercase for char in password)
    assert any(char in string.digits for char in password)
    assert any(char in "!@#$%^&*()-_=+" for char in password)


def test_random_password_rejects_short_values() -> None:
    with pytest.raises(ValueError, match="at least 16"):
        random_password(8)


@pytest.mark.skipif(os.name != "nt", reason="requires Windows ctypes declarations")
def test_netapi_structures_accept_owned_wide_buffers() -> None:
    from ctypes import wintypes
    from pycodex.windows_sandbox.local_accounts import LOCALGROUP_INFO_1, USER_INFO_1

    name = ctypes.create_unicode_buffer("CodexSandboxTest")
    password = ctypes.create_unicode_buffer("Aa1!abcdefghijkl")
    group = LOCALGROUP_INFO_1(ctypes.cast(name, wintypes.LPWSTR), None)
    user = USER_INFO_1(
        ctypes.cast(name, wintypes.LPWSTR),
        ctypes.cast(password, wintypes.LPWSTR),
        0,
        1,
        None,
        None,
        0,
        None,
    )
    assert group.lgrpi1_name == "CodexSandboxTest"
    assert user.usri1_password == "Aa1!abcdefghijkl"
