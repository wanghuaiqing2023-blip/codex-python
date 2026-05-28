"""Error helpers ported from ``codex/codex-rs/protocol/src/error.rs``."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Iterator

from .auth import KnownPlan, PlanType
from .exec_output import ExecToolCallOutput
from .network_policy import NetworkPolicyDecisionPayload
from .protocol import CodexErrorInfo, ErrorEvent, RateLimitReachedType, RateLimitSnapshot

ERROR_MESSAGE_UI_MAX_BYTES = 2 * 1024
UNEXPECTED_RESPONSE_BODY_MAX_BYTES = 1000
CLOUDFLARE_BLOCKED_MESSAGE = (
    "Access blocked by Cloudflare. This usually happens when connecting from a restricted region"
)

_NOW_OVERRIDE: datetime | None = None


@contextmanager
def retry_now_override(now: datetime) -> Iterator[None]:
    global _NOW_OVERRIDE
    previous = _NOW_OVERRIDE
    _NOW_OVERRIDE = now
    try:
        yield
    finally:
        _NOW_OVERRIDE = previous


def _now_for_retry() -> datetime:
    return _NOW_OVERRIDE or datetime.now(timezone.utc)


def _format_status(status: int) -> str:
    try:
        phrase = HTTPStatus(status).phrase
    except ValueError:
        return str(status)
    return f"{status} {phrase}"


def truncate_with_ellipsis(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    cut = max(max_bytes, 0)
    return encoded[:cut].decode("utf-8", errors="ignore") + "..."


def _take_bytes_at_char_boundary(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _take_last_bytes_at_char_boundary(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[-max_bytes:].decode("utf-8", errors="ignore")


def _truncate_middle_chars(text: str, max_bytes: int) -> str:
    encoded_len = len(text.encode("utf-8"))
    if encoded_len <= max_bytes:
        return text
    max_bytes = max(max_bytes, 0)
    left_budget = max_bytes // 2
    right_budget = max_bytes - left_budget
    left = _take_bytes_at_char_boundary(text, left_budget)
    right = _take_last_bytes_at_char_boundary(text, right_budget)
    removed = max(len(text) - len(left) - len(right), 0)
    return f"{left}\u2026{removed} chars truncated\u2026{right}"


def format_retry_timestamp(resets_at: datetime) -> str:
    local_reset = resets_at.astimezone()
    local_now = _now_for_retry().astimezone()
    if local_reset.date() == local_now.date():
        return _format_ampm(local_reset)
    return f"{local_reset.strftime('%b')} {local_reset.day}{day_suffix(local_reset.day)}, {local_reset.year} {_format_ampm(local_reset)}"


def _format_ampm(value: datetime) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def day_suffix(day: int) -> str:
    if 11 <= day <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def retry_suffix(resets_at: datetime | None) -> str:
    if resets_at is None:
        return " Try again later."
    return f" Try again at {format_retry_timestamp(resets_at)}."


def retry_suffix_after_or(resets_at: datetime | None) -> str:
    if resets_at is None:
        return " or try again later."
    return f" or try again at {format_retry_timestamp(resets_at)}."


@dataclass(frozen=True)
class UnexpectedResponseError(Exception):
    status: int
    body: str
    url: str | None = None
    cf_ray: str | None = None
    request_id: str | None = None
    identity_authorization_error: str | None = None
    identity_error_code: str | None = None

    def display_body(self) -> str:
        message = self.extract_error_message()
        if message is not None:
            return message
        trimmed = self.body.strip()
        if not trimmed:
            return "Unknown error"
        return truncate_with_ellipsis(trimmed, UNEXPECTED_RESPONSE_BODY_MAX_BYTES)

    def extract_error_message(self) -> str | None:
        try:
            payload = json.loads(self.body)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        if not isinstance(error, dict):
            return None
        message = error.get("message")
        if not isinstance(message, str):
            return None
        message = message.strip()
        return message or None

    def friendly_message(self) -> str | None:
        if self.status != 403:
            return None
        body = self.body.lower()
        if "cloudflare" not in body or "blocked" not in body:
            return None
        return self._append_details(f"{CLOUDFLARE_BLOCKED_MESSAGE} (status {_format_status(self.status)})")

    def _append_details(self, message: str) -> str:
        if self.url is not None:
            message += f", url: {self.url}"
        if self.cf_ray is not None:
            message += f", cf-ray: {self.cf_ray}"
        if self.request_id is not None:
            message += f", request id: {self.request_id}"
        if self.identity_authorization_error is not None:
            message += f", auth error: {self.identity_authorization_error}"
        if self.identity_error_code is not None:
            message += f", auth error code: {self.identity_error_code}"
        return message

    def __str__(self) -> str:
        friendly = self.friendly_message()
        if friendly is not None:
            return friendly
        return self._append_details(f"unexpected status {_format_status(self.status)}: {self.display_body()}")


@dataclass(frozen=True)
class RetryLimitReachedError(Exception):
    status: int
    request_id: str | None = None

    def __str__(self) -> str:
        message = f"exceeded retry limit, last status: {_format_status(self.status)}"
        if self.request_id is not None:
            message += f", request id: {self.request_id}"
        return message


@dataclass(frozen=True)
class ConnectionFailedError(Exception):
    source: str
    status_code: int | None = None

    def __str__(self) -> str:
        return f"Connection failed: {self.source}"


@dataclass(frozen=True)
class ResponseStreamFailed(Exception):
    source: str
    request_id: str | None = None
    status_code: int | None = None

    def __str__(self) -> str:
        message = f"Error while reading the server response: {self.source}"
        if self.request_id is not None:
            message += f", request id: {self.request_id}"
        return message


@dataclass(frozen=True)
class UsageLimitReachedError(Exception):
    plan_type: PlanType | None = None
    resets_at: datetime | None = None
    rate_limits: RateLimitSnapshot | None = None
    promo_message: str | None = None
    rate_limit_reached_type: RateLimitReachedType | None = None

    def __str__(self) -> str:
        limit_name = None
        if self.rate_limits is not None and self.rate_limits.limit_name is not None:
            limit_name = self.rate_limits.limit_name.strip()
        if limit_name and limit_name.lower() != "codex":
            return (
                f"You've hit your usage limit for {limit_name}. Switch to another model now,"
                f"{retry_suffix_after_or(self.resets_at)}"
            )

        if self.rate_limit_reached_type is RateLimitReachedType.WORKSPACE_OWNER_CREDITS_DEPLETED:
            return "Your workspace is out of credits. Add credits to continue."
        if self.rate_limit_reached_type is RateLimitReachedType.WORKSPACE_MEMBER_CREDITS_DEPLETED:
            return "Your workspace is out of credits. Ask your workspace owner to refill in order to continue."
        if self.rate_limit_reached_type is RateLimitReachedType.WORKSPACE_OWNER_USAGE_LIMIT_REACHED:
            return "You hit your spend cap set in your workspace. Increase your spend cap to continue."
        if self.rate_limit_reached_type is RateLimitReachedType.WORKSPACE_MEMBER_USAGE_LIMIT_REACHED:
            return "You hit your spend cap set by the owner of your workspace. Ask an owner to increase your spend cap to continue."

        if self.promo_message is not None:
            return f"You've hit your usage limit. {self.promo_message},{retry_suffix_after_or(self.resets_at)}"

        if self.plan_type is not None and self.plan_type.known is KnownPlan.PLUS:
            return (
                "You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), "
                "visit https://chatgpt.com/codex/settings/usage to purchase more credits"
                f"{retry_suffix_after_or(self.resets_at)}"
            )
        if self.plan_type is not None and self.plan_type.known in {
            KnownPlan.TEAM,
            KnownPlan.SELF_SERVE_BUSINESS_USAGE_BASED,
            KnownPlan.BUSINESS,
            KnownPlan.ENTERPRISE_CBP_USAGE_BASED,
        }:
            return (
                "You've hit your usage limit. To get more access now, send a request to your admin"
                f"{retry_suffix_after_or(self.resets_at)}"
            )
        if self.plan_type is not None and self.plan_type.known in {KnownPlan.FREE, KnownPlan.GO}:
            return (
                "You've hit your usage limit. Upgrade to Plus to continue using Codex "
                f"(https://chatgpt.com/explore/plus),{retry_suffix_after_or(self.resets_at)}"
            )
        if self.plan_type is not None and self.plan_type.known in {KnownPlan.PRO, KnownPlan.PRO_LITE}:
            return (
                "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
                f"to purchase more credits{retry_suffix_after_or(self.resets_at)}"
            )
        return f"You've hit your usage limit.{retry_suffix(self.resets_at)}"


class SandboxErr(Exception):
    pass


@dataclass(frozen=True)
class SandboxDenied(SandboxErr):
    output: ExecToolCallOutput
    network_policy_decision: NetworkPolicyDecisionPayload | None = None

    def __str__(self) -> str:
        return (
            "sandbox denied exec error, exit code: "
            f"{self.output.exit_code}, stdout: {self.output.stdout.text}, stderr: {self.output.stderr.text}"
        )


@dataclass(frozen=True)
class SandboxTimeout(SandboxErr):
    output: ExecToolCallOutput

    def __str__(self) -> str:
        return "command timed out"


@dataclass(frozen=True)
class SandboxSignal(SandboxErr):
    signal: int

    def __str__(self) -> str:
        return "command was killed by a signal"


class SandboxLandlockRestrict(SandboxErr):
    def __str__(self) -> str:
        return "Landlock was not able to fully enforce all sandbox rules"


@dataclass(frozen=True)
class EnvVarError(Exception):
    var: str
    instructions: str | None = None

    def __str__(self) -> str:
        message = f"Missing environment variable: `{self.var}`."
        if self.instructions is not None:
            message += f" {self.instructions}"
        return message


@dataclass(frozen=True)
class CodexErr(Exception):
    kind: str
    payload: object = None
    message: str | None = None
    status_code: int | None = None

    @classmethod
    def simple(cls, kind: str) -> "CodexErr":
        return cls(kind)

    @classmethod
    def stream(cls, message: str, retry_after: object = None) -> "CodexErr":
        return cls("stream", payload=retry_after, message=message)

    @classmethod
    def thread_not_found(cls, thread_id: str) -> "CodexErr":
        return cls("thread_not_found", message=thread_id)

    @classmethod
    def agent_limit_reached(cls, max_threads: int) -> "CodexErr":
        return cls("agent_limit_reached", payload=max_threads)

    @classmethod
    def unexpected_status(cls, error: UnexpectedResponseError) -> "CodexErr":
        return cls("unexpected_status", payload=error)

    @classmethod
    def invalid_request(cls, message: str) -> "CodexErr":
        return cls("invalid_request", message=message)

    @classmethod
    def usage_limit_reached(cls, error: UsageLimitReachedError) -> "CodexErr":
        return cls("usage_limit_reached", payload=error)

    @classmethod
    def cyber_policy(cls, message: str) -> "CodexErr":
        return cls("cyber_policy", message=message)

    @classmethod
    def response_stream_failed(cls, error: ResponseStreamFailed) -> "CodexErr":
        return cls("response_stream_failed", payload=error)

    @classmethod
    def connection_failed(cls, error: ConnectionFailedError) -> "CodexErr":
        return cls("connection_failed", payload=error)

    @classmethod
    def retry_limit(cls, error: RetryLimitReachedError) -> "CodexErr":
        return cls("retry_limit", payload=error)

    @classmethod
    def sandbox(cls, error: SandboxErr) -> "CodexErr":
        return cls("sandbox", payload=error)

    @classmethod
    def unsupported_operation(cls, message: str) -> "CodexErr":
        return cls("unsupported_operation", message=message)

    @classmethod
    def fatal(cls, message: str) -> "CodexErr":
        return cls("fatal", message=message)

    @classmethod
    def env_var(cls, error: EnvVarError) -> "CodexErr":
        return cls("env_var", payload=error)

    def is_retryable(self) -> bool:
        return self.kind in {
            "stream",
            "timeout",
            "request_timeout",
            "unexpected_status",
            "response_stream_failed",
            "connection_failed",
            "internal_server_error",
            "internal_agent_died",
            "io",
            "json",
            "tokio_join",
        }

    def to_codex_protocol_error(self) -> CodexErrorInfo:
        if self.kind == "context_window_exceeded":
            return CodexErrorInfo.context_window_exceeded()
        if self.kind in {"usage_limit_reached", "quota_exceeded", "usage_not_included"}:
            return CodexErrorInfo.usage_limit_exceeded()
        if self.kind == "server_overloaded":
            return CodexErrorInfo.server_overloaded()
        if self.kind == "cyber_policy":
            return CodexErrorInfo.cyber_policy()
        if self.kind == "retry_limit":
            return CodexErrorInfo.response_too_many_failed_attempts(self.http_status_code_value())
        if self.kind == "connection_failed":
            return CodexErrorInfo.http_connection_failed(self.http_status_code_value())
        if self.kind == "response_stream_failed":
            return CodexErrorInfo.response_stream_connection_failed(self.http_status_code_value())
        if self.kind == "refresh_token_failed":
            return CodexErrorInfo.unauthorized()
        if self.kind in {"session_configured_not_first_event", "internal_server_error", "internal_agent_died"}:
            return CodexErrorInfo.internal_server_error()
        if self.kind in {"unsupported_operation", "thread_not_found", "agent_limit_reached"}:
            return CodexErrorInfo.bad_request()
        if self.kind == "sandbox":
            return CodexErrorInfo.sandbox_error()
        return CodexErrorInfo.other()

    def to_error_event(self, message_prefix: str | None = None) -> ErrorEvent:
        error_message = str(self)
        message = f"{message_prefix}: {error_message}" if message_prefix is not None else error_message
        return ErrorEvent(message=message, codex_error_info=self.to_codex_protocol_error())

    def http_status_code_value(self) -> int | None:
        if self.kind == "retry_limit" and isinstance(self.payload, RetryLimitReachedError):
            return self.payload.status
        if self.kind == "unexpected_status" and isinstance(self.payload, UnexpectedResponseError):
            return self.payload.status
        if self.kind == "connection_failed" and isinstance(self.payload, ConnectionFailedError):
            return self.payload.status_code
        if self.kind == "response_stream_failed" and isinstance(self.payload, ResponseStreamFailed):
            return self.payload.status_code
        return self.status_code

    def __str__(self) -> str:
        if self.kind == "turn_aborted":
            return "turn aborted. Something went wrong? Hit `/feedback` to report the issue."
        if self.kind == "stream":
            return f"stream disconnected before completion: {self.message or ''}"
        if self.kind == "context_window_exceeded":
            return (
                "Codex ran out of room in the model's context window. Start a new thread or clear earlier history "
                "before retrying."
            )
        if self.kind == "thread_not_found":
            return f"no thread with id: {self.message}"
        if self.kind == "agent_limit_reached":
            return "agent thread limit reached"
        if self.kind == "session_configured_not_first_event":
            return "session configured event was not the first event in the stream"
        if self.kind == "timeout":
            return "timeout waiting for child process to exit"
        if self.kind == "request_timeout":
            return "request timed out"
        if self.kind == "spawn":
            return "spawn failed: child stdout/stderr not captured"
        if self.kind == "interrupted":
            return "interrupted (Ctrl-C). Something went wrong? Hit `/feedback` to report the issue."
        if self.kind == "invalid_request":
            return self.message or ""
        if self.kind == "invalid_image_request":
            return "Image poisoning"
        if self.kind == "server_overloaded":
            return "Selected model is at capacity. Please try a different model."
        if self.kind == "cyber_policy":
            return self.message or ""
        if self.kind == "quota_exceeded":
            return "Quota exceeded. Check your plan and billing details."
        if self.kind == "usage_not_included":
            return "To use Codex with your ChatGPT plan, upgrade to Plus: https://chatgpt.com/explore/plus."
        if self.kind == "internal_server_error":
            return "We're currently experiencing high demand, which may cause temporary errors."
        if self.kind == "internal_agent_died":
            return "internal error; agent loop died unexpectedly"
        if self.kind == "sandbox":
            return f"sandbox error: {self.payload}"
        if self.kind == "landlock_sandbox_executable_not_provided":
            return "codex-linux-sandbox was required but not provided"
        if self.kind == "unsupported_operation":
            return f"unsupported operation: {self.message or ''}"
        if self.kind == "fatal":
            return f"Fatal error: {self.message or ''}"
        if self.payload is not None:
            return str(self.payload)
        return self.message or self.kind


def get_error_message_ui(error: CodexErr) -> str:
    if error.kind == "sandbox" and isinstance(error.payload, SandboxDenied):
        output = error.payload.output
        aggregated = output.aggregated_output.text.strip()
        if aggregated:
            message = output.aggregated_output.text
        else:
            stderr = output.stderr.text.strip()
            stdout = output.stdout.text.strip()
            if stderr and stdout:
                message = f"{stderr}\n{stdout}"
            elif stderr:
                message = output.stderr.text
            elif stdout:
                message = output.stdout.text
            else:
                message = f"command failed inside sandbox with exit code {output.exit_code}"
    elif error.kind == "sandbox" and isinstance(error.payload, SandboxTimeout):
        duration_ms = int(error.payload.output.duration.total_seconds() * 1000)
        message = f"error: command timed out after {duration_ms} ms"
    else:
        message = str(error)
    return _truncate_middle_chars(message, ERROR_MESSAGE_UI_MAX_BYTES)


__all__ = [
    "CLOUDFLARE_BLOCKED_MESSAGE",
    "CodexErr",
    "ConnectionFailedError",
    "ERROR_MESSAGE_UI_MAX_BYTES",
    "EnvVarError",
    "ResponseStreamFailed",
    "RetryLimitReachedError",
    "SandboxDenied",
    "SandboxErr",
    "SandboxLandlockRestrict",
    "SandboxSignal",
    "SandboxTimeout",
    "UNEXPECTED_RESPONSE_BODY_MAX_BYTES",
    "UnexpectedResponseError",
    "UsageLimitReachedError",
    "day_suffix",
    "format_retry_timestamp",
    "get_error_message_ui",
    "retry_now_override",
    "retry_suffix",
    "retry_suffix_after_or",
    "truncate_with_ellipsis",
]
