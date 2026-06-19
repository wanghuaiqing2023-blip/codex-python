"""Cloud requirements service ported from Rust ``codex-cloud-requirements``.

This crate owns the runtime service that fetches workspace-managed
``requirements.toml`` from the Codex backend. The lower-level loader error type
and shared future abstraction live in ``pycodex.config.cloud_requirements``.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hmac
import json
import os
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pycodex.config import (
    CloudRequirementsLoadError,
    CloudRequirementsLoadErrorCode,
    ConfigRequirementsToml,
)

CLOUD_REQUIREMENTS_TIMEOUT = 15.0
CLOUD_REQUIREMENTS_MAX_ATTEMPTS = 5
CLOUD_REQUIREMENTS_CACHE_FILENAME = "cloud-requirements-cache.json"
CLOUD_REQUIREMENTS_CACHE_REFRESH_INTERVAL = 5 * 60.0
CLOUD_REQUIREMENTS_CACHE_TTL = 30 * 60.0
CLOUD_REQUIREMENTS_LOAD_FAILED_MESSAGE = "Failed to load cloud requirements (workspace-managed policies)."
CLOUD_REQUIREMENTS_PARSE_FAILED_MESSAGE = (
    "Cloud requirements (workspace-managed policies) are invalid and could not be parsed. "
    "Please contact your workspace admin."
)
CLOUD_REQUIREMENTS_AUTH_RECOVERY_FAILED_MESSAGE = (
    "Your authentication session could not be refreshed automatically. Please log out and sign in again."
)
_CACHE_WRITE_HMAC_KEY = b"codex-cloud-requirements-cache-v3-064f8542-75b4-494c-a294-97d3ce597271"
_CACHE_READ_HMAC_KEYS = (_CACHE_WRITE_HMAC_KEY,)


class RetryableFailureKind(str, Enum):
    BACKEND_CLIENT_INIT = "backend_client_init"
    REQUEST = "request"


@dataclass(frozen=True)
class FetchAttemptError(Exception):
    kind: str
    status_code: int | None = None
    message: str = ""
    retryable_kind: RetryableFailureKind | None = None

    @classmethod
    def retryable(
        cls,
        retryable_kind: RetryableFailureKind = RetryableFailureKind.REQUEST,
        status_code: int | None = None,
        message: str = "",
    ) -> "FetchAttemptError":
        return cls("retryable", status_code=status_code, message=message, retryable_kind=retryable_kind)

    @classmethod
    def unauthorized(cls, status_code: int | None = None, message: str = "") -> "FetchAttemptError":
        return cls("unauthorized", status_code=status_code, message=message)

    def is_retryable(self) -> bool:
        return self.kind == "retryable"

    def is_unauthorized(self) -> bool:
        return self.kind == "unauthorized"


class CacheLoadStatus(str, Enum):
    AUTH_IDENTITY_INCOMPLETE = "Skipping cloud requirements cache read because auth identity is incomplete."
    CACHE_FILE_NOT_FOUND = "Cloud requirements cache file not found."
    CACHE_SIGNATURE_INVALID = "Cloud requirements cache failed signature verification."
    CACHE_IDENTITY_INCOMPLETE = "Ignoring cloud requirements cache because cached identity is incomplete."
    CACHE_IDENTITY_MISMATCH = "Ignoring cloud requirements cache for different auth identity."
    CACHE_EXPIRED = "Cloud requirements cache expired."


class CacheReadFailed(Exception):
    def __str__(self) -> str:
        return f"Failed to read cloud requirements cache: {self.args[0]}."


class CacheParseFailed(Exception):
    def __str__(self) -> str:
        return f"Failed to parse cloud requirements cache: {self.args[0]}."


class CloudRequirementsError(Exception):
    pass


class CloudRequirementsLoader:
    def __init__(self, future: Awaitable[ConfigRequirementsToml | None] | Callable[[], Awaitable[ConfigRequirementsToml | None] | ConfigRequirementsToml | None]) -> None:
        self._future = future
        self._task: asyncio.Task[ConfigRequirementsToml | None] | None = None
        self._resolved = False
        self._result: ConfigRequirementsToml | None = None
        self._error: BaseException | None = None

    @classmethod
    def new(
        cls,
        future: Awaitable[ConfigRequirementsToml | None]
        | Callable[[], Awaitable[ConfigRequirementsToml | None] | ConfigRequirementsToml | None],
    ) -> "CloudRequirementsLoader":
        return cls(future)

    async def get(self) -> ConfigRequirementsToml | None:
        if self._resolved:
            if self._error is not None:
                raise self._error
            return self._result
        if self._task is None:
            self._task = asyncio.create_task(self._call_future())
        try:
            self._result = await self._task
        except BaseException as exc:
            self._error = exc
            self._resolved = True
            raise
        self._resolved = True
        return self._result

    async def load(self) -> ConfigRequirementsToml | None:
        return await self.get()

    async def _call_future(self) -> ConfigRequirementsToml | None:
        value = self._future() if callable(self._future) else self._future
        if isinstance(value, Awaitable):
            value = await value
        return value

    def __repr__(self) -> str:
        return "CloudRequirementsLoader()"


@dataclass(frozen=True)
class CloudRequirementsCacheSignedPayload:
    cached_at: datetime
    expires_at: datetime
    chatgpt_user_id: str | None
    account_id: str | None
    contents: str | None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "CloudRequirementsCacheSignedPayload":
        return cls(
            cached_at=_parse_datetime(value.get("cached_at")),
            expires_at=_parse_datetime(value.get("expires_at")),
            chatgpt_user_id=_optional_str(value.get("chatgpt_user_id")),
            account_id=_optional_str(value.get("account_id")),
            contents=_optional_str(value.get("contents")),
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "cached_at": _format_datetime(self.cached_at),
            "expires_at": _format_datetime(self.expires_at),
            "chatgpt_user_id": self.chatgpt_user_id,
            "account_id": self.account_id,
            "contents": self.contents,
        }

    def requirements(self, requirements_base_dir: str | Path) -> ConfigRequirementsToml | None:
        if self.contents is None:
            return None
        with contextlib.suppress(Exception):
            return parse_cloud_requirements(self.contents, requirements_base_dir)
        return None


@dataclass(frozen=True)
class CloudRequirementsCacheFile:
    signed_payload: CloudRequirementsCacheSignedPayload
    signature: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "CloudRequirementsCacheFile":
        payload = value.get("signed_payload")
        if not isinstance(payload, dict):
            raise ValueError("missing signed_payload")
        signature = value.get("signature")
        if not isinstance(signature, str):
            raise ValueError("missing signature")
        return cls(CloudRequirementsCacheSignedPayload.from_mapping(payload), signature)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "signed_payload": self.signed_payload.to_json_dict(),
            "signature": self.signature,
        }


class RequirementsFetcher(Protocol):
    async def fetch_requirements(self, auth: Any) -> str | None: ...


class BackendRequirementsFetcher:
    def __init__(self, base_url: str, timeout: float = CLOUD_REQUIREMENTS_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def fetch_requirements(self, auth: Any) -> str | None:
        return await asyncio.to_thread(self._fetch_requirements_sync, auth)

    def _fetch_requirements_sync(self, auth: Any) -> str | None:
        token = _call_or_get(auth, "get_token")
        if isinstance(token, Awaitable):
            raise FetchAttemptError.retryable(RetryableFailureKind.BACKEND_CLIENT_INIT)
        path = "/wham/config/requirements" if "/backend-api" in self.base_url else "/api/codex/config/requirements"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise FetchAttemptError.unauthorized(exc.code, f"GET {path} failed: {exc.code}") from exc
            raise FetchAttemptError.retryable(RetryableFailureKind.REQUEST, exc.code, str(exc)) from exc
        except OSError as exc:
            raise FetchAttemptError.retryable(RetryableFailureKind.REQUEST, None, str(exc)) from exc
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise FetchAttemptError.retryable(RetryableFailureKind.REQUEST, None, str(exc)) from exc
        contents = decoded.get("contents") if isinstance(decoded, dict) else None
        return contents if isinstance(contents, str) else None


class CloudRequirementsService:
    def __init__(
        self,
        auth_manager: Any,
        fetcher: RequirementsFetcher,
        codex_home: str | Path,
        timeout: float = CLOUD_REQUIREMENTS_TIMEOUT,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.auth_manager = auth_manager
        self.fetcher = fetcher
        self.requirements_base_dir = Path(codex_home)
        self.cache_path = self.requirements_base_dir / CLOUD_REQUIREMENTS_CACHE_FILENAME
        self.timeout = timeout
        self._sleep = sleep
        self._now = now or (lambda: datetime.now(UTC))

    async def fetch_with_timeout(self) -> ConfigRequirementsToml | None:
        try:
            return await asyncio.wait_for(self.fetch(), timeout=self.timeout)
        except TimeoutError as exc:
            raise CloudRequirementsLoadError.new(
                CloudRequirementsLoadErrorCode.TIMEOUT,
                None,
                f"timed out waiting for cloud requirements after {int(self.timeout)}s",
            ) from exc

    async def fetch(self) -> ConfigRequirementsToml | None:
        auth = await _call_async(self.auth_manager, "auth")
        if auth is None or not cloud_requirements_eligible_auth(auth):
            return None
        chatgpt_user_id, account_id = auth_identity(auth)
        with contextlib.suppress(Exception):
            cached = await self.load_cache(chatgpt_user_id, account_id)
            return cached.requirements(self.requirements_base_dir)
        return await self.fetch_with_retries(auth, "startup")

    async def fetch_with_retries(self, auth: Any, trigger: str = "startup") -> ConfigRequirementsToml | None:
        attempt = 1
        last_status_code: int | None = None
        auth_recovery = _call_or_get(self.auth_manager, "unauthorized_recovery")

        while attempt <= CLOUD_REQUIREMENTS_MAX_ATTEMPTS:
            try:
                contents = await self.fetcher.fetch_requirements(auth)
            except FetchAttemptError as exc:
                last_status_code = exc.status_code
                if exc.is_retryable():
                    if attempt < CLOUD_REQUIREMENTS_MAX_ATTEMPTS:
                        await self._sleep(_backoff(attempt))
                    attempt += 1
                    continue
                if exc.is_unauthorized():
                    if await _has_next(auth_recovery):
                        try:
                            await _next_recovery(auth_recovery)
                        except Exception as recovery_exc:
                            if attempt < CLOUD_REQUIREMENTS_MAX_ATTEMPTS and _is_transient_refresh_error(recovery_exc):
                                await self._sleep(_backoff(attempt))
                                attempt += 1
                                continue
                            message = getattr(recovery_exc, "message", None) or str(recovery_exc)
                            raise CloudRequirementsLoadError.new(
                                CloudRequirementsLoadErrorCode.AUTH,
                                exc.status_code,
                                message or CLOUD_REQUIREMENTS_AUTH_RECOVERY_FAILED_MESSAGE,
                            ) from recovery_exc
                        refreshed_auth = await _call_async(self.auth_manager, "auth")
                        if refreshed_auth is None:
                            raise CloudRequirementsLoadError.new(
                                CloudRequirementsLoadErrorCode.AUTH,
                                exc.status_code,
                                CLOUD_REQUIREMENTS_AUTH_RECOVERY_FAILED_MESSAGE,
                            )
                        auth = refreshed_auth
                        continue
                    raise CloudRequirementsLoadError.new(
                        CloudRequirementsLoadErrorCode.AUTH,
                        exc.status_code,
                        CLOUD_REQUIREMENTS_AUTH_RECOVERY_FAILED_MESSAGE,
                    ) from exc
                raise

            try:
                requirements = parse_cloud_requirements(contents, self.requirements_base_dir) if contents is not None else None
            except Exception as exc:
                raise CloudRequirementsLoadError.new(
                    CloudRequirementsLoadErrorCode.PARSE,
                    None,
                    format_cloud_requirements_parse_failed_message(contents or "", exc),
                ) from exc

            chatgpt_user_id, account_id = auth_identity(auth)
            with contextlib.suppress(Exception):
                await self.save_cache(chatgpt_user_id, account_id, contents)
            return requirements

        raise CloudRequirementsLoadError.new(
            CloudRequirementsLoadErrorCode.REQUEST_FAILED,
            last_status_code,
            CLOUD_REQUIREMENTS_LOAD_FAILED_MESSAGE,
        )

    async def refresh_cache(self) -> bool:
        auth = await _call_async(self.auth_manager, "auth")
        if auth is None or not cloud_requirements_eligible_auth(auth):
            return False
        with contextlib.suppress(CloudRequirementsLoadError):
            await self.fetch_with_retries(auth, "refresh")
        return True

    async def load_cache(
        self,
        chatgpt_user_id: str | None,
        account_id: str | None,
    ) -> CloudRequirementsCacheSignedPayload:
        if chatgpt_user_id is None or account_id is None:
            raise ValueError(CacheLoadStatus.AUTH_IDENTITY_INCOMPLETE.value)
        try:
            raw = self.cache_path.read_bytes()
        except FileNotFoundError as exc:
            raise FileNotFoundError(CacheLoadStatus.CACHE_FILE_NOT_FOUND.value) from exc
        except OSError as exc:
            raise CacheReadFailed(str(exc)) from exc
        try:
            decoded = json.loads(raw.decode("utf-8"))
            cache_file = CloudRequirementsCacheFile.from_mapping(decoded)
            payload_bytes = cache_payload_bytes(cache_file.signed_payload)
        except Exception as exc:
            raise CacheParseFailed(str(exc)) from exc
        if not verify_cache_signature(payload_bytes, cache_file.signature):
            raise ValueError(CacheLoadStatus.CACHE_SIGNATURE_INVALID.value)
        payload = cache_file.signed_payload
        if payload.chatgpt_user_id is None or payload.account_id is None:
            raise ValueError(CacheLoadStatus.CACHE_IDENTITY_INCOMPLETE.value)
        if payload.chatgpt_user_id != chatgpt_user_id or payload.account_id != account_id:
            raise ValueError(CacheLoadStatus.CACHE_IDENTITY_MISMATCH.value)
        if payload.expires_at <= self._now():
            raise ValueError(CacheLoadStatus.CACHE_EXPIRED.value)
        return payload

    async def save_cache(
        self,
        chatgpt_user_id: str | None,
        account_id: str | None,
        contents: str | None,
    ) -> None:
        now = self._now()
        payload = CloudRequirementsCacheSignedPayload(
            cached_at=now,
            expires_at=now + timedelta(seconds=CLOUD_REQUIREMENTS_CACHE_TTL),
            chatgpt_user_id=chatgpt_user_id,
            account_id=account_id,
            contents=contents,
        )
        payload_bytes = cache_payload_bytes(payload)
        cache_file = CloudRequirementsCacheFile(payload, sign_cache_payload(payload_bytes))
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(cache_file.to_json_dict(), indent=2) + "\n", encoding="utf-8")


def cloud_requirements_loader(
    auth_manager: Any,
    chatgpt_base_url: str,
    codex_home: str | Path,
    *,
    fetcher: RequirementsFetcher | None = None,
    timeout: float = CLOUD_REQUIREMENTS_TIMEOUT,
) -> CloudRequirementsLoader:
    service = CloudRequirementsService(
        auth_manager,
        fetcher or BackendRequirementsFetcher(chatgpt_base_url, timeout=timeout),
        codex_home,
        timeout,
    )
    return CloudRequirementsLoader.new(service.fetch_with_timeout())


async def cloud_requirements_loader_for_storage(
    codex_home: str | Path,
    enable_codex_api_key_env: bool,
    credentials_store_mode: str,
    chatgpt_base_url: str,
) -> CloudRequirementsLoader:
    from pycodex.login.auth.manager import AuthManager

    auth_manager = await AuthManager.new(
        codex_home,
        enable_codex_api_key_env,
        credentials_store_mode,
        chatgpt_base_url,
    )
    return cloud_requirements_loader(auth_manager, chatgpt_base_url, codex_home)


def parse_cloud_requirements(contents: str, requirements_base_dir: str | Path) -> ConfigRequirementsToml | None:
    if not contents.strip():
        return None
    with _temporary_cwd(Path(requirements_base_dir)):
        requirements = ConfigRequirementsToml.from_toml(contents)
    return None if requirements.is_empty() else requirements


def format_cloud_requirements_parse_failed_message(contents: str, err: BaseException) -> str:
    del contents
    return f"{CLOUD_REQUIREMENTS_PARSE_FAILED_MESSAGE}\n\nDetails:\n{err}"


def sign_cache_payload(payload_bytes: bytes) -> str:
    signature = hmac.digest(_CACHE_WRITE_HMAC_KEY, payload_bytes, "sha256")
    return base64.b64encode(signature).decode("ascii")


def verify_cache_signature_with_key(payload_bytes: bytes, signature_bytes: bytes, key: bytes) -> bool:
    expected = hmac.digest(key, payload_bytes, "sha256")
    return hmac.compare_digest(expected, signature_bytes)


def verify_cache_signature(payload_bytes: bytes, signature: str) -> bool:
    try:
        signature_bytes = base64.b64decode(signature, validate=True)
    except ValueError:
        return False
    return any(verify_cache_signature_with_key(payload_bytes, signature_bytes, key) for key in _CACHE_READ_HMAC_KEYS)


def cache_payload_bytes(payload: CloudRequirementsCacheSignedPayload) -> bytes:
    return json.dumps(payload.to_json_dict(), separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def auth_identity(auth: Any) -> tuple[str | None, str | None]:
    return (_optional_str(_call_or_get(auth, "get_chatgpt_user_id")), _optional_str(_call_or_get(auth, "get_account_id")))


def cloud_requirements_eligible_auth(auth: Any) -> bool:
    plan_type = _plan_type_name(_call_or_get(auth, "account_plan_type"))
    if plan_type is None:
        return False
    return bool(_call_or_get(auth, "uses_codex_backend")) and plan_type in {
        "business",
        "enterprise_cbp_usage_based",
        "enterprise",
    }


def status_code_tag(status_code: int | None) -> str:
    return str(status_code) if status_code is not None else "none"


@contextlib.contextmanager
def _temporary_cwd(path: Path) -> Any:
    original = Path.cwd()
    path.mkdir(parents=True, exist_ok=True)
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("datetime field must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _format_datetime(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z")


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _plan_type_name(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        name = value
    elif hasattr(value, "value"):
        name = str(value.value)
    elif hasattr(value, "name"):
        name = str(value.name)
    else:
        name = str(value)
    return name.replace("-", "_").lower()


def _call_or_get(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        item = value.get(name)
        return item() if callable(item) else item
    item = getattr(value, name, None)
    return item() if callable(item) else item


async def _call_async(value: Any, name: str) -> Any:
    result = _call_or_get(value, name)
    if isinstance(result, Awaitable):
        return await result
    return result


async def _has_next(recovery: Any) -> bool:
    if recovery is None:
        return False
    result = _call_or_get(recovery, "has_next")
    if isinstance(result, Awaitable):
        result = await result
    return bool(result)


async def _next_recovery(recovery: Any) -> Any:
    method = getattr(recovery, "next", None)
    if method is None:
        return None
    result = method()
    if isinstance(result, Awaitable):
        return await result
    return result


def _is_transient_refresh_error(error: BaseException) -> bool:
    return "transient" in error.__class__.__name__.lower() or bool(getattr(error, "transient", False))


def _backoff(attempt: int) -> float:
    return min(0.05 * (2 ** max(attempt - 1, 0)), 1.0)


__all__ = [
    "BackendRequirementsFetcher",
    "CLOUD_REQUIREMENTS_AUTH_RECOVERY_FAILED_MESSAGE",
    "CLOUD_REQUIREMENTS_CACHE_FILENAME",
    "CLOUD_REQUIREMENTS_CACHE_REFRESH_INTERVAL",
    "CLOUD_REQUIREMENTS_CACHE_TTL",
    "CLOUD_REQUIREMENTS_LOAD_FAILED_MESSAGE",
    "CLOUD_REQUIREMENTS_MAX_ATTEMPTS",
    "CLOUD_REQUIREMENTS_PARSE_FAILED_MESSAGE",
    "CLOUD_REQUIREMENTS_TIMEOUT",
    "CacheLoadStatus",
    "CloudRequirementsCacheFile",
    "CloudRequirementsCacheSignedPayload",
    "CloudRequirementsError",
    "CloudRequirementsLoader",
    "CloudRequirementsService",
    "FetchAttemptError",
    "RequirementsFetcher",
    "RetryableFailureKind",
    "auth_identity",
    "cache_payload_bytes",
    "cloud_requirements_eligible_auth",
    "cloud_requirements_loader",
    "cloud_requirements_loader_for_storage",
    "format_cloud_requirements_parse_failed_message",
    "parse_cloud_requirements",
    "sign_cache_payload",
    "status_code_tag",
    "verify_cache_signature",
    "verify_cache_signature_with_key",
]
