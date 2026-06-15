from __future__ import annotations

# Rust parity source: codex-rs/tui/src/chatwidget/connectors.rs
# Behavior contract: connector cache state transitions, mention snapshot lookup,
# label formatting, popup params, partial/final refresh handling, and local
# enabled-state mutation.

from pycodex.tui.chatwidget.connectors import (
    AppInfo,
    ConnectorsCacheState,
    ConnectorsSnapshot,
    ConnectorsState,
    ConnectorsWidgetState,
    connector_brief_description,
    connector_description,
    connector_status_label,
    connectors_enabled,
    connectors_loading_popup_params,
    connectors_popup_params,
)


def app(id: str, *, accessible=False, enabled=False, description=None, url="https://example.test/app", name=None):
    return AppInfo(id=id, name=name, description=description, is_accessible=accessible, is_enabled=enabled, install_url=url)


def snapshot(*connectors: AppInfo) -> ConnectorsSnapshot:
    return ConnectorsSnapshot(connectors)


def test_connectors_enabled_requires_apps_feature_and_chatgpt_account():
    assert connectors_enabled(True, True) is True
    assert connectors_enabled(False, True) is False
    assert connectors_enabled(True, False) is False


def test_begin_refresh_sets_loading_and_defers_forced_refresh_while_in_flight():
    state = ConnectorsState()

    assert state.begin_refresh(connectors_enabled=True, force_refetch=False) is True
    assert state.prefetch_in_flight is True
    assert state.cache.kind == "Loading"

    assert state.begin_refresh(connectors_enabled=True, force_refetch=True) is False
    assert state.force_refetch_pending is True


def test_begin_refresh_keeps_ready_cache_visible_while_refetching():
    state = ConnectorsState(cache=ConnectorsCacheState.Ready(snapshot(app("drive"))))

    assert state.begin_refresh(connectors_enabled=True, force_refetch=True) is True
    assert state.cache.kind == "Ready"


def test_connectors_for_mentions_prefers_partial_snapshot_then_ready_cache():
    ready = snapshot(app("ready"))
    partial = snapshot(app("partial"))
    state = ConnectorsState(cache=ConnectorsCacheState.Ready(ready), partial_snapshot=partial)

    assert [connector.id for connector in state.connectors_for_mentions(connectors_enabled=True)] == ["partial"]
    state.partial_snapshot = None
    assert [connector.id for connector in state.connectors_for_mentions(connectors_enabled=True)] == ["ready"]
    assert state.connectors_for_mentions(connectors_enabled=False) is None


def test_connector_description_status_and_brief_description_trim_like_rust():
    installed = app("drive", accessible=True, enabled=True, description="  Files  ")
    disabled = app("mail", accessible=True, enabled=False, description="")
    available = app("slack", accessible=False, enabled=False, description=None)

    assert connector_status_label(installed) == "Installed"
    assert connector_status_label(disabled) == "Installed - Disabled"
    assert connector_status_label(available) == "Can be installed"
    assert connector_description(installed) == "Files"
    assert connector_description(disabled) is None
    assert connector_brief_description(installed) == "Installed ? Files"
    assert connector_brief_description(available) == "Can be installed"


def test_loading_and_ready_popup_params_match_semantic_selection_shape():
    loading = connectors_loading_popup_params()
    assert loading["view_id"] == "connectors"
    assert loading["items"][0]["is_disabled"] is True

    params = connectors_popup_params(
        [
            app("drive", name="Drive", accessible=True, enabled=True, description="Files"),
            app("slack", accessible=False, enabled=False, url=None),
        ],
        selected_connector_id="slack",
    )

    assert params["header"][-1] == "Installed 1 of 2 available apps."
    assert params["initial_selected_idx"] == 1
    assert params["items"][0]["search_value"] == "Drive drive"
    assert params["items"][0]["action"] == "open_app_link"
    assert params["items"][1]["action"] == "missing_app_link"
    assert params["items"][1]["selected_description"] == "Can be installed. App link unavailable."


def test_on_loaded_partial_final_error_and_pending_force_refetch_semantics():
    state = ConnectorsState()
    assert state.begin_refresh(connectors_enabled=True, force_refetch=False) is True
    assert state.begin_refresh(connectors_enabled=True, force_refetch=True) is False

    assert state.on_loaded(snapshot(app("partial", accessible=True)), is_final=False) is False
    assert state.partial_snapshot is not None
    assert state.cache.kind == "Loading"

    assert state.on_loaded(snapshot(app("final", accessible=True)), is_final=True) is True
    assert state.prefetch_in_flight is False
    assert state.force_refetch_pending is False
    assert state.partial_snapshot is None
    assert [connector.id for connector in state.cache.snapshot.connectors] == ["final"]

    assert state.on_loaded("network failed", is_final=True) is False
    assert state.cache.kind == "Ready"


def test_on_loaded_error_falls_back_to_partial_before_failed_state():
    state = ConnectorsState(cache=ConnectorsCacheState.Loading(), partial_snapshot=snapshot(app("partial")))

    state.on_loaded("failed", is_final=True)
    assert state.cache.kind == "Ready"
    assert [connector.id for connector in state.cache.snapshot.connectors] == ["partial"]

    state = ConnectorsState(cache=ConnectorsCacheState.Loading())
    state.on_loaded("failed", is_final=True)
    assert state.cache == ConnectorsCacheState.Failed("failed")


def test_final_snapshot_preserves_existing_enabled_flags_and_update_enabled_changes_ready_cache():
    state = ConnectorsState(cache=ConnectorsCacheState.Ready(snapshot(app("drive", enabled=True))))

    state.on_loaded(snapshot(app("drive", enabled=False), app("mail", enabled=False)), is_final=True)
    assert [connector.is_enabled for connector in state.cache.snapshot.connectors] == [True, False]

    assert state.update_connector_enabled("drive", False) is True
    assert state.cache.snapshot.connectors[0].is_enabled is False
    assert state.update_connector_enabled("drive", False) is False
    assert state.update_connector_enabled("missing", True) is False


def test_widget_refresh_prefetch_and_disabled_output_paths() -> None:
    disabled = ConnectorsWidgetState(features_apps_enabled=False, has_chatgpt_account=True)
    disabled.refresh_connectors(force_refetch=True)
    disabled.add_connectors_output()

    assert disabled.sent_fetches == []
    assert disabled.info_messages == [("Apps are disabled.", "Enable the apps feature to use $ or /apps.")]

    widget = ConnectorsWidgetState()
    widget.prefetch_connectors()
    assert widget.sent_fetches == [False]
    assert widget.connectors.cache.kind == "Loading"


def test_widget_add_connectors_output_ready_empty_failed_and_loading_paths() -> None:
    ready = ConnectorsWidgetState(connectors=ConnectorsState(cache=ConnectorsCacheState.Ready(snapshot(app("drive")))))
    ready.add_connectors_output()
    assert ready.sent_fetches == [True]
    assert ready.shown_selection_views[-1]["items"][0]["id"] == "drive"
    assert ready.redraws == 1

    empty = ConnectorsWidgetState(connectors=ConnectorsState(cache=ConnectorsCacheState.Ready(snapshot())))
    empty.add_connectors_output()
    assert empty.info_messages == [("No apps available.", None)]

    failed = ConnectorsWidgetState(connectors=ConnectorsState(cache=ConnectorsCacheState.Failed("boom")))
    failed.add_connectors_output()
    assert failed.history == [{"kind": "error", "message": "boom"}]

    loading = ConnectorsWidgetState(replace_selection_view_result=False)
    loading.add_connectors_output()
    assert loading.shown_selection_views[-1]["items"][0]["name"] == "Loading apps..."


def test_widget_on_connectors_loaded_updates_bottom_snapshot_popup_and_pending_refetch() -> None:
    widget = ConnectorsWidgetState()
    widget.connectors.begin_refresh(connectors_enabled=True, force_refetch=False)
    widget.connectors.begin_refresh(connectors_enabled=True, force_refetch=True)

    widget.on_connectors_loaded(snapshot(app("partial", accessible=True)), is_final=False)
    assert widget.bottom_pane_snapshot.connectors[0].id == "partial"
    assert widget.connectors.partial_snapshot is not None

    widget.selected_index = 0
    widget.on_connectors_loaded(snapshot(app("final", accessible=True)), is_final=True)
    assert widget.connectors.cache.kind == "Ready"
    assert widget.bottom_pane_snapshot.connectors[0].id == "final"
    assert widget.sent_fetches == [True]
    assert widget.replaced_selection_views[-1][0] == "connectors"


def test_widget_on_connectors_loaded_error_retains_ready_or_falls_back_to_partial_or_failed() -> None:
    ready_snapshot = snapshot(app("ready"))
    ready = ConnectorsWidgetState(connectors=ConnectorsState(cache=ConnectorsCacheState.Ready(ready_snapshot)))
    ready.on_connectors_loaded("failed", is_final=True)
    assert ready.connectors.cache.snapshot is ready_snapshot
    assert ready.bottom_pane_snapshot is ready_snapshot

    partial_snapshot = snapshot(app("partial"))
    partial = ConnectorsWidgetState(connectors=ConnectorsState(cache=ConnectorsCacheState.Loading(), partial_snapshot=partial_snapshot))
    partial.on_connectors_loaded("failed", is_final=True)
    assert partial.connectors.cache.snapshot == partial_snapshot
    assert partial.bottom_pane_snapshot == partial_snapshot

    failed = ConnectorsWidgetState(connectors=ConnectorsState(cache=ConnectorsCacheState.Loading()))
    failed.on_connectors_loaded("failed", is_final=True)
    assert failed.connectors.cache == ConnectorsCacheState.Failed("failed")
    assert failed.bottom_pane_snapshot is None


def test_widget_update_connector_enabled_refreshes_popup_and_snapshot_only_on_change() -> None:
    widget = ConnectorsWidgetState(connectors=ConnectorsState(cache=ConnectorsCacheState.Ready(snapshot(app("drive", enabled=False)))))

    widget.update_connector_enabled("drive", True)

    assert widget.connectors.cache.snapshot.connectors[0].is_enabled is True
    assert widget.bottom_pane_snapshot.connectors[0].is_enabled is True
    assert widget.replaced_selection_views[-1][0] == "connectors"

    before = len(widget.replaced_selection_views)
    widget.update_connector_enabled("drive", True)
    assert len(widget.replaced_selection_views) == before
