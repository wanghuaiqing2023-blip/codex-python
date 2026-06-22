from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pycodex.aws_auth.signing import (
    AwsRequestToSign,
    InvalidHeaderValue,
    InvalidUri,
    SigningParams,
    header_value,
    sign_request,
)
from pycodex.aws_auth.config import AwsCredentials


def _credentials(session_token: str | None = None) -> AwsCredentials:
    return AwsCredentials(
        access_key_id="AKIDEXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
        session_token=session_token,
    )


def _request() -> AwsRequestToSign:
    return AwsRequestToSign(
        method="POST",
        url="https://bedrock-runtime.us-east-1.amazonaws.com/v1/responses",
        headers={
            "content-type": "application/json",
            "x-test-header": "present",
        },
        body=b'{"model":"openai.gpt-oss-120b-1:0"}',
    )


def _sign(session_token: str | None = None):
    return sign_request(
        _credentials(session_token),
        "us-east-1",
        "bedrock",
        _request(),
        datetime.fromtimestamp(1_700_000_000, tz=UTC),
    )


def test_sign_adds_sigv4_headers_and_preserves_existing_headers():
    # Rust crate/module: codex-aws-auth src/signing.rs::sign_request,
    # exercised by lib.rs::sign_adds_sigv4_headers_and_preserves_existing_headers.
    signed = _sign()

    assert header_value(signed.headers, "content-type") == "application/json"
    assert header_value(signed.headers, "x-test-header") == "present"
    assert signed.url == "https://bedrock-runtime.us-east-1.amazonaws.com/v1/responses"
    assert header_value(signed.headers, "authorization").startswith("AWS4-HMAC-SHA256 ")
    assert header_value(signed.headers, "x-amz-date") == "20231114T221320Z"


def test_sign_includes_session_token_when_credentials_have_one():
    signed = _sign("session-token")

    assert header_value(signed.headers, "x-amz-security-token") == "session-token"
    assert "x-amz-security-token" in header_value(signed.headers, "authorization")


def test_signing_is_deterministic_for_fixed_time_and_request():
    first = _sign()
    second = _sign()

    assert first == second


def test_sign_rejects_non_utf8_header_values():
    request = AwsRequestToSign(
        method="POST",
        url="https://bedrock-runtime.us-east-1.amazonaws.com/v1/responses",
        headers={"x-bad": b"\xff"},
        body=b"{}",
    )

    with pytest.raises(InvalidHeaderValue, match="non-UTF8 header value"):
        sign_request(_credentials(), "us-east-1", "bedrock", request, 1_700_000_000)


def test_sign_rejects_invalid_uri_and_missing_signing_params():
    with pytest.raises(InvalidUri, match="request URL is not a valid URI"):
        sign_request(
            _credentials(),
            "us-east-1",
            "bedrock",
            AwsRequestToSign(method="POST", url="/relative", body=b"{}"),
            1_700_000_000,
        )

    with pytest.raises(SigningParams, match="region must not be empty"):
        sign_request(_credentials(), "", "bedrock", _request(), 1_700_000_000)
