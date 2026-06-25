from __future__ import annotations

import asyncio
from pathlib import Path

from pycodex.tui.app.background_requests import (
    BackgroundRequestPlan,
    FeedbackUploadParams,
    PluginListResponse,
    PluginMarketplaceEntry,
    build_feedback_upload_params,
    fetch_account_rate_limits,
    fetch_connectors_list,
    hide_cli_only_plugin_marketplaces,
    marketplace_add_source_for_request,
    fetch_marketplace_add,
    request_plugin_list,
    write_plugin_enabled,
    mcp_inventory_maps_from_statuses,
)


def test_marketplace_add_source_for_request_resolves_relative_local_paths(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()

    resolved = marketplace_add_source_for_request(cwd, "./marketplace")
    assert Path(resolved).is_absolute()
    assert resolved == str((cwd / "marketplace").resolve())
    assert marketplace_add_source_for_request(cwd, "./marketplace#main") == f"{(cwd / 'marketplace').resolve()}#main"
    assert marketplace_add_source_for_request(cwd, "../marketplace@dev") == f"{(cwd / '../marketplace').resolve()}@dev"
    assert marketplace_add_source_for_request(cwd, "owner/repo") == "owner/repo"
    assert marketplace_add_source_for_request(cwd, "~/marketplace") == "~/marketplace"


def test_hide_cli_only_plugin_marketplaces_removes_openai_bundled() -> None:
    response = PluginListResponse(
        marketplaces=[
            PluginMarketplaceEntry("openai-bundled", "/marketplaces/openai-bundled"),
            PluginMarketplaceEntry("openai-curated", "/marketplaces/openai-curated"),
        ]
    )

    hide_cli_only_plugin_marketplaces(response)

    assert response.marketplaces == [PluginMarketplaceEntry("openai-curated", "/marketplaces/openai-curated")]


def test_mcp_inventory_maps_prefix_tool_names_by_server() -> None:
    statuses = [
        {
            "name": "docs",
            "tools": {"list": {"name": "list", "input_schema": {"type": "object"}}},
            "resources": [],
            "resource_templates": [],
            "auth_status": "Unsupported",
        },
        {
            "name": "disabled",
            "tools": {},
            "resources": [],
            "resource_templates": [],
            "auth_status": "Unsupported",
        },
    ]

    tools, resources, resource_templates, auth_statuses = mcp_inventory_maps_from_statuses(statuses)

    assert list(tools) == ["mcp__docs__list"]
    assert sorted(resources) == ["disabled", "docs"]
    assert sorted(resource_templates) == ["disabled", "docs"]
    assert auth_statuses["disabled"] == "Unsupported"


def test_build_feedback_upload_params_includes_thread_id_and_rollout_path() -> None:
    params = build_feedback_upload_params(
        "thread-1",
        "/tmp/rollout.jsonl",
        "SafetyCheck",
        "needs follow-up",
        "turn-123",
        True,
    )

    assert params == FeedbackUploadParams(
        classification="safety_check",
        reason="needs follow-up",
        thread_id="thread-1",
        include_logs=True,
        extra_log_files=["/tmp/rollout.jsonl"],
        tags={"turn_id": "turn-123"},
    )


def test_build_feedback_upload_params_omits_rollout_path_without_logs() -> None:
    params = build_feedback_upload_params(None, "/tmp/rollout.jsonl", "GoodResult", None, None, False)

    assert params == FeedbackUploadParams(
        classification="good_result",
        reason=None,
        thread_id=None,
        include_logs=False,
        extra_log_files=None,
        tags=None,
    )


def test_request_plugin_list_plans_absolute_cwd_rpc(tmp_path: Path) -> None:
    plan = asyncio.run(request_plugin_list(object(), tmp_path))

    assert plan == BackgroundRequestPlan(
        request="PluginList",
        request_id_prefix="plugin-list",
        params={"cwds": [str(tmp_path)], "marketplace_kinds": None},
        error_context="plugin/list failed in TUI",
    )


def test_rate_limits_and_connectors_launchers_include_completion_metadata() -> None:
    """Rust codex-tui app::background_requests refresh_rate_limits/fetch_connectors_list events."""

    rate_limits = asyncio.run(fetch_account_rate_limits(object()))
    connectors = asyncio.run(fetch_connectors_list(object(), True, "thread-1"))

    assert rate_limits == BackgroundRequestPlan(
        request="GetAccountRateLimits",
        request_id_prefix="account-rate-limits",
        params={},
        error_context="account/rateLimits/read failed in TUI",
        completion_event="RateLimitsLoaded",
    )
    assert connectors == BackgroundRequestPlan(
        request="AppsList",
        request_id_prefix="apps-list",
        params={"cursor": None, "limit": None, "thread_id": "thread-1", "force_refetch": True},
        error_context="app/list failed in TUI",
        completion_event="ConnectorsLoaded",
    )


def test_marketplace_add_and_plugin_enabled_write_are_semantic_rpc_plans(tmp_path: Path) -> None:
    add = asyncio.run(fetch_marketplace_add(object(), tmp_path, "./marketplace#main"))
    assert add.request == "MarketplaceAdd"
    assert add.request_id_prefix == "marketplace-add"
    assert add.params["source"] == f"{(tmp_path / 'marketplace').resolve()}#main"
    assert add.completion_event == "MarketplaceAddLoaded"

    write = asyncio.run(write_plugin_enabled(object(), "sample", False))
    assert write == BackgroundRequestPlan(
        request="ConfigValueWrite",
        request_id_prefix="plugin-enable",
        params={
            "key_path": "plugins.sample",
            "value": {"enabled": False},
            "merge_strategy": "Upsert",
        },
        error_context="config/value/write failed while updating plugin enablement in TUI",
        completion_event="PluginEnabledSet",
    )
