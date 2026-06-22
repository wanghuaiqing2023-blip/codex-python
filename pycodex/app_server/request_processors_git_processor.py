"""Git request processor projection.

Ported from ``codex-app-server/src/request_processors/git_processor.rs``.
The Rust module is a small facade over ``git_diff_to_remote``: project the
successful ``sha``/``diff`` pair into ``GitDiffToRemoteResponse`` or return an
``invalid_request`` JSON-RPC error when no remote diff can be computed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pycodex.app_server.error_code import invalid_request
from pycodex.app_server_protocol import GitDiffToRemoteParams, GitDiffToRemoteResponse, JSONRPCErrorError
from pycodex.git_utils import git_diff_to_remote

JsonValue = Any
GitDiffToRemoteFn = Callable[[Path], Any]


class GitRequestProcessorError(Exception):
    """Exception wrapper carrying Rust's JSON-RPC error payload."""

    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


class GitRequestProcessor:
    def __init__(self, diff_to_remote: GitDiffToRemoteFn | None = None) -> None:
        self._diff_to_remote = diff_to_remote or git_diff_to_remote

    @classmethod
    def new(cls) -> "GitRequestProcessor":
        return cls()

    def git_diff_to_remote(self, params: GitDiffToRemoteParams | Mapping[str, JsonValue]) -> GitDiffToRemoteResponse:
        params = _git_diff_to_remote_params(params)
        return self.git_diff_to_origin(params.cwd)

    def git_diff_to_origin(self, cwd: Path | str) -> GitDiffToRemoteResponse:
        cwd = Path(cwd)
        value = self._diff_to_remote(cwd)
        if value is None:
            raise GitRequestProcessorError(
                invalid_request(f"failed to compute git diff to remote for cwd: {_rust_path_debug(cwd)}")
            )
        return GitDiffToRemoteResponse(sha=_field(value, "sha"), diff=_field(value, "diff"))


def _git_diff_to_remote_params(params: GitDiffToRemoteParams | Mapping[str, JsonValue]) -> GitDiffToRemoteParams:
    if isinstance(params, GitDiffToRemoteParams):
        return params
    if not isinstance(params, Mapping):
        raise TypeError("GitDiffToRemoteParams mapping must be a mapping")
    cwd = params.get("cwd")
    if cwd is None:
        raise KeyError("cwd")
    return GitDiffToRemoteParams(cwd)


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value[name]
    return getattr(value, name)


def _rust_path_debug(path: Path) -> str:
    return json.dumps(str(path))


__all__ = [
    "GitRequestProcessor",
    "GitRequestProcessorError",
]
