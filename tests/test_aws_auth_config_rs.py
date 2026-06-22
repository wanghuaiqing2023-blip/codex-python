from __future__ import annotations

import asyncio

import pytest

from pycodex.aws_auth.config import (
    AwsAuthConfig,
    AwsSdkConfig,
    EmptyService,
    MissingCredentialsProvider,
    MissingRegion,
    credentials_provider,
    load_sdk_config,
    resolved_region,
)


def _run(coro):
    return asyncio.run(coro)


def test_load_sdk_config_rejects_empty_service_name():
    # Rust crate/module: codex-aws-auth src/config.rs::load_sdk_config,
    # also exercised through lib.rs::load_rejects_empty_service_name.
    with pytest.raises(EmptyService, match="AWS service name must not be empty"):
        _run(load_sdk_config(AwsAuthConfig(profile=None, region=None, service="   "), env={}))


def test_load_sdk_config_preserves_profile_region_and_env_credentials():
    config = _run(
        load_sdk_config(
            AwsAuthConfig(profile="bedrock-dev", region="us-west-2", service="bedrock"),
            env={
                "AWS_ACCESS_KEY_ID": "AKID",
                "AWS_SECRET_ACCESS_KEY": "SECRET",
                "AWS_SESSION_TOKEN": "TOKEN",
            },
        )
    )

    provider = credentials_provider(config)
    assert config.profile == "bedrock-dev"
    assert resolved_region(config) == "us-west-2"
    assert provider.credentials.access_key_id == "AKID"
    assert provider.credentials.secret_access_key == "SECRET"
    assert provider.credentials.session_token == "TOKEN"


def test_load_sdk_config_uses_environment_region_fallback():
    config = _run(
        load_sdk_config(
            AwsAuthConfig(profile=None, region=None, service="bedrock"),
            env={"AWS_DEFAULT_REGION": "us-east-1"},
        )
    )

    assert resolved_region(config) == "us-east-1"


def test_credentials_provider_and_region_report_missing_sdk_parts():
    with pytest.raises(MissingCredentialsProvider, match="credentials provider"):
        credentials_provider(AwsSdkConfig(region="us-east-1"))
    with pytest.raises(MissingRegion, match="region"):
        resolved_region(AwsSdkConfig(credentials_provider=object()))
