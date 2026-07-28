from __future__ import annotations

import asyncio

import pytest

from pycodex.app_server_transport.transport.remote_control.enroll import (
    RemoteControlEnrollment,
    format_headers,
    load_persisted_remote_control_enrollment,
    preview_remote_control_response_body,
    update_persisted_remote_control_enrollment,
)
from pycodex.app_server_transport.transport.remote_control.protocol import (
    normalize_remote_control_url,
)
from pycodex.state import StateRuntime


@pytest.mark.asyncio
async def test_persisted_enrollment_round_trips_by_target_account_and_client(
    tmp_path,
) -> None:
    runtime = await StateRuntime.init(tmp_path, "test-provider")
    target = normalize_remote_control_url("https://chatgpt.com/remote/control")
    enrollment = RemoteControlEnrollment(
        account_id="account-a",
        environment_id="env-first",
        server_id="server-first",
        server_name="first-server",
    )
    try:
        await update_persisted_remote_control_enrollment(
            runtime,
            target,
            "account-a",
            "desktop-client",
            enrollment,
        )
        assert (
            await load_persisted_remote_control_enrollment(
                runtime,
                target,
                "account-a",
                "desktop-client",
            )
            == enrollment
        )
        assert (
            await load_persisted_remote_control_enrollment(
                runtime,
                target,
                "account-b",
                "desktop-client",
            )
            is None
        )
        await update_persisted_remote_control_enrollment(
            runtime,
            target,
            "account-a",
            "desktop-client",
            None,
        )
        assert (
            await load_persisted_remote_control_enrollment(
                runtime,
                target,
                "account-a",
                "desktop-client",
            )
            is None
        )
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_persistence_requires_state_db_and_matching_account() -> None:
    target = normalize_remote_control_url("https://chatgpt.com/remote/control")
    enrollment = RemoteControlEnrollment(
        account_id="other-account",
        environment_id="env",
        server_id="server",
        server_name="name",
    )
    with pytest.raises(FileNotFoundError, match="sqlite state db is disabled"):
        await load_persisted_remote_control_enrollment(
            None,
            target,
            "account-a",
            None,
        )
    with pytest.raises(FileNotFoundError, match="sqlite state db is disabled"):
        await update_persisted_remote_control_enrollment(
            None,
            target,
            "account-a",
            None,
            enrollment,
        )


def test_response_preview_and_header_format_match_rust_contract() -> None:
    assert preview_remote_control_response_body(b"  ") == "<empty>"
    assert preview_remote_control_response_body(b" ok ") == "ok"
    assert preview_remote_control_response_body(("a" * 5000).encode()).endswith("...")
    assert format_headers({"x-oai-request-id": "req-1", "cf-ray": "ray-1"}) == (
        "request-id: req-1, cf-ray: ray-1"
    )
