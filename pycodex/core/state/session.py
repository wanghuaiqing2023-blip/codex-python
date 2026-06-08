"""Session-wide mutable state aligned with ``codex-rs/core/src/state/session.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from collections import deque
from typing import Any, Iterable

from pycodex.core.context_manager.history import ContextManager, TotalTokenUsageBreakdown
from pycodex.core.state.additional_context import AdditionalContextStore
from pycodex.core.state.auto_compact_window import AutoCompactWindow, AutoCompactWindowSnapshot
from pycodex.core.tools.handlers.utils import merge_permission_profiles
from pycodex.protocol import (
    AdditionalPermissionProfile,
    RateLimitSnapshot,
    ResponseItem,
    TokenUsage,
    TokenUsageInfo,
    TruncationPolicyConfig,
    TurnContextItem,
)


@dataclass
class SessionState:
    """Python state facade for Rust ``SessionState`` history/token helpers."""

    session_configuration: Any = None
    history: ContextManager = field(default_factory=ContextManager.new)
    latest_rate_limits: RateLimitSnapshot | None = None
    _server_reasoning_included: bool = False
    _previous_turn_settings: Any = None
    _next_turn_is_first: bool = True
    _granted_permissions: AdditionalPermissionProfile | None = None
    mcp_dependency_prompted_store: set[str] = field(default_factory=set)
    active_connector_selection: set[str] = field(default_factory=set)
    pending_session_start_sources: deque[Any] = field(default_factory=deque)
    startup_prewarm: Any = None
    additional_context: AdditionalContextStore = field(default_factory=AdditionalContextStore)
    auto_compact_window: AutoCompactWindow = field(default_factory=AutoCompactWindow)

    @classmethod
    def new(cls, session_configuration: Any = None) -> "SessionState":
        return cls(session_configuration=session_configuration)

    def record_items(
        self,
        items: Iterable[ResponseItem],
        policy: TruncationPolicyConfig | None = None,
    ) -> None:
        self.history.record_items(items, policy)

    def previous_turn_settings(self) -> Any:
        return self._previous_turn_settings

    def set_previous_turn_settings(self, previous_turn_settings: Any | None) -> None:
        self._previous_turn_settings = previous_turn_settings

    def set_next_turn_is_first(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("value must be bool")
        self._next_turn_is_first = value

    def take_next_turn_is_first(self) -> bool:
        is_first_turn = self._next_turn_is_first
        self._next_turn_is_first = False
        return is_first_turn

    def clone_history(self) -> ContextManager:
        cloned = ContextManager.from_items(self.history.raw_items())
        cloned.history_version = self.history.history_version
        cloned.set_token_info(self.history.token_info())
        cloned.set_reference_context_item(self.history.reference_context_item())
        return cloned

    def replace_history(
        self,
        items: Iterable[ResponseItem],
        reference_context_item: TurnContextItem | None,
    ) -> None:
        self.history.replace(items)
        self.history.set_reference_context_item(reference_context_item)
        self.auto_compact_window.clear_prefill()

    def set_token_info(self, info: TokenUsageInfo | None) -> None:
        self.history.set_token_info(info)

    def token_info(self) -> TokenUsageInfo | None:
        return self.history.token_info()

    def set_reference_context_item(self, item: TurnContextItem | None) -> None:
        self.history.set_reference_context_item(item)

    def reference_context_item(self) -> TurnContextItem | None:
        return self.history.reference_context_item()

    def update_token_info_from_usage(
        self,
        usage: TokenUsage,
        model_context_window: int | None = None,
    ) -> None:
        self.history.update_token_info(usage, model_context_window)

    def ensure_auto_compact_window_server_prefill_from_usage(self, usage: TokenUsage) -> None:
        self.auto_compact_window.ensure_server_observed_prefill_from_usage(usage)

    def set_auto_compact_window_estimated_prefill(self, tokens: int) -> None:
        self.auto_compact_window.set_estimated_prefill(tokens)

    def start_next_auto_compact_window(self) -> None:
        self.auto_compact_window.start_next()

    def auto_compact_window_snapshot(self) -> AutoCompactWindowSnapshot:
        return self.auto_compact_window.snapshot()

    def set_rate_limits(self, snapshot: RateLimitSnapshot) -> None:
        if not isinstance(snapshot, RateLimitSnapshot):
            raise TypeError("snapshot must be RateLimitSnapshot")
        self.latest_rate_limits = _merge_rate_limit_fields(self.latest_rate_limits, snapshot)

    def token_info_and_rate_limits(self) -> tuple[TokenUsageInfo | None, RateLimitSnapshot | None]:
        return (self.token_info(), self.latest_rate_limits)

    def set_token_usage_full(self, context_window: int) -> None:
        self.history.set_token_usage_full(context_window)

    def get_total_token_usage(self, server_reasoning_included: bool) -> int:
        if not isinstance(server_reasoning_included, bool):
            raise TypeError("server_reasoning_included must be bool")
        return self.history.get_total_token_usage(server_reasoning_included)

    def get_total_token_usage_breakdown(self) -> TotalTokenUsageBreakdown:
        return self.history.get_total_token_usage_breakdown()

    def set_server_reasoning_included(self, included: bool) -> None:
        if not isinstance(included, bool):
            raise TypeError("included must be bool")
        self._server_reasoning_included = included

    def server_reasoning_included(self) -> bool:
        return self._server_reasoning_included

    def record_mcp_dependency_prompted(self, names: Iterable[str]) -> None:
        for name in names:
            if not isinstance(name, str):
                raise TypeError("mcp dependency names must be strings")
            self.mcp_dependency_prompted_store.add(name)

    def mcp_dependency_prompted(self) -> set[str]:
        return set(self.mcp_dependency_prompted_store)

    def set_session_startup_prewarm(self, startup_prewarm: Any) -> None:
        self.startup_prewarm = startup_prewarm

    def take_session_startup_prewarm(self) -> Any | None:
        startup_prewarm = self.startup_prewarm
        self.startup_prewarm = None
        return startup_prewarm

    def merge_connector_selection(self, connector_ids: Iterable[str]) -> set[str]:
        for connector_id in connector_ids:
            if not isinstance(connector_id, str):
                raise TypeError("connector ids must be strings")
            self.active_connector_selection.add(connector_id)
        return set(self.active_connector_selection)

    def get_connector_selection(self) -> set[str]:
        return set(self.active_connector_selection)

    def clear_connector_selection(self) -> None:
        self.active_connector_selection.clear()

    def queue_pending_session_start_source(self, value: Any) -> None:
        self.pending_session_start_sources.append(value)

    def take_pending_session_start_source(self) -> Any | None:
        if not self.pending_session_start_sources:
            return None
        return self.pending_session_start_sources.popleft()

    def record_granted_permissions(self, permissions: AdditionalPermissionProfile) -> None:
        if not isinstance(permissions, AdditionalPermissionProfile):
            raise TypeError("permissions must be AdditionalPermissionProfile")
        self._granted_permissions = merge_permission_profiles(self._granted_permissions, permissions)

    def granted_permissions(self) -> AdditionalPermissionProfile | None:
        return self._granted_permissions


def _merge_rate_limit_fields(
    previous: RateLimitSnapshot | None,
    snapshot: RateLimitSnapshot,
) -> RateLimitSnapshot:
    if not isinstance(snapshot, RateLimitSnapshot):
        raise TypeError("snapshot must be RateLimitSnapshot")
    limit_id = snapshot.limit_id or "codex"
    credits = snapshot.credits
    if credits is None and previous is not None:
        credits = previous.credits
    plan_type = snapshot.plan_type
    if plan_type is None and previous is not None:
        plan_type = previous.plan_type
    if limit_id == snapshot.limit_id and credits is snapshot.credits and plan_type is snapshot.plan_type:
        return snapshot
    return replace(snapshot, limit_id=limit_id, credits=credits, plan_type=plan_type)


__all__ = [
    "SessionState",
]
