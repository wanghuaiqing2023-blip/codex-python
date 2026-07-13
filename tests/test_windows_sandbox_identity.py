from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from pycodex.windows_sandbox import dpapi
from pycodex.windows_sandbox.identity import (
    sandbox_setup_is_complete,
    select_identity,
    setup_mismatch_reason,
)
from pycodex.windows_sandbox.setup import SandboxNetworkIdentity


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires Windows DPAPI")


def _write_setup(home: Path, *, ports: list[int] | None = None) -> None:
    marker = home / ".sandbox" / "setup_marker.json"
    users = home / ".sandbox-secrets" / "sandbox_users.json"
    marker.parent.mkdir(parents=True)
    users.parent.mkdir(parents=True)
    marker.write_text(json.dumps({
        "version": 5,
        "offline_username": "offline",
        "online_username": "online",
        "proxy_ports": ports or [],
        "allow_local_binding": False,
    }), encoding="utf-8")
    users.write_text(json.dumps({
        "version": 5,
        "offline": {"username": "offline", "password": base64.b64encode(dpapi.protect(b"off-pass")).decode()},
        "online": {"username": "online", "password": base64.b64encode(dpapi.protect(b"on-pass")).decode()},
    }), encoding="utf-8")


def test_machine_dpapi_round_trip() -> None:
    # Rust owner: windows-sandbox-rs/src/dpapi.rs.
    protected = dpapi.protect("密码-secret".encode("utf-8"))
    assert protected != "密码-secret".encode("utf-8")
    assert dpapi.unprotect(protected).decode("utf-8") == "密码-secret"


def test_identity_selects_offline_and_online_credentials(tmp_path: Path) -> None:
    # Rust owner: windows-sandbox-rs/src/identity.rs::select_identity.
    _write_setup(tmp_path)
    assert sandbox_setup_is_complete(tmp_path)
    assert select_identity(SandboxNetworkIdentity.OFFLINE, tmp_path).password == "off-pass"
    assert select_identity(SandboxNetworkIdentity.ONLINE, tmp_path).password == "on-pass"


def test_identity_detects_offline_proxy_drift(tmp_path: Path) -> None:
    _write_setup(tmp_path, ports=[8123])
    reason = setup_mismatch_reason(
        tmp_path,
        SandboxNetworkIdentity.OFFLINE,
        {"HTTP_PROXY": "http://127.0.0.1:9000"},
    )
    assert reason is not None and "offline firewall settings changed" in reason
    assert setup_mismatch_reason(
        tmp_path,
        SandboxNetworkIdentity.ONLINE,
        {"HTTP_PROXY": "http://127.0.0.1:9000"},
    ) is None
