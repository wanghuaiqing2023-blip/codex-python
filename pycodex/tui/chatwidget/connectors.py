"""Semantic connector cache helpers for ``codex-tui::chatwidget::connectors``.

The Rust module mixes a small cache state machine with ChatWidget popup/event
wiring.  Python ports the cache, snapshot, label, and refresh-transition
semantics here while leaving concrete AppEvent, browser, and selection-view
runtime work to callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::connectors",
    source="codex/codex-rs/tui/src/chatwidget/connectors.rs",
    status="complete",
)

CONNECTORS_SELECTION_VIEW_ID = "connectors"


@dataclass(frozen=True)
class AppInfo:
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    is_accessible: bool = False
    is_enabled: bool = False
    install_url: Optional[str] = None


@dataclass(frozen=True)
class ConnectorsSnapshot:
    connectors: Tuple[AppInfo, ...] = ()

    @classmethod
    def from_iterable(cls, connectors: Iterable[AppInfo | Any]) -> "ConnectorsSnapshot":
        return cls(tuple(_coerce_app_info(connector) for connector in connectors))


@dataclass(frozen=True)
class ConnectorsCacheState:
    kind: str = "Uninitialized"
    snapshot: Optional[ConnectorsSnapshot] = None
    error: Optional[str] = None

    @classmethod
    def Uninitialized(cls) -> "ConnectorsCacheState":
        return cls("Uninitialized")

    @classmethod
    def Loading(cls) -> "ConnectorsCacheState":
        return cls("Loading")

    @classmethod
    def Ready(cls, snapshot: ConnectorsSnapshot | Iterable[AppInfo | Any]) -> "ConnectorsCacheState":
        return cls("Ready", _coerce_snapshot(snapshot))

    @classmethod
    def Failed(cls, error: str) -> "ConnectorsCacheState":
        return cls("Failed", error=str(error))

    def is_ready(self) -> bool:
        return self.kind == "Ready" and self.snapshot is not None


@dataclass
class ConnectorsState:
    cache: ConnectorsCacheState = field(default_factory=ConnectorsCacheState.Uninitialized)
    partial_snapshot: Optional[ConnectorsSnapshot] = None
    prefetch_in_flight: bool = False
    force_refetch_pending: bool = False

    def begin_refresh(self, *, connectors_enabled: bool, force_refetch: bool = False) -> bool:
        if not connectors_enabled:
            return False
        if self.prefetch_in_flight:
            if force_refetch:
                self.force_refetch_pending = True
            return False

        self.prefetch_in_flight = True
        if not self.cache.is_ready():
            self.cache = ConnectorsCacheState.Loading()
        return True

    def connectors_for_mentions(self, *, connectors_enabled: bool) -> Optional[Tuple[AppInfo, ...]]:
        if not connectors_enabled:
            return None
        if self.partial_snapshot is not None:
            return self.partial_snapshot.connectors
        if self.cache.is_ready() and self.cache.snapshot is not None:
            return self.cache.snapshot.connectors
        return None

    def on_loaded(self, result: Union[ConnectorsSnapshot, Iterable[Any], str, Exception], *, is_final: bool) -> bool:
        """Apply a connectors-list response.

        Returns ``True`` when Rust would immediately queue a pending forced
        refetch after a final response finishes.
        """

        trigger_pending_force_refetch = False
        if is_final:
            self.prefetch_in_flight = False
            if self.force_refetch_pending:
                self.force_refetch_pending = False
                trigger_pending_force_refetch = True

        if isinstance(result, (str, Exception)):
            self._apply_error(str(result))
            return trigger_pending_force_refetch

        snapshot = _coerce_snapshot(result)
        snapshot = self._preserve_existing_enabled_flags(snapshot)
        if is_final:
            self.partial_snapshot = None
            self.cache = ConnectorsCacheState.Ready(snapshot)
        else:
            self.partial_snapshot = snapshot
        return trigger_pending_force_refetch

    def update_connector_enabled(self, connector_id: str, enabled: bool) -> bool:
        if not self.cache.is_ready() or self.cache.snapshot is None:
            return False

        changed = False
        updated: List[AppInfo] = []
        for connector in self.cache.snapshot.connectors:
            if connector.id == connector_id:
                if connector.is_enabled != enabled:
                    changed = True
                updated.append(replace(connector, is_enabled=enabled))
            else:
                updated.append(connector)
        if not changed:
            return False

        self.cache = ConnectorsCacheState.Ready(ConnectorsSnapshot(tuple(updated)))
        return True

    def _preserve_existing_enabled_flags(self, snapshot: ConnectorsSnapshot) -> ConnectorsSnapshot:
        if not self.cache.is_ready() or self.cache.snapshot is None:
            return snapshot
        enabled_by_id = {connector.id: connector.is_enabled for connector in self.cache.snapshot.connectors}
        return ConnectorsSnapshot(
            tuple(
                replace(connector, is_enabled=enabled_by_id.get(connector.id, connector.is_enabled))
                for connector in snapshot.connectors
            )
        )

    def _apply_error(self, error: str) -> None:
        partial_snapshot = self.partial_snapshot
        self.partial_snapshot = None
        if self.cache.is_ready():
            return
        if partial_snapshot is not None:
            self.cache = ConnectorsCacheState.Ready(partial_snapshot)
        else:
            self.cache = ConnectorsCacheState.Failed(error)


def connectors_enabled(features_apps_enabled: bool, has_chatgpt_account: bool) -> bool:
    return bool(features_apps_enabled and has_chatgpt_account)


def connector_display_label(connector: AppInfo | Any) -> str:
    app = _coerce_app_info(connector)
    return app.name or app.id


def connector_status_label(connector: AppInfo | Any) -> str:
    app = _coerce_app_info(connector)
    if app.is_accessible:
        return "Installed" if app.is_enabled else "Installed - Disabled"
    return "Can be installed"


def connector_description(connector: AppInfo | Any) -> Optional[str]:
    description = _coerce_app_info(connector).description
    if description is None:
        return None
    stripped = description.strip()
    return stripped or None


def connector_brief_description(connector: AppInfo | Any) -> str:
    status_label = connector_status_label(connector)
    description = connector_description(connector)
    if description is None:
        return status_label
    return f"{status_label} ? {description}"


def connectors_loading_popup_params() -> dict[str, Any]:
    return {
        "view_id": CONNECTORS_SELECTION_VIEW_ID,
        "header": ["Apps", "Loading installed and available apps..."],
        "items": [
            {
                "name": "Loading apps...",
                "description": "This updates when the full list is ready.",
                "is_disabled": True,
            }
        ],
    }


def connectors_popup_params(connectors: Iterable[AppInfo | Any], selected_connector_id: Optional[str] = None) -> Dict[str, Any]:
    apps = tuple(_coerce_app_info(connector) for connector in connectors)
    total = len(apps)
    installed = sum(1 for connector in apps if connector.is_accessible)
    initial_selected_idx = None
    if selected_connector_id is not None:
        for index, connector in enumerate(apps):
            if connector.id == selected_connector_id:
                initial_selected_idx = index
                break

    items: List[Dict[str, Any]] = []
    for connector in apps:
        label = connector_display_label(connector)
        status_label = connector_status_label(connector)
        has_link = connector.install_url is not None
        if connector.is_accessible:
            selected_description = (
                f"{status_label}. Press Enter to open the app page to install, manage, or enable/disable this app."
            )
            instructions = "Manage this app in your browser."
        else:
            selected_description = f"{status_label}. Press Enter to open the app page to install this app."
            instructions = "Install this app in your browser, then reload Codex."
        if not has_link:
            selected_description = f"{status_label}. App link unavailable."
        items.append(
            {
                "id": connector.id,
                "name": label,
                "description": connector_brief_description(connector),
                "search_value": f"{label} {connector.id}",
                "selected_description": selected_description,
                "dismiss_on_select": True,
                "action": "open_app_link" if has_link else "missing_app_link",
                "instructions": instructions if has_link else None,
                "is_installed": connector.is_accessible,
                "is_enabled": connector.is_enabled,
                "install_url": connector.install_url,
            }
        )

    return {
        "view_id": CONNECTORS_SELECTION_VIEW_ID,
        "header": [
            "Apps",
            "Use $ to insert an installed app into your prompt.",
            f"Installed {installed} of {total} available apps.",
        ],
        "items": items,
        "is_searchable": True,
        "search_placeholder": "Type to search apps",
        "col_width_mode": "AutoAllRows",
        "initial_selected_idx": initial_selected_idx,
    }


@dataclass
class ConnectorsWidgetState:
    features_apps_enabled: bool = True
    has_chatgpt_account: bool = True
    connectors: ConnectorsState = field(default_factory=ConnectorsState)
    sent_fetches: List[bool] = field(default_factory=list)
    info_messages: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    history: List[Any] = field(default_factory=list)
    shown_selection_views: List[Dict[str, Any]] = field(default_factory=list)
    replaced_selection_views: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)
    replace_selection_view_result: bool = False
    selected_index: Optional[int] = None
    bottom_pane_snapshot: Optional[ConnectorsSnapshot] = None
    redraws: int = 0

    def connectors_enabled(self) -> bool:
        return connectors_enabled(self.features_apps_enabled, self.has_chatgpt_account)

    def refresh_connectors(self, force_refetch: bool) -> None:
        self.queue_connectors_refresh(force_refetch)

    def prefetch_connectors(self) -> None:
        self.queue_connectors_refresh(False)

    def queue_connectors_refresh(self, force_refetch: bool) -> None:
        if self.connectors.begin_refresh(connectors_enabled=self.connectors_enabled(), force_refetch=force_refetch):
            self.sent_fetches.append(force_refetch)

    def add_connectors_output(self) -> None:
        if not self.connectors_enabled():
            self.info_messages.append(("Apps are disabled.", "Enable the apps feature to use $ or /apps."))
            return
        connectors_cache = self.connectors.cache
        should_force_refetch = (not self.connectors.prefetch_in_flight) or connectors_cache.is_ready()
        self.queue_connectors_refresh(should_force_refetch)
        if connectors_cache.is_ready() and connectors_cache.snapshot is not None:
            if not connectors_cache.snapshot.connectors:
                self.info_messages.append(("No apps available.", None))
            else:
                self.open_connectors_popup(connectors_cache.snapshot.connectors)
        elif connectors_cache.kind == "Failed":
            self.history.append({"kind": "error", "message": connectors_cache.error})
        else:
            self.open_connectors_loading_popup()
        self.request_redraw()

    def open_connectors_loading_popup(self) -> None:
        params = connectors_loading_popup_params()
        if not self.replace_selection_view_if_active(CONNECTORS_SELECTION_VIEW_ID, params):
            self.show_selection_view(params)

    def open_connectors_popup(self, connectors: Iterable[AppInfo]) -> None:
        self.show_selection_view(connectors_popup_params(connectors, None))

    def refresh_connectors_popup_if_open(self, connectors: Iterable[AppInfo]) -> None:
        selected_connector_id = None
        if self.selected_index is not None and self.connectors.cache.is_ready() and self.connectors.cache.snapshot is not None:
            existing = self.connectors.cache.snapshot.connectors
            if 0 <= self.selected_index < len(existing):
                selected_connector_id = existing[self.selected_index].id
        self.replace_selection_view_if_active(
            CONNECTORS_SELECTION_VIEW_ID,
            connectors_popup_params(connectors, selected_connector_id),
        )

    def on_connectors_loaded(self, result: Union[ConnectorsSnapshot, Iterable[Any], str, Exception], is_final: bool) -> None:
        old_ready = self.connectors.cache.snapshot if self.connectors.cache.is_ready() else None
        trigger = False
        if is_final:
            self.connectors.prefetch_in_flight = False
            if self.connectors.force_refetch_pending:
                self.connectors.force_refetch_pending = False
                trigger = True
        if isinstance(result, (str, Exception)):
            partial_snapshot = self.connectors.partial_snapshot
            self.connectors.partial_snapshot = None
            if old_ready is not None:
                self.set_connectors_snapshot(old_ready)
            elif partial_snapshot is not None:
                self.refresh_connectors_popup_if_open(partial_snapshot.connectors)
                self.connectors.cache = ConnectorsCacheState.Ready(partial_snapshot)
                self.set_connectors_snapshot(partial_snapshot)
            else:
                self.connectors.cache = ConnectorsCacheState.Failed(str(result))
                self.set_connectors_snapshot(None)
        else:
            snapshot = self.connectors._preserve_existing_enabled_flags(_coerce_snapshot(result))
            if is_final:
                self.connectors.partial_snapshot = None
                self.refresh_connectors_popup_if_open(snapshot.connectors)
                self.connectors.cache = ConnectorsCacheState.Ready(snapshot)
            else:
                self.connectors.partial_snapshot = snapshot
            self.set_connectors_snapshot(snapshot)
        if trigger:
            self.queue_connectors_refresh(True)

    def update_connector_enabled(self, connector_id: str, enabled: bool) -> None:
        if not self.connectors.update_connector_enabled(connector_id, enabled):
            return
        snapshot = self.connectors.cache.snapshot
        if snapshot is not None:
            self.refresh_connectors_popup_if_open(snapshot.connectors)
            self.set_connectors_snapshot(snapshot)

    def replace_selection_view_if_active(self, view_id: str, params: Dict[str, Any]) -> bool:
        self.replaced_selection_views.append((view_id, params))
        return self.replace_selection_view_result

    def show_selection_view(self, params: Dict[str, Any]) -> None:
        self.shown_selection_views.append(params)

    def set_connectors_snapshot(self, snapshot: Optional[ConnectorsSnapshot]) -> None:
        self.bottom_pane_snapshot = snapshot

    def request_redraw(self) -> None:
        self.redraws += 1


def _coerce_snapshot(value: Union[ConnectorsSnapshot, Iterable[Any]]) -> ConnectorsSnapshot:
    if isinstance(value, ConnectorsSnapshot):
        return value
    return ConnectorsSnapshot.from_iterable(value)


def _coerce_app_info(value: AppInfo | Any) -> AppInfo:
    if isinstance(value, AppInfo):
        return value
    if isinstance(value, dict):
        get = value.get
    else:
        get = lambda name, default=None: getattr(value, name, default)
    return AppInfo(
        id=str(get("id")),
        name=get("name", None),
        description=get("description", None),
        is_accessible=bool(get("is_accessible", False)),
        is_enabled=bool(get("is_enabled", False)),
        install_url=get("install_url", None),
    )


__all__ = [
    "AppInfo",
    "CONNECTORS_SELECTION_VIEW_ID",
    "ConnectorsCacheState",
    "ConnectorsSnapshot",
    "ConnectorsState",
    "ConnectorsWidgetState",
    "RUST_MODULE",
    "connector_brief_description",
    "connector_description",
    "connector_display_label",
    "connector_status_label",
    "connectors_enabled",
    "connectors_loading_popup_params",
    "connectors_popup_params",
]
