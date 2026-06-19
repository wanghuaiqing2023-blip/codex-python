"""SigV4 request signing helpers.

Python port of ``codex/codex-rs/aws-auth/src/signing.rs``.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, quote, urlsplit

from .config import AwsAuthError, AwsCredentials


class InvalidUri(AwsAuthError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return f"request URL is not a valid URI: {self.message}"


class BuildHttpRequest(AwsAuthError):
    def __str__(self) -> str:
        return f"failed to construct HTTP request for signing: {self.args[0]}"


class InvalidHeaderValue(AwsAuthError):
    def __str__(self) -> str:
        return f"request contains a non-UTF8 header value: {self.args[0]}"


class SigningRequest(AwsAuthError):
    def __str__(self) -> str:
        return f"failed to build signable request: {self.args[0]}"


class SigningParams(AwsAuthError):
    def __str__(self) -> str:
        return f"failed to build SigV4 signing params: {self.args[0]}"


class SigningFailure(AwsAuthError):
    def __str__(self) -> str:
        return f"SigV4 signing failed: {self.args[0]}"


@dataclass(frozen=True)
class AwsRequestToSign:
    method: str
    url: str
    headers: Mapping[str, str | bytes] = field(default_factory=dict)
    body: bytes = b""


@dataclass(frozen=True)
class AwsSignedRequest:
    url: str
    headers: dict[str, str]


def sign_request(
    credentials: AwsCredentials,
    region: str,
    service: str,
    request: AwsRequestToSign,
    time: datetime | int | float,
) -> AwsSignedRequest:
    headers = _string_headers(request.headers)
    parsed = urlsplit(request.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise InvalidUri(request.url)
    if not region:
        raise SigningParams("region must not be empty")
    if not service:
        raise SigningParams("service name must not be empty")

    signed_headers = dict(headers)
    host = parsed.netloc
    signed_headers.setdefault("host", host)

    timestamp = _as_utc_datetime(time)
    amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = timestamp.strftime("%Y%m%d")
    signed_headers["x-amz-date"] = amz_date
    if credentials.session_token is not None:
        signed_headers["x-amz-security-token"] = credentials.session_token

    canonical_headers, signed_header_names = _canonical_headers(signed_headers)
    canonical_request = "\n".join(
        [
            request.method.upper(),
            _canonical_uri(parsed.path),
            _canonical_query(parsed.query),
            canonical_headers,
            signed_header_names,
            hashlib.sha256(request.body).hexdigest(),
        ]
    )
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        _signing_key(credentials.secret_access_key, date_stamp, region, service),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    signed_headers["Authorization"] = (
        "AWS4-HMAC-SHA256 "
        f"Credential={credentials.access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_header_names}, "
        f"Signature={signature}"
    )
    return AwsSignedRequest(url=request.url, headers=signed_headers)


def header_value(headers: Mapping[str, Any], name: str) -> str | None:
    wanted = name.lower()
    for header_name, value in headers.items():
        if header_name.lower() == wanted:
            if isinstance(value, bytes):
                try:
                    return value.decode("utf-8")
                except UnicodeDecodeError:
                    return None
            return str(value)
    return None


def _string_headers(headers: Mapping[str, str | bytes]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in headers.items():
        if isinstance(value, bytes):
            try:
                text = value.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise InvalidHeaderValue(str(exc)) from exc
        else:
            text = str(value)
        result[str(name)] = text
    return result


def _as_utc_datetime(value: datetime | int | float) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return datetime.fromtimestamp(value, tz=UTC)


def _canonical_uri(path: str) -> str:
    if path == "":
        return "/"
    return quote(path, safe="/-_.~")


def _canonical_query(query: str) -> str:
    pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=False)
    encoded = [
        (quote(key, safe="-_.~"), quote(value, safe="-_.~"))
        for key, value in pairs
    ]
    return "&".join(f"{key}={value}" for key, value in sorted(encoded))


def _canonical_headers(headers: Mapping[str, str]) -> tuple[str, str]:
    grouped: dict[str, list[str]] = {}
    for name, value in headers.items():
        lowered = name.lower()
        if lowered == "authorization":
            continue
        normalized = " ".join(value.strip().split())
        grouped.setdefault(lowered, []).append(normalized)
    names = sorted(grouped)
    canonical = "".join(f"{name}:{','.join(grouped[name])}\n" for name in names)
    return canonical, ";".join(names)


def _signing_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    date_key = _hmac(("AWS4" + secret).encode("utf-8"), date_stamp)
    region_key = _hmac(date_key, region)
    service_key = _hmac(region_key, service)
    return _hmac(service_key, "aws4_request")


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


__all__ = [
    "AwsRequestToSign",
    "AwsSignedRequest",
    "BuildHttpRequest",
    "InvalidHeaderValue",
    "InvalidUri",
    "SigningFailure",
    "SigningParams",
    "SigningRequest",
    "header_value",
    "sign_request",
]
