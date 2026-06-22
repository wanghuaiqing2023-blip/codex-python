import unittest

import pycodex.codex_client as codex_client


class CodexClientLibRsTests(unittest.TestCase):
    def test_crate_root_reexports_rust_public_facade(self):
        # Rust crate/module: codex-client/src/lib.rs
        # Contract: every crate-root `pub use` exported by Rust's facade is
        # reachable from the Python package root.
        expected = {
            "with_chatgpt_cloudflare_cookie_store",
            "is_allowed_chatgpt_host",
            "BuildCustomCaTransportError",
            "build_reqwest_client_for_subprocess_tests",
            "build_reqwest_client_with_custom_ca",
            "maybe_build_rustls_client_config_with_custom_ca",
            "CodexHttpClient",
            "CodexRequestBuilder",
            "StreamError",
            "TransportError",
            "PreparedRequestBody",
            "Request",
            "RequestBody",
            "RequestCompression",
            "Response",
            "RetryOn",
            "RetryPolicy",
            "backoff",
            "run_with_retry",
            "sse_stream",
            "RequestTelemetry",
            "ByteStream",
            "HttpTransport",
            "ReqwestTransport",
            "StreamResponse",
        }

        missing = sorted(name for name in expected if not hasattr(codex_client, name))

        self.assertEqual(missing, [])
        self.assertTrue(expected.issubset(set(codex_client.__all__)))

    def test_crate_root_reexports_point_at_canonical_modules(self):
        # Rust crate/module: codex-client/src/lib.rs
        # Contract: facade names are re-exports of sibling module definitions,
        # not stale package-local compatibility copies.
        from pycodex.codex_client import custom_ca
        from pycodex.codex_client import default_client
        from pycodex.codex_client import error
        from pycodex.codex_client import request
        from pycodex.codex_client import retry
        from pycodex.codex_client import sse
        from pycodex.codex_client import telemetry
        from pycodex.codex_client import transport

        self.assertIs(codex_client.BuildCustomCaTransportError, custom_ca.BuildCustomCaTransportError)
        self.assertIs(
            codex_client.build_reqwest_client_with_custom_ca,
            custom_ca.build_reqwest_client_with_custom_ca,
        )
        self.assertIs(codex_client.CodexHttpClient, default_client.CodexHttpClient)
        self.assertIs(codex_client.TransportError, error.TransportError)
        self.assertIs(codex_client.Request, request.Request)
        self.assertIs(codex_client.RetryPolicy, retry.RetryPolicy)
        self.assertIs(codex_client.sse_stream, sse.sse_stream)
        self.assertIs(codex_client.RequestTelemetry, telemetry.RequestTelemetry)
        self.assertIs(codex_client.ReqwestTransport, transport.ReqwestTransport)


if __name__ == "__main__":
    unittest.main()
