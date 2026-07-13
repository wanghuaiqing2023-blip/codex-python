from __future__ import annotations

import base64
import json

import pytest

from pycodex.windows_sandbox.setup_helper import decode_payload
from pycodex.windows_sandbox.setup_error import SetupFailure


def test_setup_helper_decodes_fixed_version_payload() -> None:
    payload = {"version": 5, "codex_home": "C:/tmp", "offline_username": "o"}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    assert decode_payload(encoded) == payload


def test_setup_helper_rejects_invalid_or_stale_payload() -> None:
    with pytest.raises(SetupFailure, match="invalid setup payload"):
        decode_payload("not-base64")
    encoded = base64.b64encode(b'{"version":4}').decode()
    with pytest.raises(SetupFailure, match="setup version mismatch"):
        decode_payload(encoded)
