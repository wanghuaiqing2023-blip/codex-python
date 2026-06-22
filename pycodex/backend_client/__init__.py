"""Dependency-light port of Rust ``codex-backend-client``.

Rust source:
- ``codex/codex-rs/backend-client/src/lib.rs``
- ``codex/codex-rs/backend-client/src/client.rs``
- ``codex/codex-rs/backend-client/src/types.rs``
"""

from __future__ import annotations

import json
import ssl
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pycodex.app_server_protocol.account import CreditsSnapshot
from pycodex.app_server_protocol.account import RateLimitReachedType
from pycodex.app_server_protocol.account import RateLimitSnapshot
from pycodex.app_server_protocol.account import RateLimitWindow
from pycodex.codex_backend_openapi_models.models import AdditionalRateLimitDetails
from pycodex.codex_backend_openapi_models.models import ConfigFileResponse
from pycodex.codex_backend_openapi_models.models import CreditStatusDetails
from pycodex.codex_backend_openapi_models.models import PaginatedListTaskListItem
from pycodex.codex_backend_openapi_models.models import PlanType as BackendPlanType
from pycodex.codex_backend_openapi_models.models import RateLimitReachedKind
from pycodex.codex_backend_openapi_models.models import RateLimitReachedType as BackendRateLimitReachedType
from pycodex.codex_backend_openapi_models.models import RateLimitStatusDetails
from pycodex.codex_backend_openapi_models.models import RateLimitStatusPayload
from pycodex.codex_backend_openapi_models.models import RateLimitWindowSnapshot
from pycodex.codex_backend_openapi_models.models import UNSET
from pycodex.codex_backend_openapi_models.models import Unset
from pycodex.codex_client.chatgpt_cloudflare_cookies import SHARED_CHATGPT_CLOUDFLARE_COOKIE_STORE
from pycodex.codex_client.custom_ca import ProcessEnv
from pycodex.codex_client.custom_ca import configured_ca_bundle
from pycodex.protocol.account import PlanType

JsonValue = Any
Transport = Callable[["BackendRequest"], "BackendResponse"]


class AddCreditsNudgeCreditType(str, Enum):
    CREDITS = "credits"
    USAGE_LIMIT = "usage_limit"


class PathStyle(str, Enum):
    CODEX_API = "codex_api"
    CHATGPT_API = "chatgpt_api"

    @classmethod
    def from_base_url(cls, base_url: str) -> "PathStyle":
        if "/backend-api" in base_url:
            return cls.CHATGPT_API
        return cls.CODEX_API


@dataclass(frozen=True)
class RequestError(Exception):
    method: str
    url: str
    status: int
    content_type: str = ""
    body: str = ""

    def __str__(self) -> str:
        return f"{self.method} {self.url} failed: {self.status}; content-type={self.content_type}; body={self.body}"

    def is_unauthorized(self) -> bool:
        return self.status == 401


@dataclass(frozen=True)
class BackendRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None = None


@dataclass(frozen=True)
class BackendResponse:
    status: int
    body: str
    content_type: str = ""
    set_cookie_headers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Client:
    base_url: str
    path_style: PathStyle = PathStyle.CODEX_API
    user_agent: str | None = None
    chatgpt_account_id: str | None = None
    chatgpt_account_is_fedramp: bool = False
    transport: Transport | None = None
    auth_provider: Any | None = None
    cookie_store: Any | None = None

    @classmethod
    def new(cls, base_url: str) -> "Client":
        normalized = _normalize_base_url(base_url)
        return cls(normalized, PathStyle.from_base_url(normalized))

    def with_user_agent(self, user_agent: str) -> "Client":
        return Client(
            self.base_url,
            self.path_style,
            user_agent,
            self.chatgpt_account_id,
            self.chatgpt_account_is_fedramp,
            self.transport,
            self.auth_provider,
            self.cookie_store,
        )

    def with_chatgpt_account_id(self, account_id: str) -> "Client":
        return Client(
            self.base_url,
            self.path_style,
            self.user_agent,
            account_id,
            self.chatgpt_account_is_fedramp,
            self.transport,
            self.auth_provider,
            self.cookie_store,
        )

    def with_fedramp_routing_header(self) -> "Client":
        return Client(
            self.base_url,
            self.path_style,
            self.user_agent,
            self.chatgpt_account_id,
            True,
            self.transport,
            self.auth_provider,
            self.cookie_store,
        )

    def with_path_style(self, style: PathStyle) -> "Client":
        return Client(
            self.base_url,
            style,
            self.user_agent,
            self.chatgpt_account_id,
            self.chatgpt_account_is_fedramp,
            self.transport,
            self.auth_provider,
            self.cookie_store,
        )

    def with_transport(self, transport: Transport) -> "Client":
        return Client(
            self.base_url,
            self.path_style,
            self.user_agent,
            self.chatgpt_account_id,
            self.chatgpt_account_is_fedramp,
            transport,
            self.auth_provider,
            self.cookie_store,
        )

    def with_auth_provider(self, auth_provider: Any) -> "Client":
        return Client(
            self.base_url,
            self.path_style,
            self.user_agent,
            self.chatgpt_account_id,
            self.chatgpt_account_is_fedramp,
            self.transport,
            auth_provider,
            self.cookie_store,
        )

    def with_cookie_store(self, cookie_store: Any | None) -> "Client":
        return Client(
            self.base_url,
            self.path_style,
            self.user_agent,
            self.chatgpt_account_id,
            self.chatgpt_account_is_fedramp,
            self.transport,
            self.auth_provider,
            cookie_store,
        )

    def headers(self) -> dict[str, str]:
        headers = {"user-agent": self.user_agent or "codex-cli"}
        _add_auth_headers(self.auth_provider, headers)
        if self.chatgpt_account_id is not None:
            _set_header_case_insensitive(headers, "ChatGPT-Account-Id", self.chatgpt_account_id)
        if self.chatgpt_account_is_fedramp:
            _set_header_case_insensitive(headers, "X-OpenAI-Fedramp", "true")
        return headers

    def send_add_credits_nudge_email_url(self) -> str:
        if self.path_style is PathStyle.CODEX_API:
            return f"{self.base_url}/api/codex/accounts/send_add_credits_nudge_email"
        return f"{self.base_url}/wham/accounts/send_add_credits_nudge_email"

    def rate_limits_url(self) -> str:
        if self.path_style is PathStyle.CODEX_API:
            return f"{self.base_url}/api/codex/usage"
        return f"{self.base_url}/wham/usage"

    def list_tasks_url(
        self,
        *,
        limit: int | None = None,
        task_filter: str | None = None,
        environment_id: str | None = None,
        cursor: str | None = None,
    ) -> str:
        path = "api/codex/tasks/list" if self.path_style is PathStyle.CODEX_API else "wham/tasks/list"
        params: list[tuple[str, str | int]] = []
        if limit is not None:
            params.append(("limit", limit))
        if task_filter is not None:
            params.append(("task_filter", task_filter))
        if cursor is not None:
            params.append(("cursor", cursor))
        if environment_id is not None:
            params.append(("environment_id", environment_id))
        query = urlencode(params)
        url = f"{self.base_url}/{path}"
        return f"{url}?{query}" if query else url

    def task_details_url(self, task_id: str) -> str:
        path = "api/codex/tasks" if self.path_style is PathStyle.CODEX_API else "wham/tasks"
        return f"{self.base_url}/{path}/{task_id}"

    def sibling_turns_url(self, task_id: str, turn_id: str) -> str:
        path = "api/codex/tasks" if self.path_style is PathStyle.CODEX_API else "wham/tasks"
        return f"{self.base_url}/{path}/{task_id}/turns/{turn_id}/sibling_turns"

    def config_requirements_file_url(self) -> str:
        if self.path_style is PathStyle.CODEX_API:
            return f"{self.base_url}/api/codex/config/requirements"
        return f"{self.base_url}/wham/config/requirements"

    def create_task_url(self) -> str:
        if self.path_style is PathStyle.CODEX_API:
            return f"{self.base_url}/api/codex/tasks"
        return f"{self.base_url}/wham/tasks"

    def create_task_id_from_response(self, body: str, *, content_type: str = "") -> str:
        try:
            value = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Decode error for {self.create_task_url()}: {exc}; content-type={content_type}; body={body}"
            ) from exc
        if isinstance(value, Mapping):
            task = value.get("task")
            if isinstance(task, Mapping):
                task_id = task.get("id")
                if isinstance(task_id, str):
                    return task_id
            top_level_id = value.get("id")
            if isinstance(top_level_id, str):
                return top_level_id
        raise ValueError(
            f"POST {self.create_task_url()} succeeded but no task id found; content-type={content_type}; body={body}"
        )

    @staticmethod
    def send_add_credits_nudge_email_body(credit_type: AddCreditsNudgeCreditType | str) -> dict[str, str]:
        kind = credit_type if isinstance(credit_type, AddCreditsNudgeCreditType) else AddCreditsNudgeCreditType(credit_type)
        return {"credit_type": kind.value}

    def get_rate_limits(self) -> RateLimitSnapshot:
        return self.preferred_rate_limit_snapshot(self.get_rate_limits_many())

    def get_rate_limits_many(self) -> list[RateLimitSnapshot]:
        body, content_type = self._exec_request("GET", self.rate_limits_url())
        payload = self._decode_json_model(self.rate_limits_url(), content_type, body, RateLimitStatusPayload)
        return self.rate_limit_snapshots_from_payload(payload)

    def send_add_credits_nudge_email(self, credit_type: AddCreditsNudgeCreditType | str) -> None:
        url = self.send_add_credits_nudge_email_url()
        self._exec_request_detailed(
            "POST",
            url,
            json_body=self.send_add_credits_nudge_email_body(credit_type),
        )

    def list_tasks(
        self,
        *,
        limit: int | None = None,
        task_filter: str | None = None,
        environment_id: str | None = None,
        cursor: str | None = None,
    ) -> PaginatedListTaskListItem:
        url = self.list_tasks_url(limit=limit, task_filter=task_filter, environment_id=environment_id, cursor=cursor)
        body, content_type = self._exec_request("GET", url)
        return self._decode_json_model(url, content_type, body, PaginatedListTaskListItem)

    def get_task_details(self, task_id: str) -> CodeTaskDetailsResponse:
        parsed, _body, _content_type = self.get_task_details_with_body(task_id)
        return parsed

    def get_task_details_with_body(self, task_id: str) -> tuple[CodeTaskDetailsResponse, str, str]:
        url = self.task_details_url(task_id)
        body, content_type = self._exec_request("GET", url)
        return CodeTaskDetailsResponse.from_json(body), body, content_type

    def list_sibling_turns(self, task_id: str, turn_id: str) -> TurnAttemptsSiblingTurnsResponse:
        url = self.sibling_turns_url(task_id, turn_id)
        body, content_type = self._exec_request("GET", url)
        return self._decode_json_model(url, content_type, body, TurnAttemptsSiblingTurnsResponse)

    def get_config_requirements_file(self) -> ConfigFileResponse:
        url = self.config_requirements_file_url()
        body, content_type = self._exec_request_detailed("GET", url)
        return self._decode_json_model(url, content_type, body, ConfigFileResponse)

    def create_task(self, request_body: Mapping[str, JsonValue]) -> str:
        url = self.create_task_url()
        body, content_type = self._exec_request("POST", url, json_body=dict(request_body))
        return self.create_task_id_from_response(body, content_type=content_type)

    def _exec_request(
        self,
        method: str,
        url: str,
        *,
        json_body: Mapping[str, JsonValue] | None = None,
    ) -> tuple[str, str]:
        response = self._send(method, url, json_body=json_body)
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(
                f"{method} {url} failed: {response.status}; content-type={response.content_type}; body={response.body}"
            )
        return response.body, response.content_type

    def _exec_request_detailed(
        self,
        method: str,
        url: str,
        *,
        json_body: Mapping[str, JsonValue] | None = None,
    ) -> tuple[str, str]:
        response = self._send(method, url, json_body=json_body)
        if response.status < 200 or response.status >= 300:
            raise RequestError(method, url, response.status, response.content_type, response.body)
        return response.body, response.content_type

    def _send(
        self,
        method: str,
        url: str,
        *,
        json_body: Mapping[str, JsonValue] | None = None,
    ) -> BackendResponse:
        headers = self.headers()
        body_bytes: bytes | None = None
        if json_body is not None:
            headers = dict(headers)
            headers["content-type"] = "application/json"
            body_bytes = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
        request = BackendRequest(method, url, headers, body_bytes)
        cookie_store = self.cookie_store or SHARED_CHATGPT_CLOUDFLARE_COOKIE_STORE
        cookie_header = _cookies_for_request(cookie_store, url)
        if cookie_header:
            headers = dict(headers)
            _set_header_case_insensitive(headers, "Cookie", cookie_header)
            request = BackendRequest(method, url, headers, body_bytes)
        if self.transport is not None:
            response = self.transport(request)
        else:
            response = _stdlib_transport(request)
        _store_response_cookies(cookie_store, response, url)
        return response

    @staticmethod
    def _decode_json_model(url: str, content_type: str, body: str, model: type[Any]) -> Any:
        try:
            value = json.loads(body)
            if hasattr(model, "from_mapping"):
                if not isinstance(value, Mapping):
                    raise TypeError("expected JSON object")
                return model.from_mapping(value)
            return value
        except Exception as exc:
            raise ValueError(f"Decode error for {url}: {exc}; content-type={content_type}; body={body}") from exc

    @staticmethod
    def rate_limit_snapshots_from_payload(payload: RateLimitStatusPayload | Mapping[str, JsonValue]) -> list[RateLimitSnapshot]:
        if isinstance(payload, Mapping):
            payload = RateLimitStatusPayload.from_mapping(payload)
        plan_type = _map_plan_type(payload.plan_type)
        reached_type = _map_rate_limit_reached_from_payload(payload.rate_limit_reached_type)
        snapshots = [
            _make_rate_limit_snapshot(
                limit_id="codex",
                limit_name=None,
                rate_limit=_unwrap_double_option(payload.rate_limit),
                credits=_unwrap_double_option(payload.credits),
                plan_type=plan_type,
                rate_limit_reached_type=reached_type,
            )
        ]
        additional = _unwrap_double_option(payload.additional_rate_limits)
        if additional is not None:
            for details in additional:
                item = _additional_rate_limit_details(details)
                snapshots.append(
                    _make_rate_limit_snapshot(
                        limit_id=item.metered_feature,
                        limit_name=item.limit_name,
                        rate_limit=_unwrap_double_option(item.rate_limit),
                        credits=None,
                        plan_type=plan_type,
                        rate_limit_reached_type=None,
                    )
                )
        return snapshots

    @staticmethod
    def preferred_rate_limit_snapshot(snapshots: Iterable[RateLimitSnapshot]) -> RateLimitSnapshot:
        values = list(snapshots)
        for snapshot in values:
            if snapshot.limit_id == "codex":
                return snapshot
        if not values:
            raise IndexError("no rate limit snapshots")
        return values[0]


@dataclass(frozen=True)
class ContentFragment:
    value: JsonValue

    def text(self) -> str | None:
        if isinstance(self.value, str):
            return None if self.value.strip() == "" else self.value
        if isinstance(self.value, Mapping):
            content_type = self.value.get("content_type")
            if isinstance(content_type, str) and content_type.lower() == "text":
                text = self.value.get("text")
                if isinstance(text, str) and text != "":
                    return text
        return None


@dataclass(frozen=True)
class TurnItem:
    kind: str = ""
    role: str | None = None
    content: tuple[ContentFragment, ...] = ()
    diff: str | None = None
    output_diff: Mapping[str, JsonValue] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TurnItem":
        raw_content = value.get("content") or []
        if not isinstance(raw_content, list):
            raw_content = []
        output_diff = value.get("output_diff")
        return cls(
            kind=_optional_str(value.get("type")) or "",
            role=_optional_str(value.get("role")),
            content=tuple(ContentFragment(item) for item in raw_content),
            diff=_optional_str(value.get("diff")),
            output_diff=output_diff if isinstance(output_diff, Mapping) else None,
        )

    def text_values(self) -> list[str]:
        return [text for fragment in self.content if (text := fragment.text()) is not None]

    def diff_text(self) -> str | None:
        if self.kind == "output_diff" and self.diff:
            return self.diff
        if self.kind == "pr" and self.output_diff is not None:
            diff = self.output_diff.get("diff")
            if isinstance(diff, str) and diff:
                return diff
        return None


@dataclass(frozen=True)
class TurnError:
    code: str | None = None
    message: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TurnError":
        return cls(_optional_str(value.get("code")), _optional_str(value.get("message")))

    def summary(self) -> str | None:
        code = self.code or ""
        message = self.message or ""
        if not code and not message:
            return None
        if code and not message:
            return code
        if message and not code:
            return message
        return f"{code}: {message}"


@dataclass(frozen=True)
class WorklogMessage:
    author_role: str | None = None
    parts: tuple[ContentFragment, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "WorklogMessage":
        author = value.get("author")
        content = value.get("content")
        parts: list[JsonValue] = []
        if isinstance(content, Mapping) and isinstance(content.get("parts"), list):
            parts = list(content["parts"])
        role = author.get("role") if isinstance(author, Mapping) else None
        return cls(_optional_str(role), tuple(ContentFragment(part) for part in parts))

    def is_assistant(self) -> bool:
        return self.author_role is not None and self.author_role.lower() == "assistant"

    def text_values(self) -> list[str]:
        return [text for fragment in self.parts if (text := fragment.text()) is not None]


@dataclass(frozen=True)
class Worklog:
    messages: tuple[WorklogMessage, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "Worklog":
        messages = value.get("messages") or []
        if not isinstance(messages, list):
            messages = []
        return cls(tuple(WorklogMessage.from_mapping(item) for item in messages if isinstance(item, Mapping)))


@dataclass(frozen=True)
class Turn:
    id: str | None = None
    attempt_placement: int | None = None
    turn_status: str | None = None
    sibling_turn_ids: tuple[str, ...] = ()
    input_items: tuple[TurnItem, ...] = ()
    output_items: tuple[TurnItem, ...] = ()
    worklog: Worklog | None = None
    error: TurnError | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "Turn":
        return cls(
            id=_optional_str(value.get("id")),
            attempt_placement=_optional_int(value.get("attempt_placement")),
            turn_status=_optional_str(value.get("turn_status")),
            sibling_turn_ids=tuple(item for item in _list_or_empty(value.get("sibling_turn_ids")) if isinstance(item, str)),
            input_items=tuple(TurnItem.from_mapping(item) for item in _list_or_empty(value.get("input_items")) if isinstance(item, Mapping)),
            output_items=tuple(TurnItem.from_mapping(item) for item in _list_or_empty(value.get("output_items")) if isinstance(item, Mapping)),
            worklog=Worklog.from_mapping(value["worklog"]) if isinstance(value.get("worklog"), Mapping) else None,
            error=TurnError.from_mapping(value["error"]) if isinstance(value.get("error"), Mapping) else None,
        )

    def unified_diff(self) -> str | None:
        for item in self.output_items:
            if diff := item.diff_text():
                return diff
        return None

    def message_texts(self) -> list[str]:
        values: list[str] = []
        for item in self.output_items:
            if item.kind == "message":
                values.extend(item.text_values())
        if self.worklog is not None:
            for message in self.worklog.messages:
                if message.is_assistant():
                    values.extend(message.text_values())
        return values

    def user_prompt(self) -> str | None:
        parts: list[str] = []
        for item in self.input_items:
            if item.kind == "message" and (item.role is None or item.role.lower() == "user"):
                parts.extend(item.text_values())
        if not parts:
            return None
        return "\n\n".join(parts)

    def error_summary(self) -> str | None:
        return None if self.error is None else self.error.summary()


@dataclass(frozen=True)
class CodeTaskDetailsResponse:
    current_user_turn: Turn | None = None
    current_assistant_turn: Turn | None = None
    current_diff_task_turn: Turn | None = None

    @classmethod
    def from_json(cls, text: str) -> "CodeTaskDetailsResponse":
        return cls.from_mapping(json.loads(text))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CodeTaskDetailsResponse":
        return cls(
            current_user_turn=_turn_or_none(value.get("current_user_turn")),
            current_assistant_turn=_turn_or_none(value.get("current_assistant_turn")),
            current_diff_task_turn=_turn_or_none(value.get("current_diff_task_turn")),
        )

    def unified_diff(self) -> str | None:
        for turn in (self.current_diff_task_turn, self.current_assistant_turn):
            if turn is not None and (diff := turn.unified_diff()):
                return diff
        return None

    def assistant_text_messages(self) -> list[str]:
        values: list[str] = []
        for turn in (self.current_diff_task_turn, self.current_assistant_turn):
            if turn is not None:
                values.extend(turn.message_texts())
        return values

    def user_text_prompt(self) -> str | None:
        return None if self.current_user_turn is None else self.current_user_turn.user_prompt()

    def assistant_error_message(self) -> str | None:
        return None if self.current_assistant_turn is None else self.current_assistant_turn.error_summary()


@dataclass(frozen=True)
class TurnAttemptsSiblingTurnsResponse:
    sibling_turns: tuple[Mapping[str, JsonValue], ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TurnAttemptsSiblingTurnsResponse":
        raw = value.get("sibling_turns") or []
        if not isinstance(raw, list):
            raw = []
        return cls(tuple(item for item in raw if isinstance(item, Mapping)))


def _normalize_base_url(base_url: str) -> str:
    normalized = str(base_url)
    while normalized.endswith("/"):
        normalized = normalized[:-1]
    if (
        normalized.startswith("https://chatgpt.com") or normalized.startswith("https://chat.openai.com")
    ) and "/backend-api" not in normalized:
        normalized = f"{normalized}/backend-api"
    return normalized


def _stdlib_transport(request: BackendRequest) -> BackendResponse:
    urllib_request = Request(
        request.url,
        data=request.body,
        headers=dict(request.headers),
        method=request.method,
    )
    context = _ssl_context_for_request(request.url)
    try:
        with urlopen(urllib_request, context=context) as response:  # noqa: S310 - mirrors backend client HTTP transport.
            body = response.read().decode("utf-8", errors="replace")
            content_type = response.headers.get("content-type", "")
            return BackendResponse(response.status, body, content_type, tuple(response.headers.get_all("set-cookie") or ()))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        content_type = exc.headers.get("content-type", "")
        return BackendResponse(exc.code, body, content_type, tuple(exc.headers.get_all("set-cookie") or ()))


def _ssl_context_for_request(url: str) -> ssl.SSLContext | None:
    if not url.lower().startswith("https://"):
        return None
    bundle = configured_ca_bundle(ProcessEnv())
    if bundle is None:
        return None
    return ssl.create_default_context(cafile=str(bundle.path))


def _cookies_for_request(cookie_store: Any, url: str) -> str | None:
    cookies = getattr(cookie_store, "cookies", None)
    if callable(cookies):
        value = cookies(url)
        return value if isinstance(value, str) and value else None
    return None


def _store_response_cookies(cookie_store: Any, response: BackendResponse, url: str) -> None:
    if not response.set_cookie_headers:
        return
    set_cookies = getattr(cookie_store, "set_cookies", None)
    if callable(set_cookies):
        set_cookies(response.set_cookie_headers, url)


def _add_auth_headers(auth_provider: Any | None, headers: dict[str, str]) -> None:
    if auth_provider is None:
        return
    add_auth_headers = getattr(auth_provider, "add_auth_headers", None)
    if callable(add_auth_headers):
        before = dict(headers)
        add_auth_headers(headers)
        _normalize_auth_mutation(headers, before)
        return
    to_auth_headers = getattr(auth_provider, "to_auth_headers", None)
    if callable(to_auth_headers):
        for key, value in dict(to_auth_headers()).items():
            _set_header_case_insensitive(headers, str(key), str(value))
        return
    if callable(auth_provider):
        result = auth_provider(headers)
        if isinstance(result, Mapping):
            for key, value in result.items():
                _set_header_case_insensitive(headers, str(key), str(value))


def _normalize_auth_mutation(headers: dict[str, str], before: Mapping[str, str]) -> None:
    additions = [(key, value) for key, value in headers.items() if before.get(key) != value or key not in before]
    for key, value in additions:
        existing_value = headers.pop(key)
        _set_header_case_insensitive(headers, key, existing_value)
        if existing_value != value:
            _set_header_case_insensitive(headers, key, value)


def _set_header_case_insensitive(headers: dict[str, str], name: str, value: str) -> None:
    wanted = name.lower()
    for key in list(headers):
        if key.lower() == wanted:
            del headers[key]
    headers[name] = value


def _make_rate_limit_snapshot(
    *,
    limit_id: str | None,
    limit_name: str | None,
    rate_limit: RateLimitStatusDetails | Mapping[str, JsonValue] | None,
    credits: CreditStatusDetails | Mapping[str, JsonValue] | None,
    plan_type: PlanType,
    rate_limit_reached_type: RateLimitReachedType | None,
) -> RateLimitSnapshot:
    details = _rate_limit_status_details(rate_limit)
    return RateLimitSnapshot(
        limit_id=limit_id,
        limit_name=limit_name,
        primary=None if details is None else _map_rate_limit_window(_unwrap_double_option(details.primary_window)),
        secondary=None if details is None else _map_rate_limit_window(_unwrap_double_option(details.secondary_window)),
        credits=_map_credits(_credit_status_details(credits)),
        plan_type=plan_type,
        rate_limit_reached_type=rate_limit_reached_type,
    )


def _map_rate_limit_window(snapshot: RateLimitWindowSnapshot | Mapping[str, JsonValue] | None) -> RateLimitWindow | None:
    if snapshot is None:
        return None
    if isinstance(snapshot, Mapping):
        snapshot = RateLimitWindowSnapshot.from_mapping(snapshot)
    return RateLimitWindow(
        used_percent=int(snapshot.used_percent),
        window_duration_mins=_window_minutes_from_seconds(snapshot.limit_window_seconds),
        resets_at=int(snapshot.reset_at),
    )


def _map_credits(details: CreditStatusDetails | None) -> CreditsSnapshot | None:
    if details is None:
        return None
    balance = _unwrap_double_option(details.balance)
    return CreditsSnapshot(details.has_credits, details.unlimited, balance)


def _map_plan_type(plan_type: BackendPlanType | str) -> PlanType:
    raw = plan_type.value if isinstance(plan_type, BackendPlanType) else str(plan_type)
    if raw in {"education", "edu"}:
        return PlanType.EDU
    if raw in {
        "guest",
        "free_workspace",
        "quorum",
        "k12",
        "unknown",
    }:
        return PlanType.UNKNOWN
    return PlanType.parse(raw)


def _map_rate_limit_reached_from_payload(
    value: BackendRateLimitReachedType | Mapping[str, JsonValue] | None | Unset,
) -> RateLimitReachedType | None:
    value = _unwrap_double_option(value)
    if value is None:
        return None
    if isinstance(value, Mapping):
        value = BackendRateLimitReachedType.from_mapping(value)
    return _map_rate_limit_reached_type(value.kind)


def _map_rate_limit_reached_type(kind: RateLimitReachedKind | str) -> RateLimitReachedType | None:
    raw = kind.value if isinstance(kind, RateLimitReachedKind) else str(kind)
    mapping = {
        "rate_limit_reached": RateLimitReachedType.RATE_LIMIT_REACHED,
        "workspace_owner_credits_depleted": RateLimitReachedType.WORKSPACE_OWNER_CREDITS_DEPLETED,
        "workspace_member_credits_depleted": RateLimitReachedType.WORKSPACE_MEMBER_CREDITS_DEPLETED,
        "workspace_owner_usage_limit_reached": RateLimitReachedType.WORKSPACE_OWNER_USAGE_LIMIT_REACHED,
        "workspace_member_usage_limit_reached": RateLimitReachedType.WORKSPACE_MEMBER_USAGE_LIMIT_REACHED,
    }
    return mapping.get(raw)


def _window_minutes_from_seconds(seconds: int) -> int | None:
    if seconds <= 0:
        return None
    return (int(seconds) + 59) // 60


def _unwrap_double_option(value: Any) -> Any | None:
    if isinstance(value, Unset):
        return None
    return value


def _rate_limit_status_details(value: RateLimitStatusDetails | Mapping[str, JsonValue] | None) -> RateLimitStatusDetails | None:
    if value is None:
        return None
    if isinstance(value, RateLimitStatusDetails):
        return value
    if isinstance(value, Mapping):
        return RateLimitStatusDetails.from_mapping(value)
    raise TypeError("expected rate limit status details")


def _credit_status_details(value: CreditStatusDetails | Mapping[str, JsonValue] | None) -> CreditStatusDetails | None:
    if value is None:
        return None
    if isinstance(value, CreditStatusDetails):
        return value
    if isinstance(value, Mapping):
        return CreditStatusDetails.from_mapping(value)
    raise TypeError("expected credit status details")


def _additional_rate_limit_details(value: AdditionalRateLimitDetails | Mapping[str, JsonValue]) -> AdditionalRateLimitDetails:
    if isinstance(value, AdditionalRateLimitDetails):
        item = value
    elif isinstance(value, Mapping):
        item = AdditionalRateLimitDetails.from_mapping(value)
    else:
        raise TypeError("expected additional rate limit details")
    rate_limit = item.rate_limit
    if isinstance(rate_limit, Mapping):
        item = AdditionalRateLimitDetails(item.limit_name, item.metered_feature, RateLimitStatusDetails.from_mapping(rate_limit))
    return item


def _turn_or_none(value: JsonValue) -> Turn | None:
    if isinstance(value, Mapping):
        return Turn.from_mapping(value)
    return None


def _list_or_empty(value: JsonValue) -> list[JsonValue]:
    return list(value) if isinstance(value, list) else []


def _optional_str(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: JsonValue) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


__all__ = [
    "AddCreditsNudgeCreditType",
    "BackendRequest",
    "BackendResponse",
    "Client",
    "CodeTaskDetailsResponse",
    "ContentFragment",
    "PathStyle",
    "RequestError",
    "Turn",
    "TurnAttemptsSiblingTurnsResponse",
    "TurnError",
    "TurnItem",
    "Worklog",
    "WorklogMessage",
]
