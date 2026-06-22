"""Port of Rust ``codex-login::auth::manager``.

Rust source:
- ``codex/codex-rs/login/src/auth/manager.rs``
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from pycodex.login.auth.agent_identity import AgentIdentityAuth
from pycodex.login.auth.external_bearer import ExternalAuthRefreshContext, ExternalAuthTokens
from pycodex.login.auth.revoke import revoke_auth_tokens
from pycodex.login.auth.storage import (
    AuthDotJson,
    AuthStorageBackend,
    agent_identity_auth_record_from_agent_identity_jwt,
    create_auth_storage,
)
from pycodex.login.token_data import TokenData, parse_chatgpt_jwt_claims, parse_jwt_expiration
from pycodex.protocol.auth import RefreshTokenFailedError, RefreshTokenFailedReason


OPENAI_API_KEY_ENV_VAR = "OPENAI_API_KEY"
CODEX_API_KEY_ENV_VAR = "CODEX_API_KEY"
CODEX_ACCESS_TOKEN_ENV_VAR = "CODEX_ACCESS_TOKEN"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
REFRESH_TOKEN_URL = "https://auth.openai.com/oauth/token"
REVOKE_TOKEN_URL = "https://auth.openai.com/oauth/revoke"
REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR = "CODEX_REFRESH_TOKEN_URL_OVERRIDE"
REVOKE_TOKEN_URL_OVERRIDE_ENV_VAR = "CODEX_REVOKE_TOKEN_URL_OVERRIDE"
DEFAULT_CHATGPT_BACKEND_BASE_URL = "https://chatgpt.com/backend-api"
TOKEN_REFRESH_INTERVAL_DAYS = 8
CHATGPT_ACCESS_TOKEN_REFRESH_WINDOW_MINUTES = 5

REFRESH_TOKEN_EXPIRED_MESSAGE = "Your access token could not be refreshed because your refresh token has expired. Please log out and sign in again."
REFRESH_TOKEN_REUSED_MESSAGE = "Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again."
REFRESH_TOKEN_INVALIDATED_MESSAGE = "Your access token could not be refreshed because your refresh token was revoked. Please log out and sign in again."
REFRESH_TOKEN_UNKNOWN_MESSAGE = "Your access token could not be refreshed. Please log out and sign in again."
REFRESH_TOKEN_ACCOUNT_MISMATCH_MESSAGE = "Your access token could not be refreshed because you have since logged out or signed in to another account. Please sign in again."

AUTH_MODE_API_KEY = "apiKey"
AUTH_MODE_CHATGPT = "chatgpt"
AUTH_MODE_CHATGPT_AUTH_TOKENS = "chatgptAuthTokens"
AUTH_MODE_AGENT_IDENTITY = "agentIdentity"
FORCED_LOGIN_API = "api"
FORCED_LOGIN_CHATGPT = "chatgpt"
EXTERNAL_AUTH_MODE_API_KEY = "api_key"


class RefreshTokenError(Exception):
    def __init__(self, error: RefreshTokenFailedError | OSError) -> None:
        super().__init__(str(error))
        self.error = error

    @classmethod
    def permanent(cls, reason: RefreshTokenFailedReason, message: str) -> "RefreshTokenError":
        return cls(RefreshTokenFailedError(reason, message))

    @classmethod
    def transient(cls, message: str | OSError) -> "RefreshTokenError":
        return cls(message if isinstance(message, OSError) else OSError(message))

    def failed_reason(self) -> RefreshTokenFailedReason | None:
        if isinstance(self.error, RefreshTokenFailedError):
            return self.error.reason
        return None


@dataclass(frozen=True)
class ExternalAuthChatgptMetadata:
    account_id: str
    plan_type: str | None = None


@dataclass(frozen=True)
class ManagerExternalAuthTokens:
    access_token: str
    chatgpt_metadata: ExternalAuthChatgptMetadata | None = None

    @classmethod
    def access_token_only(cls, access_token: str) -> "ManagerExternalAuthTokens":
        return cls(access_token=access_token)

    @classmethod
    def chatgpt(
        cls,
        access_token: str,
        chatgpt_account_id: str,
        chatgpt_plan_type: str | None = None,
    ) -> "ManagerExternalAuthTokens":
        return cls(access_token, ExternalAuthChatgptMetadata(chatgpt_account_id, chatgpt_plan_type))


ExternalAuthRefreshReason = str
EXTERNAL_AUTH_REFRESH_UNAUTHORIZED = "Unauthorized"


class ExternalAuth(Protocol):
    def auth_mode(self) -> str:
        ...

    async def resolve(self) -> ManagerExternalAuthTokens | ExternalAuthTokens | None:
        ...

    async def refresh(self, context: ExternalAuthRefreshContext) -> ManagerExternalAuthTokens | ExternalAuthTokens:
        ...


@dataclass(frozen=True)
class ApiKeyAuth:
    api_key: str


@dataclass
class ChatgptAuth:
    auth_dot_json: AuthDotJson | None
    storage: AuthStorageBackend


@dataclass
class ChatgptAuthTokens:
    auth_dot_json: AuthDotJson | None


@dataclass(frozen=True)
class CodexAuth:
    kind: str
    value: Any

    @classmethod
    def from_api_key(cls, api_key: str) -> "CodexAuth":
        return cls(AUTH_MODE_API_KEY, ApiKeyAuth(api_key))

    @classmethod
    def from_chatgpt(cls, auth_dot_json: AuthDotJson, storage: AuthStorageBackend) -> "CodexAuth":
        return cls(AUTH_MODE_CHATGPT, ChatgptAuth(auth_dot_json, storage))

    @classmethod
    def from_chatgpt_auth_tokens(cls, auth_dot_json: AuthDotJson) -> "CodexAuth":
        return cls(AUTH_MODE_CHATGPT_AUTH_TOKENS, ChatgptAuthTokens(auth_dot_json))

    @classmethod
    async def from_auth_dot_json(
        cls,
        codex_home: str | Path,
        auth_dot_json: AuthDotJson,
        auth_credentials_store_mode: str,
        chatgpt_base_url: str | None = None,
    ) -> "CodexAuth":
        mode = resolved_mode(auth_dot_json)
        if mode == AUTH_MODE_API_KEY:
            if not auth_dot_json.openai_api_key:
                raise OSError("API key auth is missing a key.")
            return cls.from_api_key(auth_dot_json.openai_api_key)
        if mode == AUTH_MODE_AGENT_IDENTITY:
            if not auth_dot_json.agent_identity:
                raise OSError("agent identity auth is missing an agent identity token.")
            record = agent_identity_auth_record_from_agent_identity_jwt(auth_dot_json.agent_identity)
            return cls(AUTH_MODE_AGENT_IDENTITY, AgentIdentityAuth(record, ""))
        if mode == AUTH_MODE_CHATGPT_AUTH_TOKENS:
            return cls.from_chatgpt_auth_tokens(auth_dot_json)
        storage = create_auth_storage(codex_home, storage_mode(auth_dot_json, auth_credentials_store_mode))
        return cls.from_chatgpt(auth_dot_json, storage)

    @classmethod
    async def from_auth_storage(
        cls,
        codex_home: str | Path,
        auth_credentials_store_mode: str,
        chatgpt_base_url: str | None = None,
    ) -> "CodexAuth | None":
        return await load_auth(codex_home, False, auth_credentials_store_mode, chatgpt_base_url)

    def auth_mode(self) -> str:
        if self.kind in {AUTH_MODE_CHATGPT, AUTH_MODE_CHATGPT_AUTH_TOKENS}:
            return AUTH_MODE_CHATGPT
        return self.kind

    def api_auth_mode(self) -> str:
        return self.kind

    def is_api_key_auth(self) -> bool:
        return self.auth_mode() == AUTH_MODE_API_KEY

    def is_chatgpt_auth(self) -> bool:
        return self.kind in {AUTH_MODE_CHATGPT, AUTH_MODE_CHATGPT_AUTH_TOKENS}

    def uses_codex_backend(self) -> bool:
        return self.kind in {AUTH_MODE_CHATGPT, AUTH_MODE_CHATGPT_AUTH_TOKENS, AUTH_MODE_AGENT_IDENTITY}

    def is_external_chatgpt_tokens(self) -> bool:
        return self.kind == AUTH_MODE_CHATGPT_AUTH_TOKENS

    def api_key(self) -> str | None:
        return self.value.api_key if isinstance(self.value, ApiKeyAuth) else None

    def get_current_auth_json(self) -> AuthDotJson | None:
        if isinstance(self.value, ChatgptAuth):
            return self.value.auth_dot_json
        if isinstance(self.value, ChatgptAuthTokens):
            return self.value.auth_dot_json
        return None

    def get_current_token_data(self) -> TokenData | None:
        auth = self.get_current_auth_json()
        return auth.tokens if auth is not None else None

    def get_token_data(self) -> TokenData:
        data = self.get_current_token_data()
        auth = self.get_current_auth_json()
        if data is None or auth is None or auth.last_refresh is None:
            raise OSError("Token data is not available.")
        return data

    def get_token(self) -> str:
        if self.api_key() is not None:
            return self.api_key() or ""
        if self.kind == AUTH_MODE_AGENT_IDENTITY:
            raise OSError("agent identity auth does not expose a bearer token")
        return self.get_token_data().access_token

    def get_account_id(self) -> str | None:
        if self.kind == AUTH_MODE_AGENT_IDENTITY:
            return self.value.account_id()
        data = self.get_current_token_data()
        return data.account_id if data is not None else None

    def get_account_email(self) -> str | None:
        if self.kind == AUTH_MODE_AGENT_IDENTITY:
            return self.value.email()
        data = self.get_current_token_data()
        return data.id_token.email if data is not None else None

    def get_chatgpt_user_id(self) -> str | None:
        if self.kind == AUTH_MODE_AGENT_IDENTITY:
            return self.value.chatgpt_user_id()
        data = self.get_current_token_data()
        return data.id_token.chatgpt_user_id if data is not None else None

    def is_fedramp_account(self) -> bool:
        if self.kind == AUTH_MODE_AGENT_IDENTITY:
            return self.value.is_fedramp_account()
        data = self.get_current_token_data()
        return bool(data and data.id_token.is_fedramp_account())

    def account_plan_type(self) -> Any:
        if self.kind == AUTH_MODE_AGENT_IDENTITY:
            return self.value.plan_type()
        data = self.get_current_token_data()
        return data.id_token.chatgpt_plan_type if data is not None else None

    def is_workspace_account(self) -> bool:
        data = self.get_current_token_data()
        return bool(data and data.id_token.is_workspace_account())

    @classmethod
    def create_dummy_chatgpt_auth_for_testing(cls) -> "CodexAuth":
        auth = AuthDotJson(
            auth_mode=AUTH_MODE_CHATGPT,
            tokens=TokenData(access_token="Access Token", refresh_token="test", account_id="account_id"),
            last_refresh=datetime.now(timezone.utc),
        )
        return cls.from_chatgpt(auth, create_auth_storage("dummy-chatgpt-auth", "ephemeral"))


def read_openai_api_key_from_env(env: Mapping[str, str] | None = None) -> str | None:
    return _read_non_empty_env_var(OPENAI_API_KEY_ENV_VAR, env)


def read_codex_api_key_from_env(env: Mapping[str, str] | None = None) -> str | None:
    return _read_non_empty_env_var(CODEX_API_KEY_ENV_VAR, env)


def read_codex_access_token_from_env(env: Mapping[str, str] | None = None) -> str | None:
    return _read_non_empty_env_var(CODEX_ACCESS_TOKEN_ENV_VAR, env)


def _read_non_empty_env_var(key: str, env: Mapping[str, str] | None = None) -> str | None:
    env_map = os.environ if env is None else env
    value = env_map.get(key)
    if value is None:
        return None
    trimmed = str(value).strip()
    return trimmed or None


def logout(codex_home: str | Path, auth_credentials_store_mode: str = "file") -> bool:
    return create_auth_storage(codex_home, auth_credentials_store_mode).delete()


async def logout_with_revoke(codex_home: str | Path, auth_credentials_store_mode: str = "file") -> bool:
    manager = await AuthManager.new(codex_home, False, auth_credentials_store_mode)
    return await manager.logout_with_revoke()


def login_with_api_key(codex_home: str | Path, api_key: str, auth_credentials_store_mode: str = "file") -> None:
    save_auth(codex_home, AuthDotJson(auth_mode=AUTH_MODE_API_KEY, openai_api_key=api_key), auth_credentials_store_mode)


async def login_with_access_token(
    codex_home: str | Path,
    access_token: str,
    auth_credentials_store_mode: str = "file",
    chatgpt_base_url: str | None = None,
) -> None:
    agent_identity_auth_record_from_agent_identity_jwt(access_token)
    save_auth(codex_home, AuthDotJson(auth_mode=AUTH_MODE_AGENT_IDENTITY, agent_identity=access_token), auth_credentials_store_mode)


def login_with_chatgpt_auth_tokens(
    codex_home: str | Path,
    access_token: str,
    chatgpt_account_id: str,
    chatgpt_plan_type: str | None = None,
) -> None:
    save_auth(codex_home, auth_dot_json_from_external_access_token(access_token, chatgpt_account_id, chatgpt_plan_type), "ephemeral")


def save_auth(codex_home: str | Path, auth: AuthDotJson, auth_credentials_store_mode: str = "file") -> None:
    create_auth_storage(codex_home, auth_credentials_store_mode).save(auth)


def load_auth_dot_json(codex_home: str | Path, auth_credentials_store_mode: str = "file") -> AuthDotJson | None:
    return create_auth_storage(codex_home, auth_credentials_store_mode).load()


@dataclass(frozen=True)
class AuthConfig:
    codex_home: Path
    auth_credentials_store_mode: str = "file"
    forced_login_method: str | None = None
    chatgpt_base_url: str | None = None
    forced_chatgpt_workspace_id: list[str] | None = None


class AuthManagerConfig(Protocol):
    codex_home: Path
    auth_credentials_store_mode: str
    forced_login_method: str | None
    chatgpt_base_url: str | None
    forced_chatgpt_workspace_id: list[str] | None


async def enforce_login_restrictions(config: AuthConfig) -> None:
    auth = await load_auth(config.codex_home, True, config.auth_credentials_store_mode, config.chatgpt_base_url)
    if auth is None:
        return
    if config.forced_login_method == FORCED_LOGIN_API and auth.auth_mode() != AUTH_MODE_API_KEY:
        return _logout_with_error(config, "API key login is required, but ChatGPT is currently being used. Logging out.")
    if config.forced_login_method == FORCED_LOGIN_CHATGPT and auth.auth_mode() == AUTH_MODE_API_KEY:
        return _logout_with_error(config, "ChatGPT login is required, but an API key is currently being used. Logging out.")
    if config.forced_chatgpt_workspace_id and auth.auth_mode() != AUTH_MODE_API_KEY:
        actual = auth.get_account_id()
        if actual not in config.forced_chatgpt_workspace_id:
            expected = ", ".join(config.forced_chatgpt_workspace_id)
            if actual is None:
                message = f"Login is restricted to workspace(s) {expected}, but current credentials lack a workspace identifier. Logging out."
            else:
                message = f"Login is restricted to workspace(s) {expected}, but current credentials belong to {actual}. Logging out."
            return _logout_with_error(config, message)


def _logout_with_error(config: AuthConfig, message: str) -> None:
    try:
        logout_all_stores(config.codex_home, config.auth_credentials_store_mode)
    except Exception as exc:
        raise OSError(f"{message}. Failed to remove auth.json: {exc}") from exc
    raise OSError(message)


def logout_all_stores(codex_home: str | Path, auth_credentials_store_mode: str = "file") -> bool:
    if str(auth_credentials_store_mode).lower() == "ephemeral":
        return logout(codex_home, "ephemeral")
    removed_ephemeral = logout(codex_home, "ephemeral")
    removed_managed = logout(codex_home, auth_credentials_store_mode)
    return removed_ephemeral or removed_managed


async def load_auth(
    codex_home: str | Path,
    enable_codex_api_key_env: bool,
    auth_credentials_store_mode: str = "file",
    chatgpt_base_url: str | None = None,
) -> CodexAuth | None:
    if enable_codex_api_key_env and (api_key := read_codex_api_key_from_env()):
        return CodexAuth.from_api_key(api_key)
    ephemeral = create_auth_storage(codex_home, "ephemeral").load()
    if ephemeral is not None:
        return await CodexAuth.from_auth_dot_json(codex_home, ephemeral, "ephemeral", chatgpt_base_url)
    if str(auth_credentials_store_mode).lower() == "ephemeral":
        return None
    if agent_identity := read_codex_access_token_from_env():
        return await CodexAuth.from_auth_dot_json(
            codex_home,
            AuthDotJson(auth_mode=AUTH_MODE_AGENT_IDENTITY, agent_identity=agent_identity),
            auth_credentials_store_mode,
            chatgpt_base_url,
        )
    auth = create_auth_storage(codex_home, auth_credentials_store_mode).load()
    if auth is None:
        return None
    return await CodexAuth.from_auth_dot_json(codex_home, auth, auth_credentials_store_mode, chatgpt_base_url)


def persist_tokens(
    storage: AuthStorageBackend,
    id_token: str | None,
    access_token: str | None,
    refresh_token: str | None,
) -> AuthDotJson:
    auth = storage.load()
    if auth is None:
        raise OSError("Token data is not available.")
    tokens = auth.tokens or TokenData()
    auth = AuthDotJson(
        auth_mode=auth.auth_mode,
        openai_api_key=auth.openai_api_key,
        tokens=TokenData(
            id_token=parse_chatgpt_jwt_claims(id_token) if id_token is not None else tokens.id_token,
            access_token=access_token if access_token is not None else tokens.access_token,
            refresh_token=refresh_token if refresh_token is not None else tokens.refresh_token,
            account_id=tokens.account_id,
        ),
        last_refresh=datetime.now(timezone.utc),
        agent_identity=auth.agent_identity,
    )
    storage.save(auth)
    return auth


def classify_refresh_token_failure(body: str) -> RefreshTokenFailedError:
    code = extract_refresh_token_error_code(body)
    normalized = code.lower() if code is not None else None
    if normalized == "refresh_token_expired":
        return RefreshTokenFailedError(RefreshTokenFailedReason.EXPIRED, REFRESH_TOKEN_EXPIRED_MESSAGE)
    if normalized == "refresh_token_reused":
        return RefreshTokenFailedError(RefreshTokenFailedReason.EXHAUSTED, REFRESH_TOKEN_REUSED_MESSAGE)
    if normalized == "refresh_token_invalidated":
        return RefreshTokenFailedError(RefreshTokenFailedReason.REVOKED, REFRESH_TOKEN_INVALIDATED_MESSAGE)
    return RefreshTokenFailedError(RefreshTokenFailedReason.OTHER, REFRESH_TOKEN_UNKNOWN_MESSAGE)


def extract_refresh_token_error_code(body: str) -> str | None:
    if not body.strip():
        return None
    try:
        parsed = json_loads_object(body)
    except ValueError:
        return None
    error = parsed.get("error")
    if isinstance(error, Mapping):
        code = error.get("code")
        return code if isinstance(code, str) else None
    if isinstance(error, str):
        return error
    code = parsed.get("code")
    return code if isinstance(code, str) else None


def refresh_token_endpoint(env: Mapping[str, str] | None = None) -> str:
    env_map = os.environ if env is None else env
    return env_map.get(REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR, REFRESH_TOKEN_URL)


def auth_dot_json_from_external_tokens(tokens: ManagerExternalAuthTokens | ExternalAuthTokens) -> AuthDotJson:
    metadata = _chatgpt_metadata(tokens)
    if metadata is None:
        raise OSError("external auth tokens are missing ChatGPT metadata")
    token_info = parse_chatgpt_jwt_claims(tokens.access_token)
    token_info = type(token_info)(
        email=token_info.email,
        chatgpt_plan_type=token_info.chatgpt_plan_type,
        chatgpt_user_id=token_info.chatgpt_user_id,
        chatgpt_account_id=metadata.account_id,
        chatgpt_account_is_fedramp=token_info.chatgpt_account_is_fedramp,
        raw_jwt=token_info.raw_jwt,
    )
    return AuthDotJson(
        auth_mode=AUTH_MODE_CHATGPT_AUTH_TOKENS,
        tokens=TokenData(id_token=token_info, access_token=tokens.access_token, refresh_token="", account_id=metadata.account_id),
        last_refresh=datetime.now(timezone.utc),
    )


def auth_dot_json_from_external_access_token(
    access_token: str,
    chatgpt_account_id: str,
    chatgpt_plan_type: str | None = None,
) -> AuthDotJson:
    return auth_dot_json_from_external_tokens(ManagerExternalAuthTokens.chatgpt(access_token, chatgpt_account_id, chatgpt_plan_type))


def resolved_mode(auth_dot_json: AuthDotJson) -> str:
    if auth_dot_json.auth_mode is not None:
        return auth_dot_json.auth_mode
    if auth_dot_json.openai_api_key is not None:
        return AUTH_MODE_API_KEY
    return AUTH_MODE_CHATGPT


def storage_mode(auth_dot_json: AuthDotJson, auth_credentials_store_mode: str) -> str:
    if resolved_mode(auth_dot_json) == AUTH_MODE_CHATGPT_AUTH_TOKENS:
        return "ephemeral"
    return auth_credentials_store_mode


@dataclass(frozen=True)
class UnauthorizedRecoveryStepResult:
    auth_state_changed: bool | None


class UnauthorizedRecovery:
    def __init__(self, manager: "AuthManager") -> None:
        self.manager = manager
        cached = manager.auth_cached()
        self.expected_account_id = cached.get_account_id() if cached is not None else None
        self.mode = "external" if manager.has_external_api_key_auth() or (cached and cached.is_external_chatgpt_tokens()) else "managed"
        self.step = "external_refresh" if self.mode == "external" else "reload"

    def has_next(self) -> bool:
        if self.manager.has_external_api_key_auth():
            return self.step != "done"
        cached = self.manager.auth_cached()
        if cached is None or not cached.is_chatgpt_auth():
            return False
        if self.mode == "external" and not self.manager.has_external_auth():
            return False
        return self.step != "done"

    def unavailable_reason(self) -> str:
        if self.manager.has_external_api_key_auth():
            return "recovery_exhausted" if self.step == "done" else "ready"
        cached = self.manager.auth_cached()
        if cached is None or not cached.is_chatgpt_auth():
            return "not_chatgpt_auth"
        if self.mode == "external" and not self.manager.has_external_auth():
            return "no_external_auth"
        return "recovery_exhausted" if self.step == "done" else "ready"

    def mode_name(self) -> str:
        return self.mode

    def step_name(self) -> str:
        return self.step

    async def next(self) -> UnauthorizedRecoveryStepResult:
        if not self.has_next():
            raise RefreshTokenError.permanent(RefreshTokenFailedReason.OTHER, "No more recovery steps available.")
        if self.step == "reload":
            changed = await self.manager.reload()
            self.step = "refresh_token"
            return UnauthorizedRecoveryStepResult(changed)
        if self.step == "refresh_token":
            await self.manager.refresh_token_from_authority()
            self.step = "done"
            return UnauthorizedRecoveryStepResult(True)
        if self.step == "external_refresh":
            await self.manager.refresh_external_auth(EXTERNAL_AUTH_REFRESH_UNAUTHORIZED)
            self.step = "done"
            return UnauthorizedRecoveryStepResult(True)
        return UnauthorizedRecoveryStepResult(None)


class AuthManager:
    def __init__(
        self,
        codex_home: str | Path,
        enable_codex_api_key_env: bool,
        auth_credentials_store_mode: str = "file",
        chatgpt_base_url: str | None = None,
        auth: CodexAuth | None = None,
    ) -> None:
        self.codex_home = Path(codex_home)
        self.enable_codex_api_key_env = enable_codex_api_key_env
        self.auth_credentials_store_mode = auth_credentials_store_mode
        self.chatgpt_base_url = chatgpt_base_url
        self._auth = auth
        self._external_auth: ExternalAuth | None = None
        self._forced_chatgpt_workspace_id: list[str] | None = None
        self._permanent_refresh_failure: tuple[CodexAuth, RefreshTokenFailedError] | None = None

    @classmethod
    async def new(
        cls,
        codex_home: str | Path,
        enable_codex_api_key_env: bool,
        auth_credentials_store_mode: str = "file",
        chatgpt_base_url: str | None = None,
    ) -> "AuthManager":
        auth = await load_auth(codex_home, enable_codex_api_key_env, auth_credentials_store_mode, chatgpt_base_url)
        return cls(codex_home, enable_codex_api_key_env, auth_credentials_store_mode, chatgpt_base_url, auth)

    @classmethod
    def from_auth_for_testing(cls, auth: CodexAuth) -> "AuthManager":
        return cls("non-existent", False, "file", auth=auth)

    @classmethod
    def from_auth_for_testing_with_home(cls, auth: CodexAuth, codex_home: str | Path) -> "AuthManager":
        return cls(codex_home, False, "file", auth=auth)

    @classmethod
    async def shared_from_config(cls, config: AuthManagerConfig | AuthConfig) -> "AuthManager":
        manager = await cls.new(
            config.codex_home,
            True,
            config.auth_credentials_store_mode,
            config.chatgpt_base_url,
        )
        manager.set_forced_chatgpt_workspace_id(config.forced_chatgpt_workspace_id)
        return manager

    @classmethod
    def external_bearer_only(cls, external_auth: ExternalAuth) -> "AuthManager":
        manager = cls("non-existent", False)
        manager.set_external_auth(external_auth)
        return manager

    def auth_cached(self) -> CodexAuth | None:
        return self._auth

    async def auth(self) -> CodexAuth | None:
        if resolved := await self.resolve_external_api_key_auth():
            return resolved
        return self._auth

    async def reload(self) -> bool:
        new_auth = await load_auth(self.codex_home, self.enable_codex_api_key_env, self.auth_credentials_store_mode, self.chatgpt_base_url)
        changed = new_auth != self._auth
        self._auth = new_auth
        if changed:
            self._permanent_refresh_failure = None
        return changed

    def refresh_failure_for_auth(self, auth: CodexAuth) -> RefreshTokenFailedError | None:
        if self._permanent_refresh_failure and self._permanent_refresh_failure[0] == auth:
            return self._permanent_refresh_failure[1]
        return None

    def record_permanent_refresh_failure_if_unchanged(self, attempted_auth: CodexAuth, error: RefreshTokenFailedError) -> None:
        if self._auth == attempted_auth:
            self._permanent_refresh_failure = (attempted_auth, error)

    def set_external_auth(self, external_auth: ExternalAuth) -> None:
        self._external_auth = external_auth

    def clear_external_auth(self) -> None:
        self._external_auth = None

    def has_external_auth(self) -> bool:
        return self._external_auth is not None

    def set_forced_chatgpt_workspace_id(self, workspace_id: list[str] | None) -> None:
        self._forced_chatgpt_workspace_id = workspace_id

    def forced_chatgpt_workspace_id(self) -> list[str] | None:
        return self._forced_chatgpt_workspace_id

    def codex_api_key_env_enabled(self) -> bool:
        return self.enable_codex_api_key_env

    def has_external_api_key_auth(self) -> bool:
        return self._external_auth is not None and self._external_auth.auth_mode() in {
            AUTH_MODE_API_KEY,
            EXTERNAL_AUTH_MODE_API_KEY,
        }

    async def resolve_external_api_key_auth(self) -> CodexAuth | None:
        if not self.has_external_api_key_auth() or self._external_auth is None:
            return None
        resolved = await self._external_auth.resolve()
        return CodexAuth.from_api_key(resolved.access_token) if resolved is not None else None

    def unauthorized_recovery(self) -> UnauthorizedRecovery:
        return UnauthorizedRecovery(self)

    async def refresh_token(self) -> None:
        await self.refresh_token_from_authority()

    async def refresh_token_from_authority(self) -> None:
        auth = self._auth
        if auth is None or auth.is_api_key_auth():
            return
        if error := self.refresh_failure_for_auth(auth):
            raise RefreshTokenError(error)
        if auth.is_external_chatgpt_tokens():
            await self.refresh_external_auth(EXTERNAL_AUTH_REFRESH_UNAUTHORIZED)

    async def refresh_external_auth(self, reason: ExternalAuthRefreshReason) -> None:
        if self._external_auth is None:
            raise RefreshTokenError.transient("external auth is not configured")
        previous_account_id = self._auth.get_account_id() if self._auth else None
        try:
            context = ExternalAuthRefreshContext(reason=reason, previous_account_id=previous_account_id)
        except TypeError:
            context = ExternalAuthRefreshContext(reason=reason)
        refreshed = await self._external_auth.refresh(context)
        if self._external_auth.auth_mode() == AUTH_MODE_API_KEY:
            return
        metadata = _chatgpt_metadata(refreshed)
        if metadata is None:
            raise RefreshTokenError.transient("external auth refresh did not return ChatGPT metadata")
        if self._forced_chatgpt_workspace_id is not None and metadata.account_id not in self._forced_chatgpt_workspace_id:
            raise RefreshTokenError.transient(
                f"external auth refresh returned workspace {metadata.account_id!r}, expected one of {self._forced_chatgpt_workspace_id!r}"
            )
        save_auth(self.codex_home, auth_dot_json_from_external_tokens(refreshed), "ephemeral")
        await self.reload()

    async def logout(self) -> bool:
        removed = logout_all_stores(self.codex_home, self.auth_credentials_store_mode)
        await self.reload()
        return removed

    async def logout_with_revoke(self) -> bool:
        auth_json = self._auth.get_current_auth_json() if self._auth is not None else None
        try:
            await revoke_auth_tokens(auth_json)
        except Exception:
            pass
        return await self.logout()

    def get_api_auth_mode(self) -> str | None:
        if self.has_external_api_key_auth():
            return AUTH_MODE_API_KEY
        return self._auth.api_auth_mode() if self._auth is not None else None

    def auth_mode(self) -> str | None:
        if self.has_external_api_key_auth():
            return AUTH_MODE_API_KEY
        return self._auth.auth_mode() if self._auth is not None else None

    def current_auth_uses_codex_backend(self) -> bool:
        return self.auth_mode() in {AUTH_MODE_CHATGPT, AUTH_MODE_CHATGPT_AUTH_TOKENS, AUTH_MODE_AGENT_IDENTITY}

    @staticmethod
    def should_refresh_proactively(auth: CodexAuth) -> bool:
        auth_json = auth.get_current_auth_json()
        if auth.kind != AUTH_MODE_CHATGPT or auth_json is None:
            return False
        if auth_json.tokens is not None:
            try:
                expires_at = parse_jwt_expiration(auth_json.tokens.access_token)
            except Exception:
                expires_at = None
            if expires_at is not None:
                return expires_at <= datetime.now(timezone.utc) + timedelta(minutes=CHATGPT_ACCESS_TOKEN_REFRESH_WINDOW_MINUTES)
        if isinstance(auth_json.last_refresh, datetime):
            return auth_json.last_refresh < datetime.now(timezone.utc) - timedelta(days=TOKEN_REFRESH_INTERVAL_DAYS)
        return False


def json_loads_object(body: str) -> dict[str, Any]:
    parsed = __import__("json").loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("expected object")
    return parsed


def _chatgpt_metadata(tokens: ManagerExternalAuthTokens | ExternalAuthTokens) -> ExternalAuthChatgptMetadata | None:
    metadata = getattr(tokens, "chatgpt_metadata", None)
    if callable(metadata):
        metadata = metadata()
    if metadata is None:
        return None
    if isinstance(metadata, ExternalAuthChatgptMetadata):
        return metadata
    account_id = getattr(metadata, "account_id", None)
    plan_type = getattr(metadata, "plan_type", None)
    if isinstance(account_id, str):
        return ExternalAuthChatgptMetadata(account_id, plan_type if isinstance(plan_type, str) else None)
    return None


__all__ = [
    "AUTH_MODE_AGENT_IDENTITY",
    "AUTH_MODE_API_KEY",
    "AUTH_MODE_CHATGPT",
    "AUTH_MODE_CHATGPT_AUTH_TOKENS",
    "CLIENT_ID",
    "CODEX_ACCESS_TOKEN_ENV_VAR",
    "CODEX_API_KEY_ENV_VAR",
    "DEFAULT_CHATGPT_BACKEND_BASE_URL",
    "EXTERNAL_AUTH_MODE_API_KEY",
    "OPENAI_API_KEY_ENV_VAR",
    "REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR",
    "REVOKE_TOKEN_URL_OVERRIDE_ENV_VAR",
    "ApiKeyAuth",
    "AuthConfig",
    "AuthManager",
    "AuthManagerConfig",
    "ChatgptAuth",
    "ChatgptAuthTokens",
    "CodexAuth",
    "ExternalAuth",
    "ExternalAuthChatgptMetadata",
    "ExternalAuthRefreshReason",
    "ManagerExternalAuthTokens",
    "RefreshTokenError",
    "UnauthorizedRecovery",
    "UnauthorizedRecoveryStepResult",
    "auth_dot_json_from_external_access_token",
    "auth_dot_json_from_external_tokens",
    "classify_refresh_token_failure",
    "enforce_login_restrictions",
    "extract_refresh_token_error_code",
    "load_auth",
    "load_auth_dot_json",
    "login_with_access_token",
    "login_with_api_key",
    "login_with_chatgpt_auth_tokens",
    "logout",
    "logout_all_stores",
    "logout_with_revoke",
    "persist_tokens",
    "read_codex_access_token_from_env",
    "read_codex_api_key_from_env",
    "read_openai_api_key_from_env",
    "refresh_token_endpoint",
    "resolved_mode",
    "save_auth",
    "storage_mode",
]
