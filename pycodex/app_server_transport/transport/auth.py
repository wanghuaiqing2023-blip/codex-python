from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping

DEFAULT_MAX_CLOCK_SKEW_SECONDS = 30
MIN_SIGNED_BEARER_SECRET_BYTES = 32
INVALID_AUTHORIZATION_HEADER_MESSAGE = "invalid authorization header"


class WebsocketAuthCliMode(Enum):
    CAPABILITY_TOKEN = "capability-token"
    SIGNED_BEARER_TOKEN = "signed-bearer-token"


class CapabilityTokenSourceKind(Enum):
    TOKEN_FILE = "token-file"
    TOKEN_SHA256 = "token-sha256"


@dataclass(frozen=True)
class AppServerWebsocketCapabilityTokenSource:
    kind: CapabilityTokenSourceKind
    token_file: Path | None = None
    token_sha256: bytes | None = None

    @classmethod
    def from_file(cls, token_file: Path) -> "AppServerWebsocketCapabilityTokenSource":
        return cls(CapabilityTokenSourceKind.TOKEN_FILE, token_file=token_file)

    @classmethod
    def from_sha256(cls, digest: bytes) -> "AppServerWebsocketCapabilityTokenSource":
        return cls(CapabilityTokenSourceKind.TOKEN_SHA256, token_sha256=digest)


class WebsocketAuthConfigKind(Enum):
    CAPABILITY_TOKEN = "capability-token"
    SIGNED_BEARER_TOKEN = "signed-bearer-token"


@dataclass(frozen=True)
class AppServerWebsocketAuthConfig:
    kind: WebsocketAuthConfigKind
    source: AppServerWebsocketCapabilityTokenSource | None = None
    shared_secret_file: Path | None = None
    issuer: str | None = None
    audience: str | None = None
    max_clock_skew_seconds: int = DEFAULT_MAX_CLOCK_SKEW_SECONDS

    @classmethod
    def capability_token(
        cls,
        source: AppServerWebsocketCapabilityTokenSource,
    ) -> "AppServerWebsocketAuthConfig":
        return cls(WebsocketAuthConfigKind.CAPABILITY_TOKEN, source=source)

    @classmethod
    def signed_bearer_token(
        cls,
        shared_secret_file: Path,
        *,
        issuer: str | None = None,
        audience: str | None = None,
        max_clock_skew_seconds: int = DEFAULT_MAX_CLOCK_SKEW_SECONDS,
    ) -> "AppServerWebsocketAuthConfig":
        return cls(
            WebsocketAuthConfigKind.SIGNED_BEARER_TOKEN,
            shared_secret_file=shared_secret_file,
            issuer=issuer,
            audience=audience,
            max_clock_skew_seconds=max_clock_skew_seconds,
        )


@dataclass(frozen=True)
class AppServerWebsocketAuthSettings:
    config: AppServerWebsocketAuthConfig | None = None


@dataclass(frozen=True)
class AppServerWebsocketAuthArgs:
    ws_auth: WebsocketAuthCliMode | None = None
    ws_token_file: Path | None = None
    ws_token_sha256: str | None = None
    ws_shared_secret_file: Path | None = None
    ws_issuer: str | None = None
    ws_audience: str | None = None
    ws_max_clock_skew_seconds: int | None = None

    def try_into_settings(self) -> AppServerWebsocketAuthSettings:
        if self.ws_auth is WebsocketAuthCliMode.CAPABILITY_TOKEN:
            if any(
                value is not None
                for value in (
                    self.ws_shared_secret_file,
                    self.ws_issuer,
                    self.ws_audience,
                    self.ws_max_clock_skew_seconds,
                )
            ):
                raise ValueError(
                    "`--ws-shared-secret-file`, `--ws-issuer`, `--ws-audience`, "
                    "and `--ws-max-clock-skew-seconds` require "
                    "`--ws-auth signed-bearer-token`"
                )
            if self.ws_token_file is not None and self.ws_token_sha256 is not None:
                raise ValueError(
                    "`--ws-token-file` and `--ws-token-sha256` are mutually exclusive"
                )
            if self.ws_token_file is not None:
                source = AppServerWebsocketCapabilityTokenSource.from_file(
                    _absolute_path_arg("--ws-token-file", self.ws_token_file)
                )
            elif self.ws_token_sha256 is not None:
                source = AppServerWebsocketCapabilityTokenSource.from_sha256(
                    _sha256_digest_arg("--ws-token-sha256", self.ws_token_sha256)
                )
            else:
                raise ValueError(
                    "`--ws-token-file` or `--ws-token-sha256` is required when "
                    "`--ws-auth capability-token` is set"
                )
            return AppServerWebsocketAuthSettings(
                AppServerWebsocketAuthConfig.capability_token(source)
            )

        if self.ws_auth is WebsocketAuthCliMode.SIGNED_BEARER_TOKEN:
            if self.ws_token_file is not None or self.ws_token_sha256 is not None:
                raise ValueError(
                    "`--ws-token-file` and `--ws-token-sha256` require "
                    "`--ws-auth capability-token`, not `signed-bearer-token`"
                )
            if self.ws_shared_secret_file is None:
                raise ValueError(
                    "`--ws-shared-secret-file` is required when "
                    "`--ws-auth signed-bearer-token` is set"
                )
            return AppServerWebsocketAuthSettings(
                AppServerWebsocketAuthConfig.signed_bearer_token(
                    _absolute_path_arg(
                        "--ws-shared-secret-file",
                        self.ws_shared_secret_file,
                    ),
                    issuer=_normalize(self.ws_issuer),
                    audience=_normalize(self.ws_audience),
                    max_clock_skew_seconds=(
                        self.ws_max_clock_skew_seconds
                        if self.ws_max_clock_skew_seconds is not None
                        else DEFAULT_MAX_CLOCK_SKEW_SECONDS
                    ),
                )
            )

        if any(
            value is not None
            for value in (
                self.ws_token_file,
                self.ws_token_sha256,
                self.ws_shared_secret_file,
                self.ws_issuer,
                self.ws_audience,
                self.ws_max_clock_skew_seconds,
            )
        ):
            raise ValueError(
                "websocket auth flags require `--ws-auth capability-token` or "
                "`--ws-auth signed-bearer-token`"
            )
        return AppServerWebsocketAuthSettings()


class WebsocketAuthModeKind(Enum):
    CAPABILITY_TOKEN = "capability-token"
    SIGNED_BEARER_TOKEN = "signed-bearer-token"


@dataclass(frozen=True)
class WebsocketAuthMode:
    kind: WebsocketAuthModeKind
    token_sha256: bytes | None = None
    shared_secret: bytes | None = None
    issuer: str | None = None
    audience: str | None = None
    max_clock_skew_seconds: int = 0


@dataclass(frozen=True)
class WebsocketAuthPolicy:
    mode: WebsocketAuthMode | None = None


class WebsocketAuthError(Exception):
    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def policy_from_settings(
    settings: AppServerWebsocketAuthSettings,
) -> WebsocketAuthPolicy:
    config = settings.config
    if config is None:
        return WebsocketAuthPolicy()
    if config.kind is WebsocketAuthConfigKind.CAPABILITY_TOKEN:
        if config.source is None:
            raise ValueError("capability-token auth requires a token source")
        if config.source.kind is CapabilityTokenSourceKind.TOKEN_FILE:
            if config.source.token_file is None:
                raise ValueError("token-file source requires a path")
            digest = _sha256_digest(
                _read_trimmed_secret(config.source.token_file).encode()
            )
        else:
            if config.source.token_sha256 is None:
                raise ValueError("token-sha256 source requires a digest")
            digest = config.source.token_sha256
        return WebsocketAuthPolicy(
            WebsocketAuthMode(
                WebsocketAuthModeKind.CAPABILITY_TOKEN,
                token_sha256=digest,
            )
        )

    if config.shared_secret_file is None:
        raise ValueError("signed bearer auth requires a shared secret file")
    shared_secret = _read_trimmed_secret(config.shared_secret_file).encode()
    if len(shared_secret) < MIN_SIGNED_BEARER_SECRET_BYTES:
        raise ValueError(
            f"signed websocket bearer secret {config.shared_secret_file} must be "
            f"at least {MIN_SIGNED_BEARER_SECRET_BYTES} bytes"
        )
    return WebsocketAuthPolicy(
        WebsocketAuthMode(
            WebsocketAuthModeKind.SIGNED_BEARER_TOKEN,
            shared_secret=shared_secret,
            issuer=config.issuer,
            audience=config.audience,
            max_clock_skew_seconds=config.max_clock_skew_seconds,
        )
    )


def is_unauthenticated_non_loopback_listener(
    bind_host: str,
    policy: WebsocketAuthPolicy,
) -> bool:
    host = bind_host.rsplit(":", 1)[0].strip("[]")
    return host not in {"127.0.0.1", "::1", "localhost"} and policy.mode is None


def authorize_upgrade(
    headers: Mapping[str, str],
    policy: WebsocketAuthPolicy,
) -> None:
    mode = policy.mode
    if mode is None:
        return
    token = _bearer_token_from_headers(headers)
    if mode.kind is WebsocketAuthModeKind.CAPABILITY_TOKEN:
        if mode.token_sha256 is None or not hmac.compare_digest(
            mode.token_sha256,
            _sha256_digest(token.encode()),
        ):
            raise WebsocketAuthError("invalid websocket bearer token")
        return
    if mode.shared_secret is None:
        raise WebsocketAuthError("invalid websocket jwt")
    _verify_signed_bearer_token(
        token,
        mode.shared_secret,
        mode.issuer,
        mode.audience,
        mode.max_clock_skew_seconds,
    )


def _verify_signed_bearer_token(
    token: str,
    shared_secret: bytes,
    issuer: str | None,
    audience: str | None,
    max_clock_skew_seconds: int,
) -> None:
    try:
        header_segment, claims_segment, signature_segment = token.split(".")
        header = json.loads(_decode_base64url(header_segment))
        if header.get("alg") != "HS256":
            raise ValueError
        expected = hmac.new(
            shared_secret,
            f"{header_segment}.{claims_segment}".encode(),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _decode_base64url(signature_segment)):
            raise ValueError
        claims = json.loads(_decode_base64url(claims_segment))
        exp = int(claims["exp"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise WebsocketAuthError("invalid websocket jwt") from None

    now = int(time.time())
    if now > exp + max_clock_skew_seconds:
        raise WebsocketAuthError("expired websocket jwt")
    nbf = claims.get("nbf")
    if nbf is not None and now < int(nbf) - max_clock_skew_seconds:
        raise WebsocketAuthError("websocket jwt is not valid yet")
    if issuer is not None and claims.get("iss") != issuer:
        raise WebsocketAuthError("websocket jwt issuer mismatch")
    if audience is not None:
        actual = claims.get("aud")
        matches = actual == audience or (
            isinstance(actual, list) and audience in actual
        )
        if not matches:
            raise WebsocketAuthError("websocket jwt audience mismatch")


def _bearer_token_from_headers(headers: Mapping[str, str]) -> str:
    raw = next(
        (value for key, value in headers.items() if key.lower() == "authorization"),
        None,
    )
    if raw is None:
        raise WebsocketAuthError("missing websocket bearer token")
    parts = raw.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise WebsocketAuthError(INVALID_AUTHORIZATION_HEADER_MESSAGE)
    return parts[1].strip()


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _absolute_path_arg(flag_name: str, path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise ValueError(f"{flag_name} must be an absolute path")
    return path


def _sha256_digest_arg(flag_name: str, value: str) -> bytes:
    trimmed = value.strip()
    if len(trimmed) != 64:
        raise ValueError(f"{flag_name} must be a 64-character hex SHA-256 digest")
    try:
        return bytes.fromhex(trimmed)
    except ValueError:
        raise ValueError(
            f"{flag_name} must be a 64-character hex SHA-256 digest"
        ) from None


def _sha256_digest(value: bytes) -> bytes:
    return hashlib.sha256(value).digest()


def _read_trimmed_secret(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OSError(
            exc.errno,
            f"failed to read websocket auth secret {path}: {exc}",
            path,
        ) from exc
    trimmed = raw.strip()
    if not trimmed:
        raise ValueError(f"websocket auth secret {path} must not be empty")
    return trimmed


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


__all__ = [
    "AppServerWebsocketAuthArgs",
    "AppServerWebsocketAuthConfig",
    "AppServerWebsocketAuthSettings",
    "AppServerWebsocketCapabilityTokenSource",
    "CapabilityTokenSourceKind",
    "WebsocketAuthCliMode",
    "WebsocketAuthConfigKind",
    "WebsocketAuthError",
    "WebsocketAuthMode",
    "WebsocketAuthModeKind",
    "WebsocketAuthPolicy",
    "authorize_upgrade",
    "is_unauthenticated_non_loopback_listener",
    "policy_from_settings",
]
