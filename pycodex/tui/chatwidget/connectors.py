"""Semantic connector cache helpers for ``codex-tui::chatwidget::connectors``.

The Rust module mixes a small cache state machine with ChatWidget popup/event
wiring.  Python ports the cache, snapshot, label, and refresh-transition
semantics here while leaving concrete AppEvent, browser, and selection-view
runtime work to callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::connectors",
    source="codex/codex-rs/tui/src/chatwidget/connectors.rs",
)

CONNECTORS_SELECTION_VIEW_ID = "connectors"


@dataclass(frozen=True)
class AppInfo:
    id: str
    name: str | None = None
    description: str | None = None
    is_accessible: bool = False
    is_enabled: bool = False
    install_url: str | None = None


@dataclass(frozen=True)
class ConnectorsSnapshot:
    connectors: tuple[AppInfo, ...] = ()

    @classmethod
    def from_iterable(cls, connectors: Iterable[AppInfo | Any]) -> "ConnectorsSnapshot":
        return cls(tuple(_coerce_app_info(connector) for connector in connectors))


@dataclass(frozen=True)
class ConnectorsCacheState:
    kind: str = "Uninitialized"
    snapshot: ConnectorsSnapshot | None = None
    error: str | None = None

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
    partial_snapshot: ConnectorsSnapshot | None = None
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

    def connectors_for_mentions(self, *, connectors_enabled: bool) -> tuple[AppInfo, ...] | None:
        if not connectors_enabled:
            return None
        if self.partial_snapshot is not None:
            return self.partial_snapshot.connectors
        if self.cache.is_ready() and self.cache.snapshot is not None:
            return self.cache.snapshot.connectors
        return None

    def on_loaded(self, result: ConnectorsSnapshot | Iterable[AppInfo | Any] | str | Exception, *, is_final: bool) -> bool:
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
        updated: list[AppInfo] = []
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


def connector_description(connector: AppInfo | Any) -> str | None:
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
    return f"{status_label} · {description}"


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


def connectors_popup_params(connectors: Iterable[AppInfo | Any], selected_connector_id: str | None = None) -> dict[str, Any]:
    apps = tuple(_coerce_app_info(connector) for connector in connectors)
    total = len(apps)
    installed = sum(1 for connector in apps if connector.is_accessible)
    initial_selected_idx = None
    if selected_connector_id is not None:
        for index, connector in enumerate(apps):
            if connector.id == selected_connector_id:
                initial_selected_idx = index
                break

    items: list[dict[str, Any]] = []
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


def _coerce_snapshot(value: ConnectorsSnapshot | Iterable[AppInfo | Any]) -> ConnectorsSnapshot:
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
    "RUST_MODULE",
    "connector_brief_description",
    "connector_description",
    "connector_display_label",
    "connector_status_label",
    "connectors_enabled",
    "connectors_loading_popup_params",
    "connectors_popup_params",
]
