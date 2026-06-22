from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pycodex.cloud_requirements import (
    CLOUD_REQUIREMENTS_AUTH_RECOVERY_FAILED_MESSAGE,
    CLOUD_REQUIREMENTS_CACHE_FILENAME,
    CLOUD_REQUIREMENTS_LOAD_FAILED_MESSAGE,
    CLOUD_REQUIREMENTS_PARSE_FAILED_MESSAGE,
    CLOUD_REQUIREMENTS_MAX_ATTEMPTS,
    CloudRequirementsCacheSignedPayload,
    CloudRequirementsService,
    FetchAttemptError,
    RetryableFailureKind,
    cache_payload_bytes,
    cloud_requirements_eligible_auth,
    cloud_requirements_loader,
    format_cloud_requirements_parse_failed_message,
    parse_cloud_requirements,
    sign_cache_payload,
    verify_cache_signature,
)
from pycodex.config import CloudRequirementsLoadError, CloudRequirementsLoadErrorCode
from pycodex.protocol.config_types import AskForApproval


class FakeAuth:
    def __init__(
        self,
        plan: str | None = "business",
        *,
        backend: bool = True,
        user_id: str | None = "user-12345",
        account_id: str | None = "account-12345",
        token: str = "token-1",
    ) -> None:
        self.plan = plan
        self.backend = backend
        self.user_id = user_id
        self.account_id = account_id
        self.token = token

    def uses_codex_backend(self) -> bool:
        return self.backend

    def account_plan_type(self) -> str | None:
        return self.plan

    def get_chatgpt_user_id(self) -> str | None:
        return self.user_id

    def get_account_id(self) -> str | None:
        return self.account_id

    def get_token(self) -> str:
        return self.token


class FakeAuthManager:
    def __init__(self, auth: FakeAuth | None, recovery: Any = None) -> None:
        self._auth = auth
        self._recovery = recovery

    async def auth(self) -> FakeAuth | None:
        return self._auth

    def unauthorized_recovery(self) -> Any:
        return self._recovery


class SequenceFetcher:
    def __init__(self, *responses: str | None | FetchAttemptError) -> None:
        self.responses = list(responses)
        self.request_count = 0

    async def fetch_requirements(self, _auth: Any) -> str | None:
        self.request_count += 1
        response = self.responses.pop(0) if self.responses else None
        if isinstance(response, FetchAttemptError):
            raise response
        return response


class TokenFetcher:
    def __init__(self, expected_token: str, contents: str) -> None:
        self.expected_token = expected_token
        self.contents = contents
        self.request_count = 0

    async def fetch_requirements(self, auth: FakeAuth) -> str | None:
        self.request_count += 1
        if auth.get_token() == self.expected_token:
            return self.contents
        raise FetchAttemptError.unauthorized(401, "GET /config/requirements failed: 401")


class ReloadRecovery:
    def __init__(self, manager: FakeAuthManager, refreshed_auth: FakeAuth) -> None:
        self.manager = manager
        self.refreshed_auth = refreshed_auth
        self.used = False

    def has_next(self) -> bool:
        return not self.used

    async def next(self) -> None:
        self.used = True
        self.manager._auth = self.refreshed_auth


def test_cloud_requirements_eligible_auth_matches_business_enterprise_filter() -> None:
    # Rust source: cloud_requirements_eligible_auth.
    assert not cloud_requirements_eligible_auth(FakeAuth(backend=False))
    assert not cloud_requirements_eligible_auth(FakeAuth("pro"))
    assert not cloud_requirements_eligible_auth(FakeAuth("team"))
    assert not cloud_requirements_eligible_auth(FakeAuth("self_serve_business_usage_based"))
    assert cloud_requirements_eligible_auth(FakeAuth("business"))
    assert cloud_requirements_eligible_auth(FakeAuth("enterprise_cbp_usage_based"))
    assert cloud_requirements_eligible_auth(FakeAuth("enterprise"))


def test_parse_cloud_requirements_handles_empty_invalid_and_valid_toml(tmp_path: Path) -> None:
    # Rust source: parse_cloud_requirements and format_cloud_requirements_parse_failed_message.
    assert parse_cloud_requirements("", tmp_path) is None
    assert parse_cloud_requirements("   # comment only\n", tmp_path) is None
    assert parse_cloud_requirements('guardian_policy_config = "  "\n', tmp_path) is None

    parsed = parse_cloud_requirements('allowed_approval_policies = ["never"]\n', tmp_path)
    assert parsed is not None
    assert parsed.allowed_approval_policies == (AskForApproval.NEVER,)

    with pytest.raises(Exception) as excinfo:
        parse_cloud_requirements('allowed_approval_policies = ["bogus"]\n', tmp_path)
    message = format_cloud_requirements_parse_failed_message("unused", excinfo.value)
    assert CLOUD_REQUIREMENTS_PARSE_FAILED_MESSAGE in message
    assert "bogus" in message


def test_parse_cloud_requirements_resolves_relative_deny_read_from_codex_home(tmp_path: Path) -> None:
    # Rust source: fetch_cloud_requirements_resolves_relative_deny_read_globs_from_codex_home.
    parsed = parse_cloud_requirements(
        """
        [permissions.filesystem]
        deny_read = ["secrets/*.txt"]
        """,
        tmp_path,
    )
    assert parsed is not None
    pattern = parsed.permissions.filesystem.deny_read[0].as_str()  # type: ignore[union-attr]
    assert pattern == str(tmp_path / "secrets" / "*.txt")


def test_fetch_cloud_requirements_skips_non_chatgpt_or_non_workspace_auth(tmp_path: Path) -> None:
    # Rust sources: fetch_cloud_requirements_skips_non_chatgpt_auth and non-business/team-like tests.
    fetcher = SequenceFetcher('allowed_approval_policies = ["never"]\n')
    service = CloudRequirementsService(FakeAuthManager(FakeAuth("business", backend=False)), fetcher, tmp_path)
    assert asyncio.run(service.fetch()) is None
    assert fetcher.request_count == 0

    fetcher = SequenceFetcher('allowed_approval_policies = ["never"]\n')
    service = CloudRequirementsService(FakeAuthManager(FakeAuth("team")), fetcher, tmp_path)
    assert asyncio.run(service.fetch()) is None
    assert fetcher.request_count == 0


def test_fetch_cloud_requirements_retries_until_success(tmp_path: Path) -> None:
    # Rust source: fetch_cloud_requirements_retries_until_success.
    fetcher = SequenceFetcher(
        FetchAttemptError.retryable(RetryableFailureKind.REQUEST, 500),
        FetchAttemptError.retryable(RetryableFailureKind.REQUEST, 502),
        'allowed_approval_policies = ["never"]\n',
    )
    service = CloudRequirementsService(FakeAuthManager(FakeAuth("business")), fetcher, tmp_path, sleep=_no_sleep)
    result = asyncio.run(service.fetch())
    assert result is not None
    assert result.allowed_approval_policies == (AskForApproval.NEVER,)
    assert fetcher.request_count == 3


def test_fetch_cloud_requirements_stops_after_max_retries(tmp_path: Path) -> None:
    # Rust source: fetch_cloud_requirements_stops_after_max_retries.
    fetcher = SequenceFetcher(
        *[FetchAttemptError.retryable(RetryableFailureKind.REQUEST, 503) for _ in range(CLOUD_REQUIREMENTS_MAX_ATTEMPTS)]
    )
    service = CloudRequirementsService(FakeAuthManager(FakeAuth("business")), fetcher, tmp_path, sleep=_no_sleep)
    with pytest.raises(CloudRequirementsLoadError) as excinfo:
        asyncio.run(service.fetch())
    assert excinfo.value.code() == CloudRequirementsLoadErrorCode.REQUEST_FAILED
    assert excinfo.value.status_code() == 503
    assert str(excinfo.value) == CLOUD_REQUIREMENTS_LOAD_FAILED_MESSAGE


def test_fetch_cloud_requirements_recovers_after_unauthorized_reload(tmp_path: Path) -> None:
    # Rust source: fetch_cloud_requirements_recovers_after_unauthorized_reload.
    initial_auth = FakeAuth("business", token="old-token")
    refreshed_auth = FakeAuth("business", token="new-token")
    manager = FakeAuthManager(initial_auth)
    manager._recovery = ReloadRecovery(manager, refreshed_auth)
    fetcher = TokenFetcher("new-token", 'allowed_approval_policies = ["never"]\n')

    service = CloudRequirementsService(manager, fetcher, tmp_path)
    result = asyncio.run(service.fetch())
    assert result is not None
    assert result.allowed_approval_policies == (AskForApproval.NEVER,)
    assert fetcher.request_count == 2


def test_fetch_cloud_requirements_unauthorized_without_recovery_uses_generic_message(tmp_path: Path) -> None:
    # Rust source: fetch_cloud_requirements_unauthorized_without_recovery_uses_generic_message.
    fetcher = SequenceFetcher(FetchAttemptError.unauthorized(401, "backend said no"))
    service = CloudRequirementsService(FakeAuthManager(FakeAuth("business")), fetcher, tmp_path)
    with pytest.raises(CloudRequirementsLoadError) as excinfo:
        asyncio.run(service.fetch())
    assert excinfo.value.code() == CloudRequirementsLoadErrorCode.AUTH
    assert excinfo.value.status_code() == 401
    assert str(excinfo.value) == CLOUD_REQUIREMENTS_AUTH_RECOVERY_FAILED_MESSAGE


def test_fetch_cloud_requirements_uses_and_writes_signed_cache(tmp_path: Path) -> None:
    # Rust sources: uses_cache_when_valid, writes_cache_when_identity_is_incomplete, writes_signed_cache.
    now = datetime(2026, 1, 1, tzinfo=UTC)
    service = CloudRequirementsService(
        FakeAuthManager(FakeAuth("business")),
        SequenceFetcher('allowed_approval_policies = ["never"]\n'),
        tmp_path,
        now=lambda: now,
    )
    result = asyncio.run(service.fetch())
    assert result is not None
    cache_file = tmp_path / CLOUD_REQUIREMENTS_CACHE_FILENAME
    assert cache_file.exists()
    raw = cache_file.read_text(encoding="utf-8")
    assert "signature" in raw

    cached_service = CloudRequirementsService(
        FakeAuthManager(FakeAuth("business")),
        SequenceFetcher(FetchAttemptError.retryable()),
        tmp_path,
        now=lambda: now + timedelta(minutes=1),
    )
    cached = asyncio.run(cached_service.fetch())
    assert cached is not None
    assert cached.allowed_approval_policies == (AskForApproval.NEVER,)


def test_fetch_cloud_requirements_ignores_tampered_or_expired_cache(tmp_path: Path) -> None:
    # Rust sources: ignores_tampered_cache and ignores_expired_cache.
    now = datetime(2026, 1, 1, tzinfo=UTC)
    service = CloudRequirementsService(
        FakeAuthManager(FakeAuth("business")),
        SequenceFetcher('allowed_approval_policies = ["never"]\n'),
        tmp_path,
        now=lambda: now,
    )
    asyncio.run(service.save_cache("user-12345", "account-12345", 'allowed_approval_policies = ["on-request"]\n'))
    cache_path = tmp_path / CLOUD_REQUIREMENTS_CACHE_FILENAME
    cache_path.write_text(cache_path.read_text(encoding="utf-8").replace("on-request", "never"), encoding="utf-8")

    fallback = SequenceFetcher('allowed_approval_policies = ["never"]\n')
    tampered_service = CloudRequirementsService(FakeAuthManager(FakeAuth("business")), fallback, tmp_path, now=lambda: now)
    result = asyncio.run(tampered_service.fetch())
    assert result is not None
    assert result.allowed_approval_policies == (AskForApproval.NEVER,)
    assert fallback.request_count == 1

    asyncio.run(service.save_cache("user-12345", "account-12345", 'allowed_approval_policies = ["on-request"]\n'))
    expired_service = CloudRequirementsService(
        FakeAuthManager(FakeAuth("business")),
        SequenceFetcher('allowed_approval_policies = ["never"]\n'),
        tmp_path,
        now=lambda: now + timedelta(hours=1),
    )
    assert asyncio.run(expired_service.fetch()).allowed_approval_policies == (AskForApproval.NEVER,)  # type: ignore[union-attr]


def test_cache_signature_helpers_round_trip() -> None:
    # Rust source: sign_cache_payload and verify_cache_signature.
    payload = CloudRequirementsCacheSignedPayload(
        cached_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=datetime(2026, 1, 1, 0, 30, tzinfo=UTC),
        chatgpt_user_id="user-12345",
        account_id="account-12345",
        contents=None,
    )
    payload_bytes = cache_payload_bytes(payload)
    signature = sign_cache_payload(payload_bytes)
    assert verify_cache_signature(payload_bytes, signature)
    assert not verify_cache_signature(payload_bytes + b"!", signature)


def test_cloud_requirements_loader_returns_shared_config_loader(tmp_path: Path) -> None:
    # Rust source: cloud_requirements_loader returns codex_config::CloudRequirementsLoader.
    loader = cloud_requirements_loader(
        FakeAuthManager(FakeAuth("business")),
        "https://chatgpt.example/backend-api",
        tmp_path,
        fetcher=SequenceFetcher('allowed_approval_policies = ["never"]\n'),
    )
    result = asyncio.run(loader.get())
    assert result is not None
    assert result.allowed_approval_policies == (AskForApproval.NEVER,)


async def _no_sleep(_seconds: float) -> None:
    return None
