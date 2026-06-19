"""Account request processor projection.

Ported from ``codex-app-server/src/request_processors/account_processor.rs``.
The Rust module coordinates account/login request state, auth-manager calls,
and app-server account notification payloads. Python keeps the module-owned
control flow dependency-light by injecting real auth, backend, config, and
outgoing implementations at the boundary.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server_protocol import (
    Account,
    AccountLoginCompletedNotification,
    AccountUpdatedNotification,
    AddCreditsNudgeCreditType,
    AddCreditsNudgeEmailStatus,
    AuthMode,
    CancelLoginAccountParams,
    CancelLoginAccountResponse,
    CancelLoginAccountStatus,
    GetAccountParams,
    GetAccountRateLimitsResponse,
    GetAccountResponse,
    JSONRPCErrorError,
    LoginAccountParams,
    LoginAccountResponse,
    LogoutAccountResponse,
    RateLimitSnapshot,
    SendAddCreditsNudgeEmailParams,
    SendAddCreditsNudgeEmailResponse,
    ServerNotification,
)
from pycodex.app_server_protocol import GetAuthStatusParams, GetAuthStatusResponse

JsonValue = Any

LOGIN_CHATGPT_TIMEOUT_SECONDS = 10 * 60


class AccountRequestProcessorError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True)
class ActiveLogin:
    kind: str
    login_id: str
    cancel_callback: Callable[[], Any] | None = None

    def cancel(self) -> None:
        if self.cancel_callback is not None:
            self.cancel_callback()


@dataclass(frozen=True)
class AccountState:
    account: Account | Mapping[str, JsonValue] | None
    requires_openai_auth: bool


class MissingChatgptAccountDetails(Exception):
    pass


class AccountRequestProcessor:
    def __init__(
        self,
        auth_manager: Any,
        thread_manager: Any,
        outgoing: Any,
        config: Any,
        config_manager: Any,
        *,
        login_with_api_key: Callable[[str], Any] | None = None,
        login_with_chatgpt_auth_tokens: Callable[[str, str, str | None], Any] | None = None,
        account_state_provider: Callable[[], Any] | None = None,
        rate_limits_fetcher: Callable[[], Any] | None = None,
        add_credits_nudge_sender: Callable[[AddCreditsNudgeCreditType], Any] | None = None,
    ) -> None:
        self.auth_manager = auth_manager
        self.thread_manager = thread_manager
        self.outgoing = outgoing
        self.config = config
        self.config_manager = config_manager
        self.active_login: ActiveLogin | None = None
        self._login_with_api_key = login_with_api_key
        self._login_with_chatgpt_auth_tokens = login_with_chatgpt_auth_tokens
        self._account_state_provider = account_state_provider
        self._rate_limits_fetcher = rate_limits_fetcher
        self._add_credits_nudge_sender = add_credits_nudge_sender

    @classmethod
    def new(
        cls,
        auth_manager: Any,
        thread_manager: Any,
        outgoing: Any,
        config: Any,
        config_manager: Any,
    ) -> "AccountRequestProcessor":
        return cls(auth_manager, thread_manager, outgoing, config, config_manager)

    async def login_account(self, request_id: Any, params: LoginAccountParams | Mapping[str, JsonValue]) -> None:
        parsed = _login_params(params)
        if parsed.type == "apiKey":
            result = await self.login_api_key_response(parsed.api_key or "")
        elif parsed.type == "chatgptAuthTokens":
            result = await self.login_chatgpt_auth_tokens_response(
                parsed.access_token or "",
                parsed.chatgpt_account_id or "",
                parsed.chatgpt_plan_type,
            )
        elif parsed.type == "chatgpt":
            result = self.login_chatgpt_response_placeholder(parsed.codex_streamlined_login)
        elif parsed.type == "chatgptDeviceCode":
            result = self.login_chatgpt_device_code_response_placeholder()
        else:
            raise AccountRequestProcessorError(invalid_request(f"unsupported login type: {parsed.type}"))

        logged_in = isinstance(result, LoginAccountResponse) and result.type in {"apiKey", "chatgptAuthTokens"}
        await self._send_result(request_id, result)
        if logged_in:
            await self.send_login_success_notifications(None)

    async def logout_account(self, request_id: Any) -> None:
        auth_mode = await self.logout_common()
        await self._send_result(request_id, LogoutAccountResponse())
        if auth_mode is not None:
            await self._send_server_notification(
                ServerNotification("AccountUpdated", AccountUpdatedNotification(auth_mode=auth_mode, plan_type=None))
            )

    async def cancel_login_account(
        self,
        params: CancelLoginAccountParams | Mapping[str, JsonValue],
    ) -> CancelLoginAccountResponse:
        return await self.cancel_login_response(params)

    async def get_account(self, params: GetAccountParams | Mapping[str, JsonValue] | None = None) -> GetAccountResponse:
        return await self.get_account_response(params)

    async def get_auth_status(self, params: GetAuthStatusParams | Mapping[str, JsonValue] | None = None) -> GetAuthStatusResponse:
        return await self.get_auth_status_response(params)

    async def get_account_rate_limits(self) -> GetAccountRateLimitsResponse:
        return await self.get_account_rate_limits_response()

    async def send_add_credits_nudge_email(
        self,
        params: SendAddCreditsNudgeEmailParams | Mapping[str, JsonValue],
    ) -> SendAddCreditsNudgeEmailResponse:
        return await self.send_add_credits_nudge_email_response(params)

    async def cancel_active_login(self) -> None:
        active = self.active_login
        self.active_login = None
        if active is not None:
            active.cancel()

    def clear_external_auth(self) -> None:
        self.auth_manager.clear_external_auth()

    def current_account_updated_notification(self) -> AccountUpdatedNotification:
        auth = self.auth_manager.auth_cached()
        return AccountUpdatedNotification(
            auth_mode=None if auth is None else _auth_mode(auth),
            plan_type=None if auth is None else _plan_type(auth),
        )

    async def login_api_key_response(self, api_key: str) -> LoginAccountResponse:
        await self.login_api_key_common(api_key)
        return LoginAccountResponse.api_key()

    async def login_api_key_common(self, api_key: str) -> None:
        if self.auth_manager.is_external_chatgpt_auth_active():
            raise AccountRequestProcessorError(self.external_auth_active_error())
        if _forced_login_method(self.config) == "chatgpt":
            raise AccountRequestProcessorError(invalid_request("API key login is disabled. Use ChatGPT login instead."))
        await self.cancel_active_login()
        try:
            if self._login_with_api_key is not None:
                await _maybe_await(self._login_with_api_key(api_key))
            else:
                await _maybe_await(self.auth_manager.login_with_api_key(api_key))
        except AccountRequestProcessorError:
            raise
        except Exception as exc:
            raise AccountRequestProcessorError(internal_error(f"failed to save api key: {exc}")) from exc
        await _maybe_await(self.auth_manager.reload())

    def login_chatgpt_response_placeholder(self, codex_streamlined_login: bool) -> LoginAccountResponse:
        self._validate_chatgpt_login_allowed()
        login_id = str(uuid.uuid4())
        self._replace_active_login(ActiveLogin("browser", login_id))
        return LoginAccountResponse.chatgpt(login_id, f"pending://chatgpt-login/{login_id}")

    def login_chatgpt_device_code_response_placeholder(self) -> LoginAccountResponse:
        self._validate_chatgpt_login_allowed()
        login_id = str(uuid.uuid4())
        self._replace_active_login(ActiveLogin("deviceCode", login_id))
        return LoginAccountResponse.chatgpt_device_code(login_id, "pending://device-code", "PENDING")

    async def login_chatgpt_auth_tokens_response(
        self,
        access_token: str,
        chatgpt_account_id: str,
        chatgpt_plan_type: str | None,
    ) -> LoginAccountResponse:
        if _forced_login_method(self.config) == "api":
            raise AccountRequestProcessorError(
                invalid_request("External ChatGPT auth is disabled. Use API key login instead.")
            )
        await self.cancel_active_login()
        expected_workspaces = getattr(self.config, "forced_chatgpt_workspace_id", None)
        if expected_workspaces is not None and chatgpt_account_id not in str(expected_workspaces):
            raise AccountRequestProcessorError(
                invalid_request(
                    f"External auth must use one of workspace(s) {expected_workspaces!r}, but received {chatgpt_account_id!r}."
                )
            )
        try:
            if self._login_with_chatgpt_auth_tokens is not None:
                await _maybe_await(
                    self._login_with_chatgpt_auth_tokens(access_token, chatgpt_account_id, chatgpt_plan_type)
                )
            else:
                await _maybe_await(
                    self.auth_manager.login_with_chatgpt_auth_tokens(
                        access_token,
                        chatgpt_account_id,
                        chatgpt_plan_type,
                    )
                )
        except Exception as exc:
            raise AccountRequestProcessorError(internal_error(f"failed to set external auth: {exc}")) from exc
        await _maybe_await(self.auth_manager.reload())
        await self._replace_cloud_requirements_loader()
        await self._sync_default_client_residency_requirement()
        return LoginAccountResponse.chatgpt_auth_tokens()

    async def cancel_login_response(
        self,
        params: CancelLoginAccountParams | Mapping[str, JsonValue],
    ) -> CancelLoginAccountResponse:
        parsed = _cancel_params(params)
        try:
            uuid.UUID(parsed.login_id)
        except ValueError as exc:
            raise AccountRequestProcessorError(invalid_request(f"invalid login id: {parsed.login_id}")) from exc
        if self.active_login is not None and self.active_login.login_id == parsed.login_id:
            await self.cancel_active_login()
            return CancelLoginAccountResponse(CancelLoginAccountStatus.CANCELED)
        return CancelLoginAccountResponse(CancelLoginAccountStatus.NOT_FOUND)

    async def send_login_success_notifications(self, login_id: str | None) -> None:
        await self.maybe_refresh_remote_installed_plugins_cache_for_current_config(self.auth_manager.auth_cached())
        await self._send_server_notification(
            ServerNotification(
                "AccountLoginCompleted",
                AccountLoginCompletedNotification(login_id=login_id, success=True, error=None),
            )
        )
        await self._send_server_notification(ServerNotification("AccountUpdated", self.current_account_updated_notification()))

    async def send_chatgpt_login_completion_notifications(
        self,
        login_id: str,
        success: bool,
        error_msg: str | None,
    ) -> None:
        await self._send_server_notification(
            ServerNotification(
                "AccountLoginCompleted",
                AccountLoginCompletedNotification(login_id=login_id, success=success, error=error_msg),
            )
        )
        if success:
            await _maybe_await(self.auth_manager.reload())
            await self._replace_cloud_requirements_loader()
            await self._sync_default_client_residency_requirement()
            await self.maybe_refresh_remote_installed_plugins_cache_for_current_config(self.auth_manager.auth_cached())
            await self._send_server_notification(ServerNotification("AccountUpdated", self.current_account_updated_notification()))

    async def logout_common(self) -> AuthMode | str | None:
        await self.cancel_active_login()
        try:
            await _maybe_await(self.auth_manager.logout_with_revoke())
        except Exception as exc:
            raise AccountRequestProcessorError(internal_error(f"logout failed: {exc}")) from exc
        await self.maybe_refresh_remote_installed_plugins_cache_for_current_config(self.auth_manager.auth_cached())
        auth = self.auth_manager.auth_cached()
        return None if auth is None else _auth_mode(auth)

    async def refresh_token_if_requested(self, do_refresh: bool) -> str:
        if self.auth_manager.is_external_chatgpt_auth_active():
            return "not_attempted_or_succeeded"
        if do_refresh:
            try:
                await _maybe_await(self.auth_manager.refresh_token())
            except Exception as exc:
                failed_reason = getattr(exc, "failed_reason", lambda: None)()
                if failed_reason is None:
                    return "failed_transiently"
                return "failed_permanently"
        return "not_attempted_or_succeeded"

    async def get_auth_status_response(
        self,
        params: GetAuthStatusParams | Mapping[str, JsonValue] | None = None,
    ) -> GetAuthStatusResponse:
        include_token = _field(params, "include_token", "includeToken", default=False) or False
        do_refresh = _field(params, "refresh_token", "refreshToken", default=False) or False
        await self.refresh_token_if_requested(bool(do_refresh))
        requires_openai_auth = bool(getattr(getattr(self.config, "model_provider", None), "requires_openai_auth", True))
        if not requires_openai_auth:
            return GetAuthStatusResponse(auth_method=None, auth_token=None, requires_openai_auth=False)
        auth = self.auth_manager.auth_cached() if do_refresh else await _maybe_await(self.auth_manager.auth())
        if auth is None:
            return GetAuthStatusResponse(auth_method=None, auth_token=None, requires_openai_auth=True)
        auth_mode = _auth_mode(auth)
        permanent_refresh_failure = bool(_call_optional(self.auth_manager, "refresh_failure_for_auth", auth))
        token = None
        if include_token and not permanent_refresh_failure and not _auth_kind_is_agent_identity(auth):
            try:
                token = await _maybe_await(auth.get_token())
                if not token:
                    return GetAuthStatusResponse(auth_method=None, auth_token=None, requires_openai_auth=True)
            except Exception:
                return GetAuthStatusResponse(auth_method=None, auth_token=None, requires_openai_auth=True)
        return GetAuthStatusResponse(auth_method=auth_mode, auth_token=token if include_token else None, requires_openai_auth=True)

    async def get_account_response(
        self,
        params: GetAccountParams | Mapping[str, JsonValue] | None = None,
    ) -> GetAccountResponse:
        parsed = _get_account_params(params)
        await self.refresh_token_if_requested(parsed.refresh_token)
        try:
            state = await _maybe_await(self._account_state())
        except MissingChatgptAccountDetails as exc:
            raise AccountRequestProcessorError(invalid_request("email and plan type are required for chatgpt authentication")) from exc
        account_state = _account_state(state)
        return GetAccountResponse(account_state.account, account_state.requires_openai_auth)

    async def get_account_rate_limits_response(self) -> GetAccountRateLimitsResponse:
        primary, by_id = await self.fetch_account_rate_limits()
        return GetAccountRateLimitsResponse(primary, by_id)

    async def send_add_credits_nudge_email_response(
        self,
        params: SendAddCreditsNudgeEmailParams | Mapping[str, JsonValue],
    ) -> SendAddCreditsNudgeEmailResponse:
        status = await self.send_add_credits_nudge_email_inner(_nudge_params(params))
        return SendAddCreditsNudgeEmailResponse(status)

    async def send_add_credits_nudge_email_inner(
        self,
        params: SendAddCreditsNudgeEmailParams,
    ) -> AddCreditsNudgeEmailStatus:
        auth = await _maybe_await(self.auth_manager.auth())
        if auth is None:
            raise AccountRequestProcessorError(
                invalid_request("codex account authentication required to notify workspace owner")
            )
        if not bool(_call_optional(auth, "uses_codex_backend")):
            raise AccountRequestProcessorError(
                invalid_request("chatgpt authentication required to notify workspace owner")
            )
        try:
            if self._add_credits_nudge_sender is None:
                sender = getattr(self.auth_manager, "send_add_credits_nudge_email")
                status = await _maybe_await(sender(self.backend_credit_type(params.credit_type)))
            else:
                status = await _maybe_await(self._add_credits_nudge_sender(self.backend_credit_type(params.credit_type)))
        except RateLimitCooldown:
            return AddCreditsNudgeEmailStatus.COOLDOWN_ACTIVE
        except Exception as exc:
            raise AccountRequestProcessorError(internal_error(f"failed to notify workspace owner: {exc}")) from exc
        return AddCreditsNudgeEmailStatus.parse(status) if isinstance(status, str) else status

    @staticmethod
    def backend_credit_type(value: AddCreditsNudgeCreditType | str) -> AddCreditsNudgeCreditType:
        return AddCreditsNudgeCreditType.parse(value)

    async def fetch_account_rate_limits(self) -> tuple[RateLimitSnapshot, dict[str, RateLimitSnapshot]]:
        auth = await _maybe_await(self.auth_manager.auth())
        if auth is None:
            raise AccountRequestProcessorError(invalid_request("codex account authentication required to read rate limits"))
        if not bool(_call_optional(auth, "uses_codex_backend")):
            raise AccountRequestProcessorError(invalid_request("chatgpt authentication required to read rate limits"))
        try:
            snapshots = await _maybe_await(self._fetch_rate_limits())
        except Exception as exc:
            raise AccountRequestProcessorError(internal_error(f"failed to fetch codex rate limits: {exc}")) from exc
        if not snapshots:
            raise AccountRequestProcessorError(internal_error("failed to fetch codex rate limits: no snapshots returned"))
        parsed = [_rate_limit_snapshot(snapshot) for snapshot in snapshots]
        by_id = {snapshot.limit_id or "codex": snapshot for snapshot in parsed}
        primary = next((snapshot for snapshot in parsed if snapshot.limit_id == "codex"), parsed[0])
        return primary, by_id

    async def maybe_refresh_remote_installed_plugins_cache_for_current_config(self, auth: Any) -> None:
        hook = getattr(self.config_manager, "maybe_refresh_remote_installed_plugins_cache_for_current_config", None)
        if callable(hook):
            await _maybe_await(hook(self.thread_manager, auth))

    def external_auth_active_error(self) -> JSONRPCErrorError:
        return invalid_request(
            "External auth is active. Use account/login/start (chatgptAuthTokens) to update it or account/logout to clear it."
        )

    def _validate_chatgpt_login_allowed(self) -> None:
        if self.auth_manager.is_external_chatgpt_auth_active():
            raise AccountRequestProcessorError(self.external_auth_active_error())
        if _forced_login_method(self.config) == "api":
            raise AccountRequestProcessorError(invalid_request("ChatGPT login is disabled. Use API key login instead."))

    def _replace_active_login(self, active: ActiveLogin) -> None:
        if self.active_login is not None:
            self.active_login.cancel()
        self.active_login = active

    async def _account_state(self) -> Any:
        if self._account_state_provider is not None:
            return await _maybe_await(self._account_state_provider())
        return await _maybe_await(self.auth_manager.account_state())

    async def _fetch_rate_limits(self) -> Sequence[Any]:
        if self._rate_limits_fetcher is not None:
            return await _maybe_await(self._rate_limits_fetcher())
        return await _maybe_await(self.auth_manager.get_rate_limits_many())

    async def _replace_cloud_requirements_loader(self) -> None:
        method = getattr(self.config_manager, "replace_cloud_requirements_loader", None)
        if callable(method):
            await _maybe_await(method(self.auth_manager, getattr(self.config, "chatgpt_base_url", None)))

    async def _sync_default_client_residency_requirement(self) -> None:
        method = getattr(self.config_manager, "sync_default_client_residency_requirement", None)
        if callable(method):
            await _maybe_await(method())

    async def _send_result(self, request_id: Any, result: Any) -> None:
        await _maybe_await(self.outgoing.send_result(request_id, result))

    async def _send_server_notification(self, notification: ServerNotification) -> None:
        await _maybe_await(self.outgoing.send_server_notification(notification))


class RateLimitCooldown(Exception):
    pass


def _login_params(value: LoginAccountParams | Mapping[str, JsonValue]) -> LoginAccountParams:
    return value if isinstance(value, LoginAccountParams) else LoginAccountParams.from_mapping(value)


def _cancel_params(value: CancelLoginAccountParams | Mapping[str, JsonValue]) -> CancelLoginAccountParams:
    return value if isinstance(value, CancelLoginAccountParams) else CancelLoginAccountParams.from_mapping(value)


def _get_account_params(value: GetAccountParams | Mapping[str, JsonValue] | None) -> GetAccountParams:
    return value if isinstance(value, GetAccountParams) else GetAccountParams.from_mapping(value)


def _nudge_params(value: SendAddCreditsNudgeEmailParams | Mapping[str, JsonValue]) -> SendAddCreditsNudgeEmailParams:
    return value if isinstance(value, SendAddCreditsNudgeEmailParams) else SendAddCreditsNudgeEmailParams.from_mapping(value)


def _account_state(value: Any) -> AccountState:
    if isinstance(value, AccountState):
        return value
    if isinstance(value, Mapping):
        return AccountState(value.get("account"), bool(_field(value, "requires_openai_auth", "requiresOpenaiAuth")))
    return AccountState(getattr(value, "account"), bool(getattr(value, "requires_openai_auth")))


def _rate_limit_snapshot(value: Any) -> RateLimitSnapshot:
    if isinstance(value, RateLimitSnapshot):
        return value
    return RateLimitSnapshot.from_mapping(value) if isinstance(value, Mapping) else RateLimitSnapshot(**value.__dict__)


def _auth_mode(auth: Any) -> AuthMode | str:
    method = getattr(auth, "api_auth_mode", None)
    value = method() if callable(method) else getattr(auth, "auth_mode", auth)
    return AuthMode.parse(value) if isinstance(value, str) else value


def _plan_type(auth: Any) -> Any:
    method = getattr(auth, "account_plan_type", None)
    return method() if callable(method) else getattr(auth, "plan_type", None)


def _forced_login_method(config: Any) -> str | None:
    value = getattr(config, "forced_login_method", None)
    raw = getattr(value, "value", value)
    return raw.lower() if isinstance(raw, str) else None


def _auth_kind_is_agent_identity(auth: Any) -> bool:
    return str(getattr(auth, "kind", "")).lower() == "agentidentity"


def _call_optional(obj: Any, name: str, *args: Any) -> Any:
    method = getattr(obj, name, None)
    if callable(method):
        return method(*args)
    return None


def _field(value: Any, *names: str, default: JsonValue = None) -> JsonValue:
    if value is None:
        return default
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return default
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "AccountRequestProcessor",
    "AccountRequestProcessorError",
    "AccountState",
    "ActiveLogin",
    "LOGIN_CHATGPT_TIMEOUT_SECONDS",
    "MissingChatgptAccountDetails",
    "RateLimitCooldown",
]
