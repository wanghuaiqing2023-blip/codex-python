from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from pycodex.aws_auth import (
    AwsAuthConfig,
    AwsAuthContext,
    AwsCredentials,
    AwsRequestToSign,
    Credentials,
    EmptyService,
    InvalidUri,
    SharedCredentialsProvider,
    header_value,
    is_retryable,
)


def _run(coro):
    return asyncio.run(coro)


def _test_context(session_token: str | None = None) -> AwsAuthContext:
    return AwsAuthContext(
        credentials_provider=SharedCredentialsProvider(
            AwsCredentials(
                access_key_id="AKIDEXAMPLE",
                secret_access_key="wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
                session_token=session_token,
            )
        ),
        _region="us-east-1",
        _service="bedrock",
    )


def _test_request() -> AwsRequestToSign:
    return AwsRequestToSign(
        method="POST",
        url="https://bedrock-runtime.us-east-1.amazonaws.com/v1/responses",
        headers={
            "content-type": "application/json",
            "x-test-header": "present",
        },
        body=b'{"model":"openai.gpt-oss-120b-1:0"}',
    )


def test_sign_adds_sigv4_headers_and_preserves_existing_headers():
    # Rust crate/module: codex-aws-auth src/lib.rs,
    # test sign_adds_sigv4_headers_and_preserves_existing_headers.
    signed = _run(
        _test_context().sign_at(
            _test_request(),
            datetime.fromtimestamp(1_700_000_000, tz=UTC),
        )
    )

    assert header_value(signed.headers, "content-type") == "application/json"
    assert header_value(signed.headers, "x-test-header") == "present"
    assert signed.url == "https://bedrock-runtime.us-east-1.amazonaws.com/v1/responses"
    assert header_value(signed.headers, "authorization").startswith("AWS4-HMAC-SHA256 ")
    assert header_value(signed.headers, "x-amz-date") is not None


def test_sign_includes_session_token_when_credentials_have_one():
    # Rust crate/module: codex-aws-auth src/lib.rs,
    # test sign_includes_session_token_when_credentials_have_one.
    signed = _run(
        _test_context("session-token").sign_at(
            _test_request(),
            datetime.fromtimestamp(1_700_000_000, tz=UTC),
        )
    )

    assert header_value(signed.headers, "x-amz-security-token") == "session-token"


def test_credentials_provider_failures_are_retryable():
    # Rust crate/module: codex-aws-auth src/lib.rs,
    # test credentials_provider_failures_are_retryable.
    assert is_retryable(Credentials.provider_error("temporarily unavailable"))
    assert Credentials.provider_timed_out(1).is_retryable()


def test_deterministic_aws_auth_errors_are_not_retryable():
    # Rust crate/module: codex-aws-auth src/lib.rs,
    # test deterministic_aws_auth_errors_are_not_retryable.
    assert not EmptyService().is_retryable()
    assert not Credentials.not_loaded_no_source().is_retryable()
    assert not Credentials.invalid_configuration("bad profile").is_retryable()
    assert not Credentials.unhandled("unexpected response").is_retryable()
    assert not InvalidUri("bad").is_retryable()


def test_load_rejects_empty_service_name():
    # Rust crate/module: codex-aws-auth src/lib.rs,
    # test load_rejects_empty_service_name.
    with pytest.raises(EmptyService, match="AWS service name must not be empty"):
        _run(AwsAuthContext.load(AwsAuthConfig(profile=None, region=None, service="   "), env={}))


def test_load_trims_service_and_exposes_region():
    context = _run(
        AwsAuthContext.load(
            AwsAuthConfig(profile=None, region="us-east-1", service=" bedrock "),
            env={
                "AWS_ACCESS_KEY_ID": "AKIDEXAMPLE",
                "AWS_SECRET_ACCESS_KEY": "secret",
            },
        )
    )

    assert context.region() == "us-east-1"
    assert context.service() == "bedrock"
    assert "AKIDEXAMPLE" not in repr(context)
