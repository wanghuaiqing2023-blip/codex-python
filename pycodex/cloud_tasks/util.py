"""Port of Rust ``codex-cloud-tasks/src/util.rs``."""

from __future__ import annotations

from datetime import datetime, timezone
import inspect
from pathlib import Path
from typing import Any, Mapping

from pycodex.config import ConfigToml
from pycodex.core.config.edit import CONFIG_TOML_FILE, read_toml_mapping
from pycodex.login.auth import default_client
from pycodex.login.auth.manager import AuthManager
from pycodex.model_provider import auth_provider_from_auth
from pycodex.utils.home_dir import find_codex_home


def normalize_base_url(input_url: str) -> str:
    base_url = input_url
    while base_url.endswith("/"):
        base_url = base_url[:-1]
    if (
        base_url.startswith("https://chatgpt.com")
        or base_url.startswith("https://chat.openai.com")
    ) and "/backend-api" not in base_url:
        base_url = f"{base_url}/backend-api"
    return base_url


def append_error_log(message: object) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with open("error.log", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except OSError:
        return


def set_user_agent_suffix(suffix: str) -> None:
    default_client.set_user_agent_suffix(suffix)


async def load_auth_manager(chatgpt_base_url: str | None = None) -> Any | None:
    try:
        codex_home = find_codex_home()
        config_toml = ConfigToml.from_mapping(
            read_toml_mapping(Path(codex_home) / CONFIG_TOML_FILE)
        )
        store_mode = config_toml.cli_auth_credentials_store or "file"
        resolved_chatgpt_base_url = chatgpt_base_url or config_toml.chatgpt_base_url
        return await AuthManager.new(
            Path(codex_home),
            False,
            _enum_value(store_mode),
            resolved_chatgpt_base_url,
        )
    except Exception:
        return None


async def build_chatgpt_headers(auth_manager: Any | None = None) -> dict[str, str]:
    set_user_agent_suffix("codex_cloud_tasks_tui")
    headers = {
        default_client.USER_AGENT_HEADER_NAME: default_client.get_codex_user_agent()
    }

    manager = auth_manager
    if manager is None:
        manager = await load_auth_manager(None)
    auth = await _auth_from_manager(manager)
    if auth is not None and _auth_uses_codex_backend(auth):
        headers.update(auth_provider_from_auth(auth).to_auth_headers())
    return headers


def task_url(base_url: str, task_id: str) -> str:
    normalized = normalize_base_url(base_url)
    if normalized.endswith("/backend-api"):
        return f"{normalized[:-len('/backend-api')]}/codex/tasks/{task_id}"
    if normalized.endswith("/api/codex"):
        return f"{normalized[:-len('/api/codex')]}/codex/tasks/{task_id}"
    if normalized.endswith("/codex"):
        return f"{normalized}/tasks/{task_id}"
    return f"{normalized}/codex/tasks/{task_id}"


def format_relative_time(reference: datetime, ts: datetime | float) -> str:
    if isinstance(ts, (int, float)):
        ts = datetime.fromtimestamp(ts, tz=timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    secs = int((reference - ts).total_seconds())
    if secs < 0:
        secs = 0
    if secs < 60:
        return f"{secs}s ago"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    local = ts.astimezone()
    return f"{local.strftime('%b')} {local.day:2d} {local.strftime('%H:%M')}"


async def _auth_from_manager(auth_manager: Any | None) -> Any | None:
    if auth_manager is None:
        return None
    auth_method = getattr(auth_manager, "auth", None)
    if not callable(auth_method):
        return None
    auth = auth_method()
    if inspect.isawaitable(auth):
        auth = await auth
    return auth


def _auth_uses_codex_backend(auth: Any) -> bool:
    uses = getattr(auth, "uses_codex_backend", None)
    if callable(uses):
        return bool(uses())
    if isinstance(auth, Mapping):
        return bool(auth.get("uses_codex_backend"))
    return bool(getattr(auth, "uses_codex_backend", False))


def _auth_account_id(auth: Any) -> str | None:
    getter = getattr(auth, "get_account_id", None)
    if callable(getter):
        value = getter()
    elif isinstance(auth, Mapping):
        value = auth.get("account_id")
    else:
        value = getattr(auth, "account_id", None)
    return None if value is None else str(value)


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw)
