"""Canonical TUI session state shared by app, widgets, and status surfaces.

Rust counterpart: ``codex-rs/tui/src/session_state.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PathLikeValue = str | Path


def _path_value(path: PathLikeValue) -> str:
    return str(path)


@dataclass(frozen=True)
class SessionNetworkProxyRuntime:
    http_addr: str
    socks_addr: str


@dataclass(frozen=True)
class MessageHistoryMetadata:
    log_id: int = 0
    entry_count: int = 0


@dataclass
class ThreadSessionState:
    thread_id: Any
    forked_from_id: Any | None = None
    fork_parent_title: str | None = None
    thread_name: str | None = None
    model: str = ""
    model_provider_id: str = ""
    service_tier: str | None = None
    approval_policy: Any | None = None
    approvals_reviewer: Any | None = None
    permission_profile: Any | None = None
    active_permission_profile: Any | None = None
    cwd: PathLikeValue = ""
    runtime_workspace_roots: list[PathLikeValue] = field(default_factory=list)
    instruction_source_paths: list[PathLikeValue] = field(default_factory=list)
    reasoning_effort: Any | None = None
    collaboration_mode: Any | None = None
    personality: Any | None = None
    message_history: MessageHistoryMetadata | None = None
    network_proxy: SessionNetworkProxyRuntime | None = None
    rollout_path: PathLikeValue | None = None

    def set_cwd_retargeting_implicit_runtime_workspace_root(self, cwd: PathLikeValue) -> None:
        """Retarget cwd and replace the old implicit workspace root when present.

        Rust replaces ``self.cwd`` first. If the previous cwd was one of the
        runtime workspace roots, that root is replaced by the new cwd and all
        other roots are preserved in their original order without duplicates.
        """

        previous_cwd = self.cwd
        self.cwd = cwd
        previous_key = _path_value(previous_cwd)
        if previous_key not in {_path_value(root) for root in self.runtime_workspace_roots}:
            return

        previous_roots = list(self.runtime_workspace_roots)
        new_roots: list[PathLikeValue] = [cwd]
        seen = {_path_value(cwd)}
        for root in previous_roots:
            root_key = _path_value(root)
            if root_key != previous_key and root_key not in seen:
                new_roots.append(root)
                seen.add(root_key)
        self.runtime_workspace_roots = new_roots


__all__ = [
    "MessageHistoryMetadata",
    "SessionNetworkProxyRuntime",
    "ThreadSessionState",
]
