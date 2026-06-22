import pytest

from pycodex.app_server.attestation import (
    ATTESTATION_GENERATE_TIMEOUT_MILLIS,
    AppServerAttestationStatus,
    app_server_attestation_header_value,
    attestation_request_projection,
)


def test_app_server_attestation_header_value_wraps_opaque_client_payloads() -> None:
    # Rust: attestation.rs::app_server_attestation_header_value_wraps_opaque_client_payloads.
    assert (
        app_server_attestation_header_value(
            AppServerAttestationStatus.OK,
            "v1.opaque-client-payload",
        )
        == '{"v":1,"s":0,"t":"v1.opaque-client-payload"}'
    )


def test_app_server_attestation_header_value_reports_app_server_failures() -> None:
    # Rust: attestation.rs::app_server_attestation_header_value_reports_app_server_failures.
    assert app_server_attestation_header_value(AppServerAttestationStatus.TIMEOUT) == '{"v":1,"s":1}'
    assert app_server_attestation_header_value(AppServerAttestationStatus.REQUEST_FAILED) == '{"v":1,"s":2}'
    assert app_server_attestation_header_value(AppServerAttestationStatus.REQUEST_CANCELED) == '{"v":1,"s":3}'
    assert app_server_attestation_header_value(AppServerAttestationStatus.MALFORMED_RESPONSE) == '{"v":1,"s":4}'


def test_attestation_request_projection_maps_rust_result_branches() -> None:
    assert ATTESTATION_GENERATE_TIMEOUT_MILLIS == 100

    assert attestation_request_projection("no_connection").header_value is None
    assert attestation_request_projection("ok", token="tok").header_value == '{"v":1,"s":0,"t":"tok"}'
    assert attestation_request_projection("request_failed").header_value == '{"v":1,"s":2}'
    assert attestation_request_projection("request_canceled").header_value == '{"v":1,"s":3}'
    assert attestation_request_projection("malformed_response").header_value == '{"v":1,"s":4}'

    timeout = attestation_request_projection("timeout")
    assert timeout.header_value == '{"v":1,"s":1}'
    assert timeout.cancel_request is True


def test_attestation_status_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="unknown attestation status"):
        app_server_attestation_header_value("bad")
