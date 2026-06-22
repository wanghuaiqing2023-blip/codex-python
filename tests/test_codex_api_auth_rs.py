"""Rust-derived tests for ``codex-api/src/auth.rs``."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import MutableMapping

from pycodex.codex_api import AuthError
from pycodex.codex_api import AuthHeaderTelemetry
from pycodex.codex_api import AuthProvider
from pycodex.codex_api import auth_header_telemetry
from pycodex.codex_client import Request


class HeaderOnlyAuth:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers

    def add_auth_headers(self, headers: MutableMapping[str, str]) -> None:
        headers.update(self.headers)

    def to_auth_headers(self) -> dict[str, str]:
        return AuthProvider.to_auth_headers(self)

    async def apply_auth(self, request: Request) -> Request:
        return await AuthProvider.apply_auth(self, request)


class CodexApiAuthRsTests(unittest.TestCase):
    def test_auth_error_display_and_transport_mapping(self) -> None:
        # Rust crate/module: codex-api/src/auth.rs
        # Contract: AuthError display text and From<AuthError> for TransportError.
        build = AuthError.build("bad key")
        transient = AuthError.transient("refresh failed")

        self.assertEqual(str(build), "request auth build error: bad key")
        self.assertEqual(str(transient), "transient auth error: refresh failed")

        build_transport = build.to_transport_error()
        transient_transport = transient.to_transport_error()
        self.assertEqual(build_transport.kind, "build")
        self.assertEqual(str(build_transport), "request build error: bad key")
        self.assertEqual(transient_transport.kind, "network")
        self.assertEqual(
            str(transient_transport),
            "network error: refresh failed",
        )

    def test_to_auth_headers_builds_fresh_header_map(self) -> None:
        # Rust crate/module: codex-api/src/auth.rs
        # Contract: AuthProvider::to_auth_headers creates a new HeaderMap and
        # delegates population to add_auth_headers.
        auth = HeaderOnlyAuth({"authorization": "Bearer token"})
        headers = auth.to_auth_headers()
        headers["authorization"] = "changed"

        self.assertEqual(
            auth.to_auth_headers(),
            {"authorization": "Bearer token"},
        )

    def test_header_maps_replace_case_insensitive_names(self) -> None:
        # Rust crate/module: codex-api/src/auth.rs
        # Contract: AuthProvider uses http::HeaderMap, so inserting a header
        # name replaces an existing equivalent header regardless of casing.
        auth = HeaderOnlyAuth({"Authorization": "Bearer fresh"})
        request = Request.new("POST", "https://example.test").with_headers(
            {"authorization": "Bearer stale", "x-existing": "1"}
        )

        self.assertEqual(
            auth.to_auth_headers(),
            {"Authorization": "Bearer fresh"},
        )
        self.assertEqual(
            asyncio.run(auth.apply_auth(request)).headers,
            {"x-existing": "1", "Authorization": "Bearer fresh"},
        )

    def test_default_apply_auth_returns_request_with_auth_headers(self) -> None:
        # Rust crate/module: codex-api/src/auth.rs
        # Contract: default AuthProvider::apply_auth mutates the owned outbound
        # request headers through add_auth_headers and returns that request.
        auth = HeaderOnlyAuth({"authorization": "Bearer token", "x-auth": "yes"})
        request = Request.new("POST", "https://example.test").with_headers(
            {"x-existing": "1"}
        )

        authed = asyncio.run(auth.apply_auth(request))

        self.assertEqual(request.headers, {"x-existing": "1"})
        self.assertEqual(
            authed.headers,
            {
                "x-existing": "1",
                "authorization": "Bearer token",
                "x-auth": "yes",
            },
        )

    def test_auth_header_telemetry_detects_authorization_header(self) -> None:
        # Rust crate/module: codex-api/src/auth.rs
        # Contract: telemetry only reports the authorization header name when it
        # is attached by the provider.
        self.assertEqual(
            auth_header_telemetry(HeaderOnlyAuth({"Authorization": "Bearer token"})),
            AuthHeaderTelemetry(attached=True, name="authorization"),
        )
        self.assertEqual(
            auth_header_telemetry(HeaderOnlyAuth({"x-auth": "yes"})),
            AuthHeaderTelemetry(attached=False, name=None),
        )


if __name__ == "__main__":
    unittest.main()
