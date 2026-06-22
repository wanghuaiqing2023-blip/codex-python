from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from pycodex.app_server.request_processors_account_processor import (
    AccountRequestProcessor,
    AccountRequestProcessorError,
    AccountState,
    ActiveLogin,
    MissingChatgptAccountDetails,
    RateLimitCooldown,
)
from pycodex.app_server.error_code import INTERNAL_ERROR_CODE, INVALID_REQUEST_ERROR_CODE
from pycodex.app_server_protocol import (
    AddCreditsNudgeCreditType,
    AddCreditsNudgeEmailStatus,
    AuthMode,
    CancelLoginAccountParams,
    CancelLoginAccountStatus,
    GetAccountParams,
    LoginAccountParams,
    RateLimitSnapshot,
    SendAddCreditsNudgeEmailParams,
)
from pycodex.protocol.account import PlanType


def test_current_account_updated_notification_uses_cached_auth() -> None:
    processor = make_processor(auth=FakeAuth(AuthMode.CHATGPT, PlanType.PRO))

    notification = processor.current_account_updated_notification()

    assert notification.auth_mode == AuthMode.CHATGPT
    assert notification.plan_type == PlanType.PRO


def test_login_api_key_common_rejects_external_auth_and_forced_chatgpt() -> None:
    processor = make_processor(auth_manager=FakeAuthManager(external=True))

    error = catch_error(lambda: asyncio.run(processor.login_api_key_common("sk-test")))

    assert error.code == INVALID_REQUEST_ERROR_CODE
    assert "External auth is active" in error.message

    processor = make_processor(config=Config(forced_login_method="chatgpt"))
    error = catch_error(lambda: asyncio.run(processor.login_api_key_common("sk-test")))

    assert error.code == INVALID_REQUEST_ERROR_CODE
    assert error.message == "API key login is disabled. Use ChatGPT login instead."


def test_login_api_key_common_cancels_active_login_and_reloads() -> None:
    cancelled: list[str] = []
    saved: list[str] = []
    processor = make_processor(login_with_api_key=saved.append)
    processor.active_login = ActiveLogin("browser", str(uuid.uuid4()), lambda: cancelled.append("old"))

    asyncio.run(processor.login_api_key_common("sk-test"))

    assert cancelled == ["old"]
    assert saved == ["sk-test"]
    assert processor.auth_manager.reloads == 1
    assert processor.active_login is None


def test_cancel_login_response_validates_uuid_and_matches_active_login() -> None:
    login_id = str(uuid.uuid4())
    cancelled: list[str] = []
    processor = make_processor()
    processor.active_login = ActiveLogin("deviceCode", login_id, lambda: cancelled.append("cancel"))

    response = asyncio.run(processor.cancel_login_response(CancelLoginAccountParams(login_id)))

    assert response.status == CancelLoginAccountStatus.CANCELED
    assert cancelled == ["cancel"]
    assert processor.active_login is None
    assert asyncio.run(processor.cancel_login_response(CancelLoginAccountParams(str(uuid.uuid4())))).status == CancelLoginAccountStatus.NOT_FOUND

    error = catch_error(lambda: asyncio.run(processor.cancel_login_response(CancelLoginAccountParams("not-a-uuid"))))
    assert error.code == INVALID_REQUEST_ERROR_CODE
    assert error.message == "invalid login id: not-a-uuid"


def test_chatgpt_auth_tokens_respects_forced_login_and_workspace() -> None:
    processor = make_processor(config=Config(forced_login_method="api"))
    error = catch_error(lambda: asyncio.run(processor.login_chatgpt_auth_tokens_response("token", "ws-1", None)))
    assert error.message == "External ChatGPT auth is disabled. Use API key login instead."

    processor = make_processor(config=Config(forced_chatgpt_workspace_id="ws-allowed"))
    error = catch_error(lambda: asyncio.run(processor.login_chatgpt_auth_tokens_response("token", "ws-other", None)))
    assert error.code == INVALID_REQUEST_ERROR_CODE
    assert "External auth must use one of workspace" in error.message


def test_chatgpt_auth_tokens_success_clears_active_login_and_syncs_config() -> None:
    calls: list[tuple[str, str, str | None]] = []
    processor = make_processor(login_with_chatgpt_auth_tokens=lambda *args: calls.append(args))
    processor.active_login = ActiveLogin("browser", str(uuid.uuid4()))

    response = asyncio.run(processor.login_chatgpt_auth_tokens_response("token", "ws-1", "pro"))

    assert response.type == "chatgptAuthTokens"
    assert calls == [("token", "ws-1", "pro")]
    assert processor.auth_manager.reloads == 1
    assert processor.config_manager.replaced_cloud_loader == 1
    assert processor.config_manager.synced_residency == 1
    assert processor.active_login is None


def test_send_login_success_notifications_emits_login_completed_then_account_updated() -> None:
    processor = make_processor(auth=FakeAuth(AuthMode.API_KEY, None))

    asyncio.run(processor.send_login_success_notifications(None))

    assert [notification.type for notification in processor.outgoing.notifications] == [
        "AccountLoginCompleted",
        "AccountUpdated",
    ]
    assert processor.outgoing.notifications[0].payload.success is True
    assert processor.outgoing.notifications[1].payload.auth_mode == AuthMode.API_KEY
    assert processor.config_manager.refreshes == 1


def test_logout_account_sends_result_before_account_updated_when_auth_mode_remains() -> None:
    processor = make_processor(auth=FakeAuth(AuthMode.CHATGPT, PlanType.PLUS))

    asyncio.run(processor.logout_account("req-1"))

    assert processor.outgoing.results[0][0] == "req-1"
    assert processor.outgoing.results[0][1].to_mapping() == {}
    assert processor.outgoing.notifications[-1].type == "AccountUpdated"
    assert processor.outgoing.notifications[-1].payload.auth_mode == AuthMode.CHATGPT


def test_get_account_response_maps_missing_chatgpt_details_to_invalid_request() -> None:
    processor = make_processor(account_state_provider=lambda: (_ for _ in ()).throw(MissingChatgptAccountDetails()))

    error = catch_error(lambda: asyncio.run(processor.get_account_response(GetAccountParams())))

    assert error.code == INVALID_REQUEST_ERROR_CODE
    assert error.message == "email and plan type are required for chatgpt authentication"


def test_get_account_response_projects_account_state() -> None:
    processor = make_processor(
        account_state_provider=lambda: AccountState({"type": "chatgpt", "email": "a@example.com", "plan_type": "pro"}, True)
    )

    response = asyncio.run(processor.get_account_response({"refreshToken": True}))

    assert response.requires_openai_auth is True
    assert response.account.email == "a@example.com"
    assert processor.auth_manager.refreshes == 1


def test_rate_limits_selects_codex_primary_and_builds_by_id_map() -> None:
    processor = make_processor(
        auth=FakeAuth(AuthMode.CHATGPT, PlanType.PRO, uses_backend=True),
        rate_limits_fetcher=lambda: [
            {"limit_id": "other", "primary": {"used_percent": 1}},
            {"limit_id": "codex", "primary": {"used_percent": 2}},
        ],
    )

    response = asyncio.run(processor.get_account_rate_limits_response())

    assert response.rate_limits.limit_id == "codex"
    assert set(response.rate_limits_by_limit_id) == {"other", "codex"}


def test_rate_limits_require_backend_auth_and_non_empty_snapshots() -> None:
    processor = make_processor(auth=None)
    assert catch_error(lambda: asyncio.run(processor.get_account_rate_limits_response())).message == "codex account authentication required to read rate limits"

    processor = make_processor(auth=FakeAuth(AuthMode.API_KEY, None, uses_backend=False))
    assert catch_error(lambda: asyncio.run(processor.get_account_rate_limits_response())).message == "chatgpt authentication required to read rate limits"

    processor = make_processor(auth=FakeAuth(AuthMode.CHATGPT, PlanType.PRO, uses_backend=True), rate_limits_fetcher=lambda: [])
    error = catch_error(lambda: asyncio.run(processor.get_account_rate_limits_response()))
    assert error.code == INTERNAL_ERROR_CODE
    assert error.message == "failed to fetch codex rate limits: no snapshots returned"


def test_add_credits_nudge_maps_credit_type_and_cooldown() -> None:
    sent: list[AddCreditsNudgeCreditType] = []
    processor = make_processor(
        auth=FakeAuth(AuthMode.CHATGPT, PlanType.PRO, uses_backend=True),
        add_credits_nudge_sender=lambda credit_type: sent.append(credit_type) or AddCreditsNudgeEmailStatus.SENT,
    )

    response = asyncio.run(
        processor.send_add_credits_nudge_email_response(
            SendAddCreditsNudgeEmailParams(AddCreditsNudgeCreditType.USAGE_LIMIT)
        )
    )

    assert sent == [AddCreditsNudgeCreditType.USAGE_LIMIT]
    assert response.status == AddCreditsNudgeEmailStatus.SENT

    processor = make_processor(
        auth=FakeAuth(AuthMode.CHATGPT, PlanType.PRO, uses_backend=True),
        add_credits_nudge_sender=lambda _: (_ for _ in ()).throw(RateLimitCooldown()),
    )
    response = asyncio.run(processor.send_add_credits_nudge_email_response({"creditType": "credits"}))
    assert response.status == AddCreditsNudgeEmailStatus.COOLDOWN_ACTIVE


def catch_error(fn):
    try:
        fn()
    except AccountRequestProcessorError as exc:
        return exc.error
    raise AssertionError("expected AccountRequestProcessorError")


def make_processor(
    *,
    auth=None,
    auth_manager=None,
    config=None,
    login_with_api_key=None,
    login_with_chatgpt_auth_tokens=None,
    account_state_provider=None,
    rate_limits_fetcher=None,
    add_credits_nudge_sender=None,
):
    auth_manager = auth_manager or FakeAuthManager(auth)
    return AccountRequestProcessor(
        auth_manager,
        FakeThreadManager(),
        FakeOutgoing(),
        config or Config(),
        FakeConfigManager(),
        login_with_api_key=login_with_api_key,
        login_with_chatgpt_auth_tokens=login_with_chatgpt_auth_tokens,
        account_state_provider=account_state_provider,
        rate_limits_fetcher=rate_limits_fetcher,
        add_credits_nudge_sender=add_credits_nudge_sender,
    )


class Config:
    def __init__(self, *, forced_login_method=None, forced_chatgpt_workspace_id=None):
        self.forced_login_method = forced_login_method
        self.forced_chatgpt_workspace_id = forced_chatgpt_workspace_id
        self.chatgpt_base_url = "https://chatgpt.example"
        self.model_provider = SimpleNamespace(requires_openai_auth=True)


class FakeAuth:
    def __init__(self, mode, plan_type, *, uses_backend=True, token="token", kind="chatgpt"):
        self.mode = mode
        self.plan_type = plan_type
        self._uses_backend = uses_backend
        self.token = token
        self.kind = kind

    def api_auth_mode(self):
        return self.mode

    def account_plan_type(self):
        return self.plan_type

    def uses_codex_backend(self):
        return self._uses_backend

    def get_token(self):
        return self.token


class FakeAuthManager:
    def __init__(self, auth=None, *, external=False):
        self._auth = auth
        self.external = external
        self.reloads = 0
        self.refreshes = 0
        self.logged_out = 0

    def is_external_chatgpt_auth_active(self):
        return self.external

    def auth_cached(self):
        return self._auth

    async def auth(self):
        return self._auth

    async def reload(self):
        self.reloads += 1

    async def refresh_token(self):
        self.refreshes += 1

    async def logout_with_revoke(self):
        self.logged_out += 1

    def refresh_failure_for_auth(self, _auth):
        return None

    def clear_external_auth(self):
        self.external = False


class FakeThreadManager:
    pass


class FakeOutgoing:
    def __init__(self):
        self.results = []
        self.notifications = []

    async def send_result(self, request_id, result):
        self.results.append((request_id, result))

    async def send_server_notification(self, notification):
        self.notifications.append(notification)


class FakeConfigManager:
    def __init__(self):
        self.refreshes = 0
        self.replaced_cloud_loader = 0
        self.synced_residency = 0

    async def maybe_refresh_remote_installed_plugins_cache_for_current_config(self, _thread_manager, _auth):
        self.refreshes += 1

    async def replace_cloud_requirements_loader(self, _auth_manager, _chatgpt_base_url):
        self.replaced_cloud_loader += 1

    async def sync_default_client_residency_requirement(self):
        self.synced_residency += 1
