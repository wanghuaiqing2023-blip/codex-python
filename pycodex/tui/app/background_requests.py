"""Semantic helpers for Rust ``codex-tui::app::background_requests``.

Upstream source: ``codex/codex-rs/tui/src/app/background_requests.rs``.

Rust launches app-server RPCs in background tasks and routes results back as
``AppEvent`` values.  Python models those launchers as deterministic request
plans so the module boundary is complete without requiring a live app-server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::background_requests",
    source="codex/codex-rs/tui/src/app/background_requests.rs",
    status="complete",
)

CLI_HIDDEN_PLUGIN_MARKETPLACES = ["openai-bundled"]


@dataclass(eq=True)
class PluginMarketplaceEntry:
    name: str
    path: Optional[str] = None
    interface: Any = None
    plugins: List[Any] = field(default_factory=list)


@dataclass(eq=True)
class PluginListResponse:
    marketplaces: List[Any] = field(default_factory=list)
    marketplace_load_errors: List[Any] = field(default_factory=list)
    featured_plugin_ids: List[str] = field(default_factory=list)


@dataclass(eq=True)
class FeedbackUploadParams:
    classification: str
    reason: Optional[str]
    thread_id: Optional[str]
    include_logs: bool
    extra_log_files: Optional[List[str]]
    tags: Optional[Dict[str, str]]


@dataclass(frozen=True, eq=True)
class BackgroundRequestPlan:
    request: str
    request_id_prefix: str
    params: Dict[str, Any] = field(default_factory=dict)
    error_context: Optional[str] = None
    completion_event: Optional[str] = None


@dataclass(frozen=True, eq=True)
class BackgroundAppEventPlan:
    event: str
    payload: Dict[str, Any] = field(default_factory=dict)


def _marketplace_name(entry: Any) -> Optional[str]:
    if isinstance(entry, dict):
        value = entry.get("name")
    else:
        value = getattr(entry, "name", None)
    return None if value is None else str(value)


def hide_cli_only_plugin_marketplaces(response: Any) -> None:
    """Remove marketplaces hidden from the CLI, matching Rust retain semantics."""

    marketplaces = getattr(response, "marketplaces", None)
    if marketplaces is None and isinstance(response, dict):
        marketplaces = response.get("marketplaces")
    if marketplaces is None:
        raise TypeError("response must expose a marketplaces list")
    kept = [entry for entry in marketplaces if _marketplace_name(entry) not in CLI_HIDDEN_PLUGIN_MARKETPLACES]
    if isinstance(response, dict):
        response["marketplaces"] = kept
    else:
        response.marketplaces = kept


def _split_marketplace_suffix(source: str) -> Tuple[str, Optional[str]]:
    hash_index = source.rfind("#")
    at_index = source.rfind("@")
    if hash_index != -1:
        return source[:hash_index], source[hash_index:]
    if at_index != -1:
        return source[:at_index], source[at_index:]
    return source, None


def _is_relative_local_marketplace_source(base_source: str) -> bool:
    return (
        base_source in {".", ".."}
        or base_source.startswith("./")
        or base_source.startswith("../")
        or base_source.startswith(".\\")
        or base_source.startswith("..\\")
    )


def marketplace_add_source_for_request(cwd: Any, source: str) -> str:
    """Resolve relative local marketplace sources against ``cwd``.

    Mirrors Rust's preservation of ``#ref``/``@ref`` suffixes and leaves owner,
    repo, tilde, and other non-dot-relative sources unchanged.
    """

    base_source, suffix = _split_marketplace_suffix(str(source))
    if not _is_relative_local_marketplace_source(base_source):
        return str(source)
    resolved = str((Path(cwd) / base_source).resolve())
    return resolved + (suffix or "")


def _feedback_classification(category: Any) -> str:
    if hasattr(category, "value"):
        category = category.value
    text = str(category)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    text = text.replace("-", "_")
    out = []
    for index, ch in enumerate(text):
        if ch.isupper() and index > 0 and (not text[index - 1].isupper()):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def build_feedback_upload_params(
    origin_thread_id: Optional[Any],
    rollout_path: Optional[Any],
    category: Any,
    reason: Optional[str],
    turn_id: Optional[str],
    include_logs: bool,
) -> FeedbackUploadParams:
    extra_log_files = [str(rollout_path)] if include_logs and rollout_path is not None else None
    tags = {"turn_id": turn_id} if turn_id is not None else None
    return FeedbackUploadParams(
        classification=_feedback_classification(category),
        reason=reason,
        thread_id=None if origin_thread_id is None else str(origin_thread_id),
        include_logs=include_logs,
        extra_log_files=extra_log_files,
        tags=tags,
    )


def mcp_inventory_maps_from_statuses(statuses: List[Any]) -> Tuple[Dict[str, Any], Dict[str, List[Any]], Dict[str, List[Any]], Dict[str, Any]]:
    tools = {}
    resources = {}
    resource_templates = {}
    auth_statuses = {}
    for status in statuses:
        if isinstance(status, dict):
            server_name = str(status["name"])
            status_tools = status.get("tools", {})
            status_resources = status.get("resources", [])
            status_resource_templates = status.get("resource_templates", [])
            auth_status = status.get("auth_status")
        else:
            server_name = str(status.name)
            status_tools = getattr(status, "tools", {})
            status_resources = getattr(status, "resources", [])
            status_resource_templates = getattr(status, "resource_templates", [])
            auth_status = getattr(status, "auth_status", None)
        resources[server_name] = list(status_resources)
        resource_templates[server_name] = list(status_resource_templates)
        auth_statuses[server_name] = auth_status
        for tool_name, tool in dict(status_tools).items():
            tools["mcp__%s__%s" % (server_name, tool_name)] = tool
    return tools, resources, resource_templates, auth_statuses


def _ensure_absolute_path(path: Any, context: str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError(context)
    return str(candidate)


def _plan(request: str, request_id_prefix: str, params: Optional[Dict[str, Any]] = None, error_context: Optional[str] = None, completion_event: Optional[str] = None) -> BackgroundRequestPlan:
    return BackgroundRequestPlan(
        request=request,
        request_id_prefix=request_id_prefix,
        params=params or {},
        error_context=error_context,
        completion_event=completion_event,
    )


async def fetch_all_mcp_server_statuses(request_handle: Any, detail: Any, thread_id: Optional[Any] = None) -> BackgroundRequestPlan:
    del request_handle
    return _plan(
        "McpListTools",
        "mcp-inventory",
        {"detail": detail, "thread_id": None if thread_id is None else str(thread_id)},
        "mcp/list failed in TUI",
        "McpInventoryLoaded",
    )


async def fetch_account_rate_limits(request_handle: Any) -> BackgroundRequestPlan:
    del request_handle
    return _plan("GetAccountRateLimits", "account-rate-limits", {}, "account/rateLimits/read failed in TUI", "RateLimitsLoaded")


async def send_add_credits_nudge_email(request_handle: Any, credit_type: Any) -> BackgroundRequestPlan:
    del request_handle
    return _plan(
        "SendAddCreditsNudgeEmail",
        "add-credits-nudge",
        {"credit_type": credit_type},
        "account/sendAddCreditsNudgeEmail failed in TUI",
        "AddCreditsNudgeEmailFinished",
    )


async def fetch_skills_list(request_handle: Any, cwd: Any) -> BackgroundRequestPlan:
    del request_handle
    return _plan("SkillsList", "startup-skills-list", {"cwds": [str(cwd)], "force_reload": True}, "skills/list failed in TUI", "SkillsListLoaded")


async def fetch_connectors_list(request_handle: Any, force_refetch: bool, thread_id: Optional[str] = None) -> BackgroundRequestPlan:
    del request_handle
    return _plan(
        "AppsList",
        "apps-list",
        {"cursor": None, "limit": None, "thread_id": thread_id, "force_refetch": force_refetch},
        "app/list failed in TUI",
        "ConnectorsLoaded",
    )


async def request_plugin_list(request_handle: Any, cwd: Any) -> BackgroundRequestPlan:
    del request_handle
    absolute_cwd = _ensure_absolute_path(cwd, "plugin list cwd must be absolute")
    return _plan(
        "PluginList",
        "plugin-list",
        {"cwds": [absolute_cwd], "marketplace_kinds": None},
        "plugin/list failed in TUI",
    )


async def fetch_plugins_list(request_handle: Any, cwd: Any) -> BackgroundRequestPlan:
    plan = await request_plugin_list(request_handle, cwd)
    return _plan(plan.request, plan.request_id_prefix, plan.params, "plugin/list failed while loading the plugins menu", "PluginsLoaded")


async def fetch_plugin_detail(request_handle: Any, params: Any) -> BackgroundRequestPlan:
    del request_handle
    return _plan("PluginRead", "plugin-read", {"params": params}, "plugin/read failed in TUI", "PluginDetailLoaded")


async def fetch_marketplace_add(request_handle: Any, cwd: Any, source: str) -> BackgroundRequestPlan:
    del request_handle
    absolute_cwd = _ensure_absolute_path(cwd, "marketplace/add cwd must be absolute")
    return _plan(
        "MarketplaceAdd",
        "marketplace-add",
        {"source": marketplace_add_source_for_request(absolute_cwd, source), "ref_name": None, "sparse_paths": None},
        "marketplace/add failed in TUI",
        "MarketplaceAddLoaded",
    )


async def fetch_marketplace_remove(request_handle: Any, marketplace_name: str) -> BackgroundRequestPlan:
    del request_handle
    return _plan("MarketplaceRemove", "marketplace-remove", {"marketplace_name": marketplace_name}, "marketplace/remove failed in TUI", "MarketplaceRemoveLoaded")


async def fetch_marketplace_upgrade(request_handle: Any, marketplace_name: Optional[str] = None) -> BackgroundRequestPlan:
    del request_handle
    return _plan("MarketplaceUpgrade", "marketplace-upgrade", {"marketplace_name": marketplace_name}, "marketplace/upgrade failed in TUI", "MarketplaceUpgradeLoaded")


async def fetch_plugin_install(request_handle: Any, marketplace_path: Any, plugin_name: str) -> BackgroundRequestPlan:
    del request_handle
    return _plan(
        "PluginInstall",
        "plugin-install",
        {"marketplace_path": str(marketplace_path), "remote_marketplace_name": None, "plugin_name": plugin_name},
        "plugin/install failed in TUI",
        "PluginInstallLoaded",
    )


async def fetch_plugin_uninstall(request_handle: Any, plugin_id: str) -> BackgroundRequestPlan:
    del request_handle
    return _plan("PluginUninstall", "plugin-uninstall", {"plugin_id": plugin_id}, "plugin/uninstall failed in TUI", "PluginUninstallLoaded")


async def write_plugin_enabled(request_handle: Any, plugin_id: str, enabled: bool) -> BackgroundRequestPlan:
    del request_handle
    return _plan(
        "ConfigValueWrite",
        "plugin-enable",
        {"key_path": "plugins.%s" % plugin_id, "value": {"enabled": enabled}, "merge_strategy": "Upsert"},
        "config/value/write failed while updating plugin enablement in TUI",
        "PluginEnabledSet",
    )


async def write_hook_enabled(request_handle: Any, key: str, enabled: bool) -> BackgroundRequestPlan:
    del request_handle
    return _plan(
        "ConfigBatchWrite",
        "hooks-config-write",
        {"edits": [{"key_path": "hooks.state", "value": {key: {"enabled": enabled}}, "merge_strategy": "Upsert"}], "reload_user_config": True},
        "config/batchWrite failed while updating hook enablement in TUI",
        "HookEnabledSet",
    )


async def fetch_feedback_upload(request_handle: Any, params: FeedbackUploadParams) -> BackgroundRequestPlan:
    del request_handle
    return _plan("FeedbackUpload", "feedback-upload", {"params": params}, "feedback/upload failed in TUI", "FeedbackSubmitted")


__all__ = [
    "BackgroundAppEventPlan",
    "BackgroundRequestPlan",
    "CLI_HIDDEN_PLUGIN_MARKETPLACES",
    "FeedbackUploadParams",
    "PluginListResponse",
    "PluginMarketplaceEntry",
    "RUST_MODULE",
    "build_feedback_upload_params",
    "fetch_account_rate_limits",
    "fetch_all_mcp_server_statuses",
    "fetch_connectors_list",
    "fetch_feedback_upload",
    "fetch_marketplace_add",
    "fetch_marketplace_remove",
    "fetch_marketplace_upgrade",
    "fetch_plugin_detail",
    "fetch_plugin_install",
    "fetch_plugin_uninstall",
    "fetch_plugins_list",
    "fetch_skills_list",
    "hide_cli_only_plugin_marketplaces",
    "marketplace_add_source_for_request",
    "mcp_inventory_maps_from_statuses",
    "request_plugin_list",
    "send_add_credits_nudge_email",
    "write_hook_enabled",
    "write_plugin_enabled",
]
