"""Account protocol types ported from ``protocol/v2/account.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.protocol.account import PlanType
from pycodex.protocol.account import ProviderAccount

JsonValue = Any


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__} value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid {cls.__name__}: {raw}; expected one of: {choices}") from exc


class AuthMode(_StringEnum):
    API_KEY = "apikey"
    CHATGPT = "chatgpt"
    CHATGPT_AUTH_TOKENS = "chatgptAuthTokens"
    AGENT_IDENTITY = "agentIdentity"


@dataclass(frozen=True)
class Account:
    type: str
    email: str | None = None
    plan_type: PlanType | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _ensure_str(self.type, "type"))
        object.__setattr__(self, "email", _optional_str(self.email, "email"))
        object.__setattr__(self, "plan_type", _optional_plan_type(self.plan_type, "plan_type"))
        if self.type == "apiKey":
            _reject_fields(self, "email", "plan_type")
        elif self.type == "chatgpt":
            _require_field(self.email, "email")
            _require_field(self.plan_type, "plan_type")
        elif self.type == "amazonBedrock":
            _reject_fields(self, "email", "plan_type")
        else:
            raise ValueError(f"unknown account type: {self.type}")

    @classmethod
    def api_key(cls) -> "Account":
        return cls("apiKey")

    @classmethod
    def chatgpt(cls, email: str, plan_type: PlanType | str) -> "Account":
        return cls("chatgpt", email=email, plan_type=plan_type)

    @classmethod
    def amazon_bedrock(cls) -> "Account":
        return cls("amazonBedrock")

    @classmethod
    def from_provider_account(cls, value: ProviderAccount) -> "Account":
        if not isinstance(value, ProviderAccount):
            raise TypeError("value must be a ProviderAccount")
        if value.kind == "api_key":
            return cls.api_key()
        if value.kind == "chatgpt":
            return cls.chatgpt(value.email or "", value.plan_type or PlanType.UNKNOWN)
        if value.kind == "amazon_bedrock":
            return cls.amazon_bedrock()
        raise ValueError(f"unknown provider account kind: {value.kind}")

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "Account":
        data = _mapping(value, "Account")
        account_type = _ensure_str(data["type"], "type")
        if account_type == "apiKey":
            return cls.api_key()
        if account_type == "chatgpt":
            return cls.chatgpt(_ensure_str(data["email"], "email"), _plan_type(_pick(data, "plan_type", "planType")))
        if account_type == "amazonBedrock":
            return cls.amazon_bedrock()
        raise ValueError(f"unknown account type: {account_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"type": self.type}
        if self.type == "chatgpt":
            result["email"] = self.email
            result["plan_type"] = self.plan_type.value
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"type": self.type}
        if self.type == "chatgpt":
            result["email"] = self.email
            result["planType"] = self.plan_type.value
        return result


@dataclass(frozen=True)
class LoginAccountParams:
    type: str
    api_key: str | None = None
    codex_streamlined_login: bool = False
    access_token: str | None = None
    chatgpt_account_id: str | None = None
    chatgpt_plan_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _ensure_str(self.type, "type"))
        object.__setattr__(self, "api_key", _optional_str(self.api_key, "api_key"))
        object.__setattr__(self, "codex_streamlined_login", _ensure_bool(self.codex_streamlined_login, "codex_streamlined_login"))
        object.__setattr__(self, "access_token", _optional_str(self.access_token, "access_token"))
        object.__setattr__(self, "chatgpt_account_id", _optional_str(self.chatgpt_account_id, "chatgpt_account_id"))
        object.__setattr__(self, "chatgpt_plan_type", _optional_str(self.chatgpt_plan_type, "chatgpt_plan_type"))
        if self.type == "apiKey":
            _require_field(self.api_key, "api_key")
            _reject_fields(self, "access_token", "chatgpt_account_id", "chatgpt_plan_type")
        elif self.type == "chatgpt":
            _reject_fields(self, "api_key", "access_token", "chatgpt_account_id", "chatgpt_plan_type")
        elif self.type == "chatgptDeviceCode":
            _reject_fields(self, "api_key", "access_token", "chatgpt_account_id", "chatgpt_plan_type")
            if self.codex_streamlined_login:
                raise ValueError("codex_streamlined_login is not valid for chatgptDeviceCode login")
        elif self.type == "chatgptAuthTokens":
            _require_field(self.access_token, "access_token")
            _require_field(self.chatgpt_account_id, "chatgpt_account_id")
            _reject_fields(self, "api_key")
            if self.codex_streamlined_login:
                raise ValueError("codex_streamlined_login is not valid for chatgptAuthTokens login")
        else:
            raise ValueError(f"unknown login account params type: {self.type}")

    @classmethod
    def api_key_login(cls, api_key: str) -> "LoginAccountParams":
        return cls("apiKey", api_key=api_key)

    @classmethod
    def chatgpt(cls, codex_streamlined_login: bool = False) -> "LoginAccountParams":
        return cls("chatgpt", codex_streamlined_login=codex_streamlined_login)

    @classmethod
    def chatgpt_device_code(cls) -> "LoginAccountParams":
        return cls("chatgptDeviceCode")

    @classmethod
    def chatgpt_auth_tokens(
        cls,
        access_token: str,
        chatgpt_account_id: str,
        chatgpt_plan_type: str | None = None,
    ) -> "LoginAccountParams":
        return cls(
            "chatgptAuthTokens",
            access_token=access_token,
            chatgpt_account_id=chatgpt_account_id,
            chatgpt_plan_type=chatgpt_plan_type,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "LoginAccountParams":
        data = _mapping(value, "LoginAccountParams")
        login_type = _ensure_str(data["type"], "type")
        if login_type == "apiKey":
            return cls.api_key_login(_ensure_str(_pick(data, "api_key", "apiKey"), "api_key"))
        if login_type == "chatgpt":
            return cls.chatgpt(
                _ensure_bool(
                    _pick(data, "codex_streamlined_login", "codexStreamlinedLogin", default=False),
                    "codex_streamlined_login",
                )
            )
        if login_type == "chatgptDeviceCode":
            return cls.chatgpt_device_code()
        if login_type == "chatgptAuthTokens":
            return cls.chatgpt_auth_tokens(
                _ensure_str(_pick(data, "access_token", "accessToken"), "access_token"),
                _ensure_str(_pick(data, "chatgpt_account_id", "chatgptAccountId"), "chatgpt_account_id"),
                _optional_str(_pick(data, "chatgpt_plan_type", "chatgptPlanType"), "chatgpt_plan_type"),
            )
        raise ValueError(f"unknown login account params type: {login_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"type": self.type}
        if self.type == "apiKey":
            result["api_key"] = self.api_key
        elif self.type == "chatgpt":
            _put_true(result, "codex_streamlined_login", self.codex_streamlined_login)
        elif self.type == "chatgptAuthTokens":
            result.update(
                {
                    "access_token": self.access_token,
                    "chatgpt_account_id": self.chatgpt_account_id,
                    "chatgpt_plan_type": self.chatgpt_plan_type,
                }
            )
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"type": self.type}
        if self.type == "apiKey":
            result["apiKey"] = self.api_key
        elif self.type == "chatgpt":
            _put_true(result, "codexStreamlinedLogin", self.codex_streamlined_login)
        elif self.type == "chatgptAuthTokens":
            result.update(
                {
                    "accessToken": self.access_token,
                    "chatgptAccountId": self.chatgpt_account_id,
                    "chatgptPlanType": self.chatgpt_plan_type,
                }
            )
        return result


@dataclass(frozen=True)
class LoginAccountResponse:
    type: str
    login_id: str | None = None
    auth_url: str | None = None
    verification_url: str | None = None
    user_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _ensure_str(self.type, "type"))
        object.__setattr__(self, "login_id", _optional_str(self.login_id, "login_id"))
        object.__setattr__(self, "auth_url", _optional_str(self.auth_url, "auth_url"))
        object.__setattr__(self, "verification_url", _optional_str(self.verification_url, "verification_url"))
        object.__setattr__(self, "user_code", _optional_str(self.user_code, "user_code"))
        if self.type in {"apiKey", "chatgptAuthTokens"}:
            _reject_fields(self, "login_id", "auth_url", "verification_url", "user_code")
        elif self.type == "chatgpt":
            _require_field(self.login_id, "login_id")
            _require_field(self.auth_url, "auth_url")
            _reject_fields(self, "verification_url", "user_code")
        elif self.type == "chatgptDeviceCode":
            _require_field(self.login_id, "login_id")
            _require_field(self.verification_url, "verification_url")
            _require_field(self.user_code, "user_code")
            _reject_fields(self, "auth_url")
        else:
            raise ValueError(f"unknown login account response type: {self.type}")

    @classmethod
    def api_key(cls) -> "LoginAccountResponse":
        return cls("apiKey")

    @classmethod
    def chatgpt(cls, login_id: str, auth_url: str) -> "LoginAccountResponse":
        return cls("chatgpt", login_id=login_id, auth_url=auth_url)

    @classmethod
    def chatgpt_device_code(cls, login_id: str, verification_url: str, user_code: str) -> "LoginAccountResponse":
        return cls("chatgptDeviceCode", login_id=login_id, verification_url=verification_url, user_code=user_code)

    @classmethod
    def chatgpt_auth_tokens(cls) -> "LoginAccountResponse":
        return cls("chatgptAuthTokens")

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "LoginAccountResponse":
        data = _mapping(value, "LoginAccountResponse")
        response_type = _ensure_str(data["type"], "type")
        if response_type == "apiKey":
            return cls.api_key()
        if response_type == "chatgpt":
            return cls.chatgpt(
                _ensure_str(_pick(data, "login_id", "loginId"), "login_id"),
                _ensure_str(_pick(data, "auth_url", "authUrl"), "auth_url"),
            )
        if response_type == "chatgptDeviceCode":
            return cls.chatgpt_device_code(
                _ensure_str(_pick(data, "login_id", "loginId"), "login_id"),
                _ensure_str(_pick(data, "verification_url", "verificationUrl"), "verification_url"),
                _ensure_str(_pick(data, "user_code", "userCode"), "user_code"),
            )
        if response_type == "chatgptAuthTokens":
            return cls.chatgpt_auth_tokens()
        raise ValueError(f"unknown login account response type: {response_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"type": self.type}
        if self.type == "chatgpt":
            result.update({"login_id": self.login_id, "auth_url": self.auth_url})
        elif self.type == "chatgptDeviceCode":
            result.update(
                {
                    "login_id": self.login_id,
                    "verification_url": self.verification_url,
                    "user_code": self.user_code,
                }
            )
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"type": self.type}
        if self.type == "chatgpt":
            result.update({"loginId": self.login_id, "authUrl": self.auth_url})
        elif self.type == "chatgptDeviceCode":
            result.update(
                {
                    "loginId": self.login_id,
                    "verificationUrl": self.verification_url,
                    "userCode": self.user_code,
                }
            )
        return result


@dataclass(frozen=True)
class CancelLoginAccountParams:
    login_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "login_id", _ensure_str(self.login_id, "login_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CancelLoginAccountParams":
        data = _mapping(value, "CancelLoginAccountParams")
        return cls(_ensure_str(_pick(data, "login_id", "loginId"), "login_id"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"login_id": self.login_id}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"loginId": self.login_id}


class CancelLoginAccountStatus(_StringEnum):
    CANCELED = "canceled"
    NOT_FOUND = "notFound"


@dataclass(frozen=True)
class CancelLoginAccountResponse:
    status: CancelLoginAccountStatus | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", CancelLoginAccountStatus.parse(self.status))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CancelLoginAccountResponse":
        data = _mapping(value, "CancelLoginAccountResponse")
        return cls(CancelLoginAccountStatus.parse(data["status"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"status": self.status.value}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class LogoutAccountResponse:
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "LogoutAccountResponse":
        if value is not None:
            _mapping(value, "LogoutAccountResponse")
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {}


class ChatgptAuthTokensRefreshReason(_StringEnum):
    UNAUTHORIZED = "unauthorized"


@dataclass(frozen=True)
class ChatgptAuthTokensRefreshParams:
    reason: ChatgptAuthTokensRefreshReason | str
    previous_account_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", ChatgptAuthTokensRefreshReason.parse(self.reason))
        object.__setattr__(self, "previous_account_id", _optional_str(self.previous_account_id, "previous_account_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ChatgptAuthTokensRefreshParams":
        data = _mapping(value, "ChatgptAuthTokensRefreshParams")
        return cls(
            ChatgptAuthTokensRefreshReason.parse(data["reason"]),
            _optional_str(_pick(data, "previous_account_id", "previousAccountId"), "previous_account_id"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"reason": self.reason.value, "previous_account_id": self.previous_account_id}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"reason": self.reason.value, "previousAccountId": self.previous_account_id}


@dataclass(frozen=True)
class ChatgptAuthTokensRefreshResponse:
    access_token: str
    chatgpt_account_id: str
    chatgpt_plan_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "access_token", _ensure_str(self.access_token, "access_token"))
        object.__setattr__(self, "chatgpt_account_id", _ensure_str(self.chatgpt_account_id, "chatgpt_account_id"))
        object.__setattr__(self, "chatgpt_plan_type", _optional_str(self.chatgpt_plan_type, "chatgpt_plan_type"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ChatgptAuthTokensRefreshResponse":
        data = _mapping(value, "ChatgptAuthTokensRefreshResponse")
        return cls(
            _ensure_str(_pick(data, "access_token", "accessToken"), "access_token"),
            _ensure_str(_pick(data, "chatgpt_account_id", "chatgptAccountId"), "chatgpt_account_id"),
            _optional_str(_pick(data, "chatgpt_plan_type", "chatgptPlanType"), "chatgpt_plan_type"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "access_token": self.access_token,
            "chatgpt_account_id": self.chatgpt_account_id,
            "chatgpt_plan_type": self.chatgpt_plan_type,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "accessToken": self.access_token,
            "chatgptAccountId": self.chatgpt_account_id,
            "chatgptPlanType": self.chatgpt_plan_type,
        }


class AddCreditsNudgeCreditType(_StringEnum):
    CREDITS = "credits"
    USAGE_LIMIT = "usage_limit"


class AddCreditsNudgeEmailStatus(_StringEnum):
    SENT = "sent"
    COOLDOWN_ACTIVE = "cooldown_active"


@dataclass(frozen=True)
class SendAddCreditsNudgeEmailParams:
    credit_type: AddCreditsNudgeCreditType | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "credit_type", AddCreditsNudgeCreditType.parse(self.credit_type))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "SendAddCreditsNudgeEmailParams":
        data = _mapping(value, "SendAddCreditsNudgeEmailParams")
        return cls(AddCreditsNudgeCreditType.parse(_pick(data, "credit_type", "creditType")))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"credit_type": self.credit_type.value}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"creditType": self.credit_type.value}


@dataclass(frozen=True)
class SendAddCreditsNudgeEmailResponse:
    status: AddCreditsNudgeEmailStatus | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", AddCreditsNudgeEmailStatus.parse(self.status))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "SendAddCreditsNudgeEmailResponse":
        data = _mapping(value, "SendAddCreditsNudgeEmailResponse")
        return cls(AddCreditsNudgeEmailStatus.parse(data["status"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"status": self.status.value}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class GetAccountParams:
    refresh_token: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "refresh_token", _ensure_bool(self.refresh_token, "refresh_token"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "GetAccountParams":
        data = {} if value is None else _mapping(value, "GetAccountParams")
        return cls(_ensure_bool(_pick(data, "refresh_token", "refreshToken", default=False), "refresh_token"))

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        _put_true(result, "refresh_token", self.refresh_token)
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        _put_true(result, "refreshToken", self.refresh_token)
        return result


@dataclass(frozen=True)
class GetAccountResponse:
    account: Account | Mapping[str, JsonValue] | None
    requires_openai_auth: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "account", _optional_account(self.account))
        object.__setattr__(self, "requires_openai_auth", _ensure_bool(self.requires_openai_auth, "requires_openai_auth"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "GetAccountResponse":
        data = _mapping(value, "GetAccountResponse")
        return cls(
            _optional_account(data.get("account")),
            _ensure_bool(_pick(data, "requires_openai_auth", "requiresOpenaiAuth"), "requires_openai_auth"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "account": None if self.account is None else self.account.to_mapping(),
            "requires_openai_auth": self.requires_openai_auth,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "account": None if self.account is None else self.account.to_camel_mapping(),
            "requiresOpenaiAuth": self.requires_openai_auth,
        }


@dataclass(frozen=True)
class AccountUpdatedNotification:
    auth_mode: AuthMode | str | None = None
    plan_type: PlanType | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "auth_mode", None if self.auth_mode is None else AuthMode.parse(self.auth_mode))
        object.__setattr__(self, "plan_type", _optional_plan_type(self.plan_type, "plan_type"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AccountUpdatedNotification":
        data = _mapping(value, "AccountUpdatedNotification")
        auth_mode = _pick(data, "auth_mode", "authMode")
        return cls(
            None if auth_mode is None else AuthMode.parse(auth_mode),
            _optional_plan_type(_pick(data, "plan_type", "planType"), "plan_type"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "auth_mode": None if self.auth_mode is None else self.auth_mode.value,
            "plan_type": None if self.plan_type is None else self.plan_type.value,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "authMode": None if self.auth_mode is None else self.auth_mode.value,
            "planType": None if self.plan_type is None else self.plan_type.value,
        }


class RateLimitReachedType(_StringEnum):
    RATE_LIMIT_REACHED = "rate_limit_reached"
    WORKSPACE_OWNER_CREDITS_DEPLETED = "workspace_owner_credits_depleted"
    WORKSPACE_MEMBER_CREDITS_DEPLETED = "workspace_member_credits_depleted"
    WORKSPACE_OWNER_USAGE_LIMIT_REACHED = "workspace_owner_usage_limit_reached"
    WORKSPACE_MEMBER_USAGE_LIMIT_REACHED = "workspace_member_usage_limit_reached"


@dataclass(frozen=True)
class RateLimitWindow:
    used_percent: int
    window_duration_mins: int | None = None
    resets_at: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "used_percent", _ensure_i32(self.used_percent, "used_percent"))
        object.__setattr__(self, "window_duration_mins", _optional_i64(self.window_duration_mins, "window_duration_mins"))
        object.__setattr__(self, "resets_at", _optional_i64(self.resets_at, "resets_at"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RateLimitWindow":
        data = _mapping(value, "RateLimitWindow")
        return cls(
            _ensure_i32(_pick(data, "used_percent", "usedPercent"), "used_percent"),
            _optional_i64(_pick(data, "window_duration_mins", "windowDurationMins"), "window_duration_mins"),
            _optional_i64(_pick(data, "resets_at", "resetsAt"), "resets_at"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "used_percent": self.used_percent,
            "window_duration_mins": self.window_duration_mins,
            "resets_at": self.resets_at,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "usedPercent": self.used_percent,
            "windowDurationMins": self.window_duration_mins,
            "resetsAt": self.resets_at,
        }


@dataclass(frozen=True)
class CreditsSnapshot:
    has_credits: bool
    unlimited: bool
    balance: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "has_credits", _ensure_bool(self.has_credits, "has_credits"))
        object.__setattr__(self, "unlimited", _ensure_bool(self.unlimited, "unlimited"))
        object.__setattr__(self, "balance", _optional_str(self.balance, "balance"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CreditsSnapshot":
        data = _mapping(value, "CreditsSnapshot")
        return cls(
            _ensure_bool(_pick(data, "has_credits", "hasCredits"), "has_credits"),
            _ensure_bool(data["unlimited"], "unlimited"),
            _optional_str(data.get("balance"), "balance"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"has_credits": self.has_credits, "unlimited": self.unlimited, "balance": self.balance}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"hasCredits": self.has_credits, "unlimited": self.unlimited, "balance": self.balance}


@dataclass(frozen=True)
class RateLimitSnapshot:
    limit_id: str | None = None
    limit_name: str | None = None
    primary: RateLimitWindow | Mapping[str, JsonValue] | None = None
    secondary: RateLimitWindow | Mapping[str, JsonValue] | None = None
    credits: CreditsSnapshot | Mapping[str, JsonValue] | None = None
    plan_type: PlanType | str | None = None
    rate_limit_reached_type: RateLimitReachedType | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "limit_id", _optional_str(self.limit_id, "limit_id"))
        object.__setattr__(self, "limit_name", _optional_str(self.limit_name, "limit_name"))
        object.__setattr__(self, "primary", _optional_rate_limit_window(self.primary))
        object.__setattr__(self, "secondary", _optional_rate_limit_window(self.secondary))
        object.__setattr__(self, "credits", _optional_credits_snapshot(self.credits))
        object.__setattr__(self, "plan_type", _optional_plan_type(self.plan_type, "plan_type"))
        object.__setattr__(
            self,
            "rate_limit_reached_type",
            None if self.rate_limit_reached_type is None else RateLimitReachedType.parse(self.rate_limit_reached_type),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RateLimitSnapshot":
        data = _mapping(value, "RateLimitSnapshot")
        return cls(
            limit_id=_optional_str(_pick(data, "limit_id", "limitId"), "limit_id"),
            limit_name=_optional_str(_pick(data, "limit_name", "limitName"), "limit_name"),
            primary=_optional_rate_limit_window(data.get("primary")),
            secondary=_optional_rate_limit_window(data.get("secondary")),
            credits=_optional_credits_snapshot(data.get("credits")),
            plan_type=_optional_plan_type(_pick(data, "plan_type", "planType"), "plan_type"),
            rate_limit_reached_type=(
                None
                if _pick(data, "rate_limit_reached_type", "rateLimitReachedType") is None
                else RateLimitReachedType.parse(_pick(data, "rate_limit_reached_type", "rateLimitReachedType"))
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "limit_id": self.limit_id,
            "limit_name": self.limit_name,
            "primary": None if self.primary is None else self.primary.to_mapping(),
            "secondary": None if self.secondary is None else self.secondary.to_mapping(),
            "credits": None if self.credits is None else self.credits.to_mapping(),
            "plan_type": None if self.plan_type is None else self.plan_type.value,
            "rate_limit_reached_type": (
                None if self.rate_limit_reached_type is None else self.rate_limit_reached_type.value
            ),
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "limitId": self.limit_id,
            "limitName": self.limit_name,
            "primary": None if self.primary is None else self.primary.to_camel_mapping(),
            "secondary": None if self.secondary is None else self.secondary.to_camel_mapping(),
            "credits": None if self.credits is None else self.credits.to_camel_mapping(),
            "planType": None if self.plan_type is None else self.plan_type.value,
            "rateLimitReachedType": (
                None if self.rate_limit_reached_type is None else self.rate_limit_reached_type.value
            ),
        }


@dataclass(frozen=True)
class GetAccountRateLimitsResponse:
    rate_limits: RateLimitSnapshot | Mapping[str, JsonValue]
    rate_limits_by_limit_id: Mapping[str, RateLimitSnapshot | Mapping[str, JsonValue]] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate_limits", _rate_limit_snapshot(self.rate_limits))
        object.__setattr__(self, "rate_limits_by_limit_id", _optional_rate_limit_map(self.rate_limits_by_limit_id))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "GetAccountRateLimitsResponse":
        data = _mapping(value, "GetAccountRateLimitsResponse")
        return cls(
            _rate_limit_snapshot(_pick(data, "rate_limits", "rateLimits")),
            _optional_rate_limit_map(_pick(data, "rate_limits_by_limit_id", "rateLimitsByLimitId")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "rate_limits": self.rate_limits.to_mapping(),
            "rate_limits_by_limit_id": (
                None
                if self.rate_limits_by_limit_id is None
                else {key: value.to_mapping() for key, value in self.rate_limits_by_limit_id.items()}
            ),
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "rateLimits": self.rate_limits.to_camel_mapping(),
            "rateLimitsByLimitId": (
                None
                if self.rate_limits_by_limit_id is None
                else {key: value.to_camel_mapping() for key, value in self.rate_limits_by_limit_id.items()}
            ),
        }


@dataclass(frozen=True)
class AccountRateLimitsUpdatedNotification:
    rate_limits: RateLimitSnapshot | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate_limits", _rate_limit_snapshot(self.rate_limits))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AccountRateLimitsUpdatedNotification":
        data = _mapping(value, "AccountRateLimitsUpdatedNotification")
        return cls(_rate_limit_snapshot(_pick(data, "rate_limits", "rateLimits")))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"rate_limits": self.rate_limits.to_mapping()}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"rateLimits": self.rate_limits.to_camel_mapping()}


@dataclass(frozen=True)
class AccountLoginCompletedNotification:
    login_id: str | None
    success: bool
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "login_id", _optional_str(self.login_id, "login_id"))
        object.__setattr__(self, "success", _ensure_bool(self.success, "success"))
        object.__setattr__(self, "error", _optional_str(self.error, "error"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AccountLoginCompletedNotification":
        data = _mapping(value, "AccountLoginCompletedNotification")
        return cls(
            _optional_str(_pick(data, "login_id", "loginId"), "login_id"),
            _ensure_bool(data["success"], "success"),
            _optional_str(data.get("error"), "error"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"login_id": self.login_id, "success": self.success, "error": self.error}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"loginId": self.login_id, "success": self.success, "error": self.error}


def _mapping(value: JsonValue, type_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping")
    return value


def _pick(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _ensure_i32(value: JsonValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < -(2**31) or value > 2**31 - 1:
        raise TypeError(f"{field_name} must be a signed 32-bit integer")
    return value


def _optional_i64(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < -(2**63) or value > 2**63 - 1:
        raise TypeError(f"{field_name} must be a signed 64-bit integer or None")
    return value


def _plan_type(value: JsonValue) -> PlanType:
    if isinstance(value, PlanType):
        return value
    return PlanType.parse(_ensure_str(value, "plan_type"))


def _optional_plan_type(value: JsonValue, field_name: str) -> PlanType | None:
    if value is None:
        return None
    if isinstance(value, PlanType):
        return value
    return PlanType.parse(_ensure_str(value, field_name))


def _optional_account(value: JsonValue) -> Account | None:
    if value is None:
        return None
    if isinstance(value, Account):
        return value
    if isinstance(value, Mapping):
        return Account.from_mapping(value)
    raise TypeError("account must be Account, mapping, or None")


def _rate_limit_snapshot(value: JsonValue) -> RateLimitSnapshot:
    if isinstance(value, RateLimitSnapshot):
        return value
    if isinstance(value, Mapping):
        return RateLimitSnapshot.from_mapping(value)
    raise TypeError("rate limit snapshot must be RateLimitSnapshot or mapping")


def _optional_rate_limit_window(value: JsonValue) -> RateLimitWindow | None:
    if value is None:
        return None
    if isinstance(value, RateLimitWindow):
        return value
    if isinstance(value, Mapping):
        return RateLimitWindow.from_mapping(value)
    raise TypeError("rate limit window must be RateLimitWindow, mapping, or None")


def _optional_credits_snapshot(value: JsonValue) -> CreditsSnapshot | None:
    if value is None:
        return None
    if isinstance(value, CreditsSnapshot):
        return value
    if isinstance(value, Mapping):
        return CreditsSnapshot.from_mapping(value)
    raise TypeError("credits snapshot must be CreditsSnapshot, mapping, or None")


def _optional_rate_limit_map(
    value: Mapping[str, RateLimitSnapshot | Mapping[str, JsonValue]] | None,
) -> dict[str, RateLimitSnapshot] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("rate_limits_by_limit_id must be a mapping")
    result: dict[str, RateLimitSnapshot] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("rate_limits_by_limit_id keys must be strings")
        result[key] = _rate_limit_snapshot(item)
    return result


def _require_field(value: JsonValue, field_name: str) -> None:
    if value is None:
        raise ValueError(f"{field_name} is required for this variant")


def _reject_fields(value: JsonValue, *field_names: str) -> None:
    for field_name in field_names:
        if getattr(value, field_name) is not None:
            raise ValueError(f"{field_name} is not valid for {getattr(value, 'type', 'this')} variant")


def _put_true(result: dict[str, JsonValue], key: str, value: bool) -> None:
    if value:
        result[key] = value


__all__ = [
    "Account",
    "AccountLoginCompletedNotification",
    "AccountRateLimitsUpdatedNotification",
    "AccountUpdatedNotification",
    "AddCreditsNudgeCreditType",
    "AddCreditsNudgeEmailStatus",
    "AuthMode",
    "CancelLoginAccountParams",
    "CancelLoginAccountResponse",
    "CancelLoginAccountStatus",
    "ChatgptAuthTokensRefreshParams",
    "ChatgptAuthTokensRefreshReason",
    "ChatgptAuthTokensRefreshResponse",
    "CreditsSnapshot",
    "GetAccountParams",
    "GetAccountRateLimitsResponse",
    "GetAccountResponse",
    "LoginAccountParams",
    "LoginAccountResponse",
    "LogoutAccountResponse",
    "RateLimitReachedType",
    "RateLimitSnapshot",
    "RateLimitWindow",
    "SendAddCreditsNudgeEmailParams",
    "SendAddCreditsNudgeEmailResponse",
]
