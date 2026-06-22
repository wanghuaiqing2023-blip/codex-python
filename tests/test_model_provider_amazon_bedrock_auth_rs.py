import asyncio
import unittest

from pycodex.model_provider.amazon_bedrock.auth import (
    AWS_BEARER_TOKEN_BEDROCK_ENV_VAR,
    AwsSdkAuth,
    BedrockMantleSigV4AuthProvider,
    EnvBearerToken,
    aws_auth_error_to_auth_error,
    bearer_token_from_env,
    bearer_token_region_from_config,
    remove_headers_not_preserved_by_bedrock_mantle,
    resolve_auth_method,
    resolve_provider_auth,
)
from pycodex.model_provider.amazon_bedrock.mantle import AwsAuthConfig, CodexFatalError
from pycodex.model_provider.bearer_auth_provider import BearerAuthProvider
from pycodex.model_provider_info import ModelProviderAwsAuthInfo


class FakeAwsError(Exception):
    def __init__(self, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class SigningContext:
    def __init__(self) -> None:
        self.seen_headers = None

    def sign(self, request):
        self.seen_headers = dict(request["headers"])
        request["signed"] = True
        return request


class ModelProviderAmazonBedrockAuthRsTests(unittest.TestCase):
    def test_bedrock_bearer_auth_uses_configured_region_and_header(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/auth.rs
        # bedrock_bearer_auth_uses_configured_region_and_header.
        token = "bedrock-api-key-test"
        region = bearer_token_region_from_config(ModelProviderAwsAuthInfo(region=" us-west-2 "))
        provider = BearerAuthProvider(token=token, account_id=None, is_fedramp_account=False)

        self.assertEqual(region, "us-west-2")
        self.assertTrue(provider.to_auth_headers()["Authorization"].startswith("Bearer bedrock-api-key-"))

    def test_bedrock_bearer_auth_rejects_missing_configured_region(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/auth.rs
        # bedrock_bearer_auth_rejects_missing_configured_region.
        with self.assertRaises(CodexFatalError) as caught:
            bearer_token_region_from_config(ModelProviderAwsAuthInfo(region=None))

        self.assertEqual(
            str(caught.exception),
            "Fatal error: Amazon Bedrock bearer token auth requires "
            "`model_providers.amazon-bedrock.aws.region`",
        )

    def test_bearer_token_from_env_trims_and_ignores_empty_values(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/auth.rs
        # bearer_token_from_env trims env values and filters empty strings.
        self.assertEqual(
            bearer_token_from_env({AWS_BEARER_TOKEN_BEDROCK_ENV_VAR: " token "}),
            "token",
        )
        self.assertIsNone(bearer_token_from_env({AWS_BEARER_TOKEN_BEDROCK_ENV_VAR: "   "}))
        self.assertIsNone(bearer_token_from_env({}))

    def test_resolve_auth_method_prefers_env_bearer_token(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/auth.rs
        # resolve_auth_method returns EnvBearerToken before loading AWS SDK auth.
        method = asyncio.run(
            resolve_auth_method(
                ModelProviderAwsAuthInfo(region="eu-west-1"),
                env={AWS_BEARER_TOKEN_BEDROCK_ENV_VAR: " bedrock-token "},
                aws_context_loader=lambda _config: self.fail("AWS loader should not be called"),
            )
        )

        self.assertEqual(method, EnvBearerToken(token="bedrock-token", region="eu-west-1"))

    def test_resolve_auth_method_loads_aws_context_with_mantle_config(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/auth.rs
        # resolve_auth_method falls back to AwsAuthContext::load(aws_auth_config).
        captured = []

        def loader(config):
            captured.append(config)
            return {"context": "ok"}

        method = asyncio.run(
            resolve_auth_method(
                ModelProviderAwsAuthInfo(profile="codex-bedrock", region="ap-south-1"),
                env={},
                aws_context_loader=loader,
            )
        )

        self.assertEqual(
            captured,
            [AwsAuthConfig(profile="codex-bedrock", region="ap-south-1", service="bedrock-mantle")],
        )
        self.assertEqual(method, AwsSdkAuth(context={"context": "ok"}))

    def test_resolve_provider_auth_returns_bearer_or_sigv4_provider(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/auth.rs
        # resolve_provider_auth maps BedrockAuthMethod variants to auth providers.
        bearer = asyncio.run(
            resolve_provider_auth(
                ModelProviderAwsAuthInfo(region="us-east-1"),
                env={AWS_BEARER_TOKEN_BEDROCK_ENV_VAR: "token"},
            )
        )
        sigv4 = asyncio.run(
            resolve_provider_auth(
                ModelProviderAwsAuthInfo(region="us-east-1"),
                env={},
                aws_context_loader=lambda _config: {"signer": "context"},
            )
        )

        self.assertIsInstance(bearer, BearerAuthProvider)
        self.assertEqual(bearer.to_auth_headers(), {"Authorization": "Bearer token"})
        self.assertIsInstance(sigv4, BedrockMantleSigV4AuthProvider)

    def test_bedrock_mantle_sigv4_strips_headers_not_preserved_by_mantle(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/auth.rs
        # bedrock_mantle_sigv4_strips_headers_not_preserved_by_mantle.
        headers = {
            "session_id": "019dae79-15c3-70c3-8736-3219b8602b37",
            "thread_id": "019dae79-15c3-70c3-8736-3219b8602b37",
            "future_identity_header": "019dae79-15c3-70c3-8736-3219b8602b37",
            "x-client-request-id": "request-id",
        }

        remove_headers_not_preserved_by_bedrock_mantle(headers)

        self.assertNotIn("session_id", headers)
        self.assertNotIn("thread_id", headers)
        self.assertNotIn("future_identity_header", headers)
        self.assertEqual(headers.get("x-client-request-id"), "request-id")

    def test_sigv4_apply_auth_strips_headers_before_signing(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/auth.rs
        # apply_auth strips snake_case headers before context signing.
        context = SigningContext()
        provider = BedrockMantleSigV4AuthProvider.new(context)
        request = {"headers": {"thread_id": "thread", "x-client-request-id": "request-id"}}

        signed = asyncio.run(provider.apply_auth(request))

        self.assertTrue(signed["signed"])
        self.assertEqual(context.seen_headers, {"x-client-request-id": "request-id"})

    def test_aws_auth_error_to_auth_error_distinguishes_retryable_errors(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/auth.rs
        # retryable AWS auth errors map to transient auth errors.
        self.assertEqual(str(aws_auth_error_to_auth_error(FakeAwsError("temporary", True))), "transient: temporary")
        self.assertEqual(str(aws_auth_error_to_auth_error(FakeAwsError("bad config", False))), "build: bad config")


if __name__ == "__main__":
    unittest.main()
