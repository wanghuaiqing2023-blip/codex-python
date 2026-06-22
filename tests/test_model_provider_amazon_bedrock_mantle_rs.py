import asyncio
import unittest

from pycodex.model_provider.amazon_bedrock.mantle import (
    BEDROCK_MANTLE_SERVICE_NAME,
    AwsAuthConfig,
    CodexFatalError,
    aws_auth_config,
    base_url,
    region_from_config,
    resolve_region,
    runtime_base_url,
)
from pycodex.model_provider_info import ModelProviderAwsAuthInfo


class Context:
    def __init__(self, region: str) -> None:
        self._region = region

    def region(self) -> str:
        return self._region


class ModelProviderAmazonBedrockMantleRsTests(unittest.TestCase):
    def test_base_url_uses_region_endpoint(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/mantle.rs
        # base_url_uses_region_endpoint.
        self.assertEqual(
            base_url("ap-northeast-1"),
            "https://bedrock-mantle.ap-northeast-1.api.aws/openai/v1",
        )

    def test_base_url_rejects_unsupported_region(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/mantle.rs
        # base_url_rejects_unsupported_region.
        with self.assertRaises(CodexFatalError) as caught:
            base_url("us-west-1")

        self.assertEqual(
            str(caught.exception),
            "Fatal error: Amazon Bedrock Mantle does not support region `us-west-1`",
        )

    def test_aws_auth_config_uses_profile_and_mantle_service(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/mantle.rs
        # aws_auth_config_uses_profile_and_mantle_service.
        self.assertEqual(
            aws_auth_config(ModelProviderAwsAuthInfo(profile="codex-bedrock", region=None)),
            AwsAuthConfig(profile="codex-bedrock", region=None, service=BEDROCK_MANTLE_SERVICE_NAME),
        )

    def test_aws_auth_config_uses_configured_region(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/mantle.rs
        # aws_auth_config_uses_configured_region.
        self.assertEqual(
            aws_auth_config(ModelProviderAwsAuthInfo(profile=None, region=" us-west-2 ")),
            AwsAuthConfig(profile=None, region="us-west-2", service=BEDROCK_MANTLE_SERVICE_NAME),
        )

    def test_region_from_config_trims_empty_region_to_none(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/mantle.rs
        # region_from_config maps trimmed empty strings to None.
        self.assertIsNone(region_from_config(ModelProviderAwsAuthInfo(region="   ")))

    def test_resolve_region_reads_env_bearer_or_aws_context_region(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/mantle.rs
        # resolve_region handles both BedrockAuthMethod variants.
        self.assertEqual(
            asyncio.run(resolve_region({}, resolve_auth_method=lambda _aws: {"region": "eu-west-1"})),
            "eu-west-1",
        )
        self.assertEqual(
            asyncio.run(resolve_region({}, resolve_auth_method=lambda _aws: {"context": Context("us-east-2")})),
            "us-east-2",
        )

    def test_runtime_base_url_resolves_region_then_formats_endpoint(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/mantle.rs
        # runtime_base_url calls resolve_region and base_url.
        self.assertEqual(
            asyncio.run(runtime_base_url({}, resolve_auth_method=lambda _aws: {"region": "eu-central-1"})),
            "https://bedrock-mantle.eu-central-1.api.aws/openai/v1",
        )


if __name__ == "__main__":
    unittest.main()
