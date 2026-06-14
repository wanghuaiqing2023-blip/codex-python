"""Semantic helpers for Rust ``codex-tui::app::background_requests``.

Upstream source: ``codex/codex-rs/tui/src/app/background_requests.rs``.

Most functions in the Rust module are app-server RPC launchers.  Python keeps
those runtime boundaries explicit with ``not_ported`` while porting the pure
module-owned helpers covered by Rust unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::background_requests",
    source="codex/codex-rs/tui/src/app/background_requests.rs",
)

CLI_HIDDEN_PLUGIN_MARKETPLACES = ["openai-bundled"]


@dataclass(eq=True)
class PluginMarketplaceEntry:
    name: str
    path: str | None = None
    interface: Any | None = None
    plugins: list[Any] = field(default_factory=list)


@dataclass(eq=True)
class PluginListResponse:
    marketplaces: list[Any] = field(default_factory=list)
    marketplace_load_errors: list[Any] = field(default_factory=list)
    featured_plugin_ids: list[str] = field(default_factory=list)


@dataclass(eq=True)
class FeedbackUploadParams:
    classification: str
    reason: str | None
    thread_id: str | None
    include_logs: bool
    extra_log_files: list[str] | None
    tags: dict[str, str] | None


def _marketplace_name(entry: Any) -> str | None:
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


def _split_marketplace_suffix(source: str) -> tuple[str, str | None]:
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
        or base_source.startswith(r".\")
        or base_source.startswith(r"..\")
    )


def marketplace_add_source_for_request(cwd: str | Path, source: str) -> str:
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
    out: list[str] = []
    for index, ch in enumerate(text):
        if ch.isupper() and index > 0 and (not text[index - 1].isupper()):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def build_feedback_upload_params(
    origin_thread_id: Any | None,
    rollout_path: str | Path | None,
    category: Any,
    reason: str | None,
    turn_id: str | None,
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


def mcp_inventory_maps_from_statuses(statuses: list[Any]) -> tuple[dict[str, Any], dict[str, list[Any]], dict[str, list[Any]], dict[str, Any]]:
    tools: dict[str, Any] = {}
    resources: dict[str, list[Any]] = {}
    resource_templates: dict[str, list[Any]] = {}
    auth_statuses: dict[str, Any] = {}
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
            tools[f"mcp__{server_name}__{tool_name}"] = tool
    return tools, resources, resource_templates, auth_statuses


async def fetch_all_mcp_server_statuses(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_all_mcp_server_statuses app-server RPC is not ported")


async def fetch_account_rate_limits(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_account_rate_limits app-server RPC is not ported")


async def send_add_credits_nudge_email(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.send_add_credits_nudge_email app-server RPC is not ported")


async def fetch_skills_list(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_skills_list app-server RPC is not ported")


async def fetch_connectors_list(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_connectors_list app-server RPC is not ported")


async def fetch_plugins_list(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_plugins_list app-server RPC is not ported")


async def request_plugin_list(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.request_plugin_list app-server RPC is not ported")


async def fetch_plugin_detail(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_plugin_detail app-server RPC is not ported")


async def fetch_marketplace_add(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_marketplace_add app-server RPC is not ported")


async def fetch_marketplace_remove(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_marketplace_remove app-server RPC is not ported")


async def fetch_marketplace_upgrade(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_marketplace_upgrade app-server RPC is not ported")


async def fetch_plugin_install(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_plugin_install app-server RPC is not ported")


async def fetch_plugin_uninstall(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_plugin_uninstall app-server RPC is not ported")


async def write_plugin_enabled(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.write_plugin_enabled app-server RPC is not ported")


async def write_hook_enabled(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.write_hook_enabled app-server RPC is not ported")


async def fetch_feedback_upload(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::background_requests.fetch_feedback_upload app-server RPC is not ported")


__all__ = [
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
