"""Environment request processor projection.

Ported from ``codex-app-server/src/request_processors/environment_processor.rs``.
The Rust module is a thin wrapper around ``EnvironmentManager::upsert_environment``:
store the manager, add/update an environment, convert failures through
``invalid_request(err.to_string())``, and return an empty
``EnvironmentAddResponse`` on success.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pycodex.app_server.error_code import invalid_request
from pycodex.app_server_protocol import EnvironmentAddParams, EnvironmentAddResponse, JSONRPCErrorError

JsonValue = Any


class EnvironmentRequestProcessorError(Exception):
    """Exception wrapper carrying Rust's JSON-RPC error payload."""

    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


class EnvironmentRequestProcessor:
    def __init__(self, environment_manager: Any) -> None:
        self.environment_manager = environment_manager

    @classmethod
    def new(cls, environment_manager: Any) -> "EnvironmentRequestProcessor":
        return cls(environment_manager)

    def environment_add(self, params: EnvironmentAddParams | Mapping[str, JsonValue]) -> EnvironmentAddResponse:
        params = _environment_add_params(params)
        upsert_environment = getattr(self.environment_manager, "upsert_environment", None)
        if not callable(upsert_environment):
            raise EnvironmentRequestProcessorError(
                invalid_request("environment manager must expose upsert_environment(environment_id, exec_server_url)")
            )
        try:
            upsert_environment(params.environment_id, params.exec_server_url)
        except Exception as exc:
            raise EnvironmentRequestProcessorError(invalid_request(str(exc))) from exc
        return EnvironmentAddResponse()


def _environment_add_params(params: EnvironmentAddParams | Mapping[str, JsonValue]) -> EnvironmentAddParams:
    if isinstance(params, EnvironmentAddParams):
        return params
    return EnvironmentAddParams.from_mapping(params)


__all__ = [
    "EnvironmentRequestProcessor",
    "EnvironmentRequestProcessorError",
]
