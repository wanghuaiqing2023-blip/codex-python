from __future__ import annotations

import json
from pathlib import Path

from pycodex.protocol import PermissionProfile
from pycodex.windows_sandbox.resolved_permissions import ResolvedWindowsSandboxPermissions
from pycodex.windows_sandbox.setup import (
    OfflineProxySettings,
    SandboxNetworkIdentity,
    SetupMarker,
    build_elevation_payload,
    loopback_proxy_port_from_url,
    offline_proxy_settings_from_env,
)
from pycodex.windows_sandbox.setup_error import (
    SetupErrorCode,
    SetupErrorReport,
    SetupFailure,
    clear_setup_error_report,
    read_setup_error_report,
    write_setup_error_report,
)


def test_proxy_settings_match_fixed_rust_setup_contract() -> None:
    # Rust owner: windows-sandbox-rs/src/setup.rs::offline_proxy_settings_from_env.
    env = {
        "HTTP_PROXY": "http://127.0.0.1:8123",
        "HTTPS_PROXY": "http://localhost:8123/path",
        "ALL_PROXY": "socks5://[::1]:9000",
        "WS_PROXY": "http://example.com:7777",
        "CODEX_NETWORK_ALLOW_LOCAL_BINDING": "1",
    }
    assert offline_proxy_settings_from_env(env, SandboxNetworkIdentity.OFFLINE) == OfflineProxySettings(
        (8123, 9000), True
    )
    assert offline_proxy_settings_from_env(env, SandboxNetworkIdentity.ONLINE) == OfflineProxySettings()
    assert loopback_proxy_port_from_url("not-a-url") is None


def test_setup_marker_reports_only_offline_firewall_drift() -> None:
    marker = SetupMarker(5, "offline", "online", proxy_ports=(8123,), allow_local_binding=False)
    desired = OfflineProxySettings((9000,), True)
    assert marker.request_mismatch_reason(SandboxNetworkIdentity.ONLINE, desired) is None
    assert "offline firewall settings changed" in (
        marker.request_mismatch_reason(SandboxNetworkIdentity.OFFLINE, desired) or ""
    )


def test_elevation_payload_keeps_helper_root_and_refresh_shape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    extra = tmp_path / "extra"
    workspace.mkdir()
    extra.mkdir()
    home = tmp_path / "home"
    permissions = ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(
        PermissionProfile.read_only(), workspace
    )
    payload = build_elevation_payload(
        permissions,
        workspace,
        {},
        home,
        read_roots_override=(extra,),
        write_roots_override=(),
        refresh_only=True,
    )
    mapping = payload.to_mapping()
    assert mapping["version"] == 5
    assert mapping["refresh_only"] is True
    assert str(extra.resolve()) in mapping["read_roots"]
    assert str((home / ".sandbox-bin").resolve()) in mapping["read_roots"]
    assert mapping["write_roots"] == []
    json.dumps(mapping)


def test_elevation_payload_preserves_missing_deny_paths(tmp_path: Path) -> None:
    # Rust source: windows-sandbox-rs/src/setup.rs.
    # Explicit deny paths must reach setup before the paths exist.
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    missing_read = tmp_path / "future-read-secret"
    missing_write = tmp_path / "future-write-secret"
    permissions = ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(
        PermissionProfile.read_only(), workspace
    )

    payload = build_elevation_payload(
        permissions,
        workspace,
        {},
        tmp_path / "home",
        deny_read_paths=(missing_read,),
        deny_write_paths=(missing_write,),
    )

    assert payload.deny_read_paths == (missing_read.absolute(),)
    assert payload.deny_write_paths == (missing_write.absolute(),)


def test_setup_error_report_round_trips_and_failure_is_structured(tmp_path: Path) -> None:
    report = SetupErrorReport(SetupErrorCode.HELPER_USER_PROVISION_FAILED, "user failed")
    write_setup_error_report(tmp_path, report)
    assert read_setup_error_report(tmp_path) == report
    failure = SetupFailure(report.code, report.message)
    assert str(failure) == "helper_user_provision_failed: user failed"
    clear_setup_error_report(tmp_path)
    assert read_setup_error_report(tmp_path) is None
