"""Remote thread-config loader from ``codex-config::thread_config::remote``."""

from __future__ import annotations

import inspect
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import JsonValue
from .. import SessionThreadConfig
from .. import ThreadConfigContext
from .. import ThreadConfigLoadError
from .. import ThreadConfigLoadErrorCode
from .. import ThreadConfigLoader
from .. import ThreadConfigSource
from .. import UserThreadConfig
from .. import _provider_to_mapping


REMOTE_THREAD_CONFIG_LOAD_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class RemoteThreadConfigLoader(ThreadConfigLoader):
    endpoint: str
    client: Any = None

    @classmethod
    def new(cls, endpoint: str, client: Any = None) -> "RemoteThreadConfigLoader":
        return cls(str(endpoint), client)

    async def load(self, context: ThreadConfigContext) -> list[ThreadConfigSource]:
        if self.client is not None:
            request = load_thread_config_request(context)
            response = self.client(request)
            if inspect.isawaitable(response):
                response = await response
            return [
                thread_config_source_from_proto(source)
                for source in _response_sources(response)
            ]
        raise ThreadConfigLoadError.new(
            ThreadConfigLoadErrorCode.REQUEST_FAILED,
            None,
            "remote thread config loading is not implemented in pycodex",
        )


def load_thread_config_request(
    context: ThreadConfigContext,
) -> dict[str, JsonValue]:
    if not isinstance(context, ThreadConfigContext):
        raise TypeError("context must be ThreadConfigContext")
    return {
        "thread_id": context.thread_id,
        "cwd": None if context.cwd is None else str(context.cwd),
        "timeout_seconds": REMOTE_THREAD_CONFIG_LOAD_TIMEOUT_SECONDS,
        "grpc_timeout": "5000000u",
    }


def remote_status_to_error(status: Any) -> ThreadConfigLoadError:
    code = _status_code(status)
    error_code = (
        ThreadConfigLoadErrorCode.AUTH
        if code in {"unauthenticated", "permission_denied"}
        else ThreadConfigLoadErrorCode.TIMEOUT
        if code == "deadline_exceeded"
        else ThreadConfigLoadErrorCode.REQUEST_FAILED
    )
    return ThreadConfigLoadError.new(
        error_code,
        None,
        f"remote thread config request failed: {status}",
    )


def thread_config_source_from_proto(
    source: Mapping[str, JsonValue] | Any,
) -> ThreadConfigSource:
    payload = _as_mapping(source, "thread config source")
    if "session" in payload:
        return ThreadConfigSource.session(
            session_thread_config_from_proto(payload["session"])
        )
    if "user" in payload:
        return ThreadConfigSource.user(UserThreadConfig())
    kind = payload.get("source")
    if kind == "session":
        return ThreadConfigSource.session(
            session_thread_config_from_proto(payload.get("config", {}))
        )
    if kind == "user":
        return ThreadConfigSource.user(UserThreadConfig())
    raise _parse_error("remote thread config omitted source payload")


def session_thread_config_from_proto(
    config: Mapping[str, JsonValue] | Any,
) -> SessionThreadConfig:
    payload = _as_mapping(config, "session thread config")
    providers = payload.get("model_providers", ())
    if isinstance(providers, Mapping):
        provider_items = providers.items()
    elif isinstance(providers, Sequence) and not isinstance(
        providers,
        (str, bytes),
    ):
        provider_items = (
            model_provider_from_proto(provider) for provider in providers
        )
        model_providers = {
            provider_id: provider for provider_id, provider in provider_items
        }
        return SessionThreadConfig(
            model_provider=_optional_string(
                payload.get("model_provider"),
                "model_provider",
            ),
            model_providers=model_providers,
            features=_bool_mapping(payload.get("features", {}), "features"),
        )
    else:
        raise _parse_error("remote thread config returned invalid model_providers")
    return SessionThreadConfig(
        model_provider=_optional_string(
            payload.get("model_provider"),
            "model_provider",
        ),
        model_providers={
            str(provider_id): _provider_to_mapping(provider)
            for provider_id, provider in provider_items
        },
        features=_bool_mapping(payload.get("features", {}), "features"),
    )


def model_provider_from_proto(
    provider: Mapping[str, JsonValue] | Any,
) -> tuple[str, Mapping[str, JsonValue]]:
    payload = _as_mapping(provider, "model provider")
    provider_id = payload.get("id")
    if not isinstance(provider_id, str) or not provider_id:
        raise _parse_error(
            "remote thread config returned model provider without an id"
        )
    wire_api = payload.get("wire_api")
    if wire_api in {None, "", "unspecified", 0}:
        raise _parse_error("remote thread config omitted wire_api")
    if wire_api not in {"responses", "Responses", 1}:
        raise _parse_error(
            f"remote thread config returned unknown wire_api: {wire_api}"
        )
    info: dict[str, JsonValue] = {}
    for key in (
        "name",
        "base_url",
        "env_key",
        "env_key_instructions",
        "experimental_bearer_token",
        "query_params",
        "http_headers",
        "env_http_headers",
        "request_max_retries",
        "stream_max_retries",
        "stream_idle_timeout_ms",
        "websocket_connect_timeout_ms",
        "requires_openai_auth",
        "supports_websockets",
    ):
        if key in payload:
            info[key] = payload[key]
    info["wire_api"] = "responses"
    if "auth" in payload and payload["auth"] is not None:
        info["auth"] = model_provider_auth_from_proto(payload["auth"])
    if "name" not in info:
        info["name"] = provider_id
    return provider_id, info


def model_provider_auth_from_proto(
    auth: Mapping[str, JsonValue] | Any,
) -> dict[str, JsonValue]:
    payload = _as_mapping(auth, "model provider auth")
    timeout_ms = payload.get("timeout_ms")
    if (
        not isinstance(timeout_ms, int)
        or isinstance(timeout_ms, bool)
        or timeout_ms == 0
    ):
        raise _parse_error("remote thread config returned zero auth timeout_ms")
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        raise _parse_error(
            f"remote thread config returned invalid auth cwd {cwd!r}"
        )
    return {
        "command": _required_string(payload.get("command"), "command"),
        "args": list(_string_sequence(payload.get("args", ()), "args")),
        "timeout_ms": timeout_ms,
        "refresh_interval_ms": payload.get("refresh_interval_ms"),
        "cwd": cwd,
    }


def _response_sources(response: Any) -> Sequence[Any]:
    payload = _as_mapping(response, "remote thread config response")
    sources = payload.get("sources", ())
    if isinstance(sources, str) or not isinstance(sources, Sequence):
        raise _parse_error("remote thread config returned invalid sources")
    return sources


def _status_code(status: Any) -> str:
    code = status() if callable(status) else getattr(status, "code", None)
    if callable(code):
        code = code()
    if code is None and isinstance(status, Mapping):
        code = status.get("code")
    text = str(code if code is not None else status).rsplit(".", 1)[-1]
    text = text.replace("-", "_")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()


def _as_mapping(
    value: Mapping[str, JsonValue] | Any,
    label: str,
) -> Mapping[str, JsonValue]:
    if isinstance(value, Mapping):
        return value
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        mapped = to_mapping()
        if isinstance(mapped, Mapping):
            return mapped
    if hasattr(value, "__dict__"):
        return vars(value)
    raise _parse_error(f"{label} must be a mapping")


def _parse_error(message: str) -> ThreadConfigLoadError:
    return ThreadConfigLoadError.new(
        ThreadConfigLoadErrorCode.PARSE,
        None,
        message,
    )


def _optional_string(value: JsonValue, label: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, label)


def _required_string(value: JsonValue, label: str) -> str:
    if not isinstance(value, str):
        raise _parse_error(f"{label} must be a string")
    return value


def _string_sequence(value: JsonValue, label: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise _parse_error(f"{label} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise _parse_error(f"{label} must be a sequence of strings")
    return tuple(value)


def _bool_mapping(value: JsonValue, label: str) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        raise _parse_error(f"{label} must be a mapping")
    result: dict[str, bool] = {}
    for key, item in value.items():
        if not isinstance(item, bool):
            raise _parse_error(f"{label} values must be bools")
        result[str(key)] = item
    return dict(sorted(result.items()))


__all__ = ["RemoteThreadConfigLoader"]
