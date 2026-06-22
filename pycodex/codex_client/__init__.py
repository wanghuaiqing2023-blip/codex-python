"""Porting surface for Rust ``codex-client``.

Rust source:
- ``codex/codex-rs/codex-client/src/lib.rs``
"""

from __future__ import annotations

from .chatgpt_hosts import is_allowed_chatgpt_host
from .chatgpt_cloudflare_cookies import ChatGptCloudflareCookieStore
from .chatgpt_cloudflare_cookies import is_allowed_cloudflare_cookie_name
from .chatgpt_cloudflare_cookies import is_allowed_cloudflare_set_cookie_header
from .chatgpt_cloudflare_cookies import is_chatgpt_cookie_url
from .chatgpt_cloudflare_cookies import only_cloudflare_cookies
from .chatgpt_cloudflare_cookies import set_cookie_name
from .chatgpt_cloudflare_cookies import with_chatgpt_cloudflare_cookie_store
from .custom_ca import BuildClientWithCustomCa
from .custom_ca import BuildClientWithSystemRoots
from .custom_ca import BuildCustomCaTransportError
from .custom_ca import CODEX_CA_CERT_ENV
from .custom_ca import ConfiguredCaBundle
from .custom_ca import InvalidCaFile
from .custom_ca import MapEnv
from .custom_ca import ReadCaFile
from .custom_ca import RegisterCertificate
from .custom_ca import RegisterRustlsCertificate
from .custom_ca import RustlsClientConfig
from .custom_ca import SSL_CERT_FILE_ENV
from .custom_ca import build_reqwest_client_for_subprocess_tests
from .custom_ca import build_reqwest_client_with_custom_ca
from .custom_ca import configured_ca_bundle
from .custom_ca import maybe_build_rustls_client_config_with_custom_ca
from .default_client import CodexHttpClient
from .default_client import CodexRequestBuilder
from .default_client import CodexRequestSnapshot
from .default_client import trace_headers
from .error import StreamError
from .error import TransportError
from .retry import RetryOn
from .retry import RetryPolicy
from .retry import backoff
from .retry import run_with_retry
from .request import PreparedRequestBody
from .request import Request
from .request import RequestBody
from .request import RequestCompression
from .request import Response
from .sse import IdleTimeout
from .sse import SseResult
from .sse import sse_stream
from .telemetry import RequestTelemetry
from .transport import ByteStream
from .transport import HttpTransport
from .transport import PreparedTransportRequest
from .transport import ReqwestTransport
from .transport import StreamResponse
from .transport import TransportHttpResponse
from .transport import request_body_for_trace


__all__ = [
    "ByteStream",
    "BuildClientWithCustomCa",
    "BuildClientWithSystemRoots",
    "BuildCustomCaTransportError",
    "CODEX_CA_CERT_ENV",
    "ChatGptCloudflareCookieStore",
    "CodexHttpClient",
    "CodexRequestBuilder",
    "CodexRequestSnapshot",
    "ConfiguredCaBundle",
    "HttpTransport",
    "IdleTimeout",
    "InvalidCaFile",
    "MapEnv",
    "PreparedRequestBody",
    "PreparedTransportRequest",
    "ReadCaFile",
    "RegisterCertificate",
    "RegisterRustlsCertificate",
    "Request",
    "RequestBody",
    "RequestCompression",
    "RequestTelemetry",
    "ReqwestTransport",
    "Response",
    "RetryOn",
    "RetryPolicy",
    "RustlsClientConfig",
    "SSL_CERT_FILE_ENV",
    "StreamError",
    "StreamResponse",
    "TransportError",
    "TransportHttpResponse",
    "backoff",
    "build_reqwest_client_for_subprocess_tests",
    "build_reqwest_client_with_custom_ca",
    "configured_ca_bundle",
    "is_allowed_cloudflare_cookie_name",
    "is_allowed_cloudflare_set_cookie_header",
    "is_allowed_chatgpt_host",
    "is_chatgpt_cookie_url",
    "maybe_build_rustls_client_config_with_custom_ca",
    "only_cloudflare_cookies",
    "request_body_for_trace",
    "run_with_retry",
    "set_cookie_name",
    "sse_stream",
    "SseResult",
    "trace_headers",
    "with_chatgpt_cloudflare_cookie_store",
]
