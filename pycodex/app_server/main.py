"""CLI entrypoint projection for Rust ``codex-app-server/src/main.rs``."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from pycodex.config import CliConfigOverrides, LoaderOverrides
from pycodex.protocol import SessionSource

from . import AppServerRuntimeOptions, PluginStartupTasks, RunMainWithTransportOptionsCall


MANAGED_CONFIG_PATH_ENV_VAR = "CODEX_APP_SERVER_MANAGED_CONFIG_PATH"
DISABLE_MANAGED_CONFIG_ENV_VAR = "CODEX_APP_SERVER_DISABLE_MANAGED_CONFIG"
DEFAULT_LISTEN_URL = "stdio://"


@dataclass(frozen=True)
class AppServerArgsProjection:
    """Rust ``AppServerArgs`` fields that shape app-server startup."""

    listen: str = DEFAULT_LISTEN_URL
    session_source: SessionSource = SessionSource.vscode()
    auth: Any = "default"
    strict_config: bool = False
    disable_plugin_startup_tasks_for_tests: bool = False
    remote_control: bool = False


def disable_managed_config_from_debug_env(environ: Mapping[str, str] | None = None) -> bool:
    """Mirror Rust's debug env truth table for disabling managed config."""

    source = os.environ if environ is None else environ
    value = source.get(DISABLE_MANAGED_CONFIG_ENV_VAR)
    return value in {"1", "true", "TRUE", "yes", "YES"}


def managed_config_path_from_debug_env(environ: Mapping[str, str] | None = None) -> Path | None:
    """Mirror Rust's debug env path hook for integration tests."""

    source = os.environ if environ is None else environ
    value = source.get(MANAGED_CONFIG_PATH_ENV_VAR)
    if value is None or value == "":
        return None
    return Path(value)


def loader_overrides_from_debug_env(environ: Mapping[str, str] | None = None) -> LoaderOverrides:
    """Mirror Rust ``main.rs`` managed-config override selection."""

    if disable_managed_config_from_debug_env(environ):
        return LoaderOverrides.without_managed_config_for_tests()

    managed_path = managed_config_path_from_debug_env(environ)
    if managed_path is not None:
        return LoaderOverrides.with_managed_config_path_for_tests(managed_path)

    return LoaderOverrides()


def main_runtime_call_projection(
    arg0_paths: Any,
    args: AppServerArgsProjection | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    debug_assertions: bool = True,
) -> RunMainWithTransportOptionsCall:
    """Project Rust ``main`` argument/env shaping before runtime startup."""

    app_args = args or AppServerArgsProjection()
    runtime_options = AppServerRuntimeOptions(remote_control_enabled=app_args.remote_control)
    if debug_assertions and app_args.disable_plugin_startup_tasks_for_tests:
        runtime_options = replace(runtime_options, plugin_startup_tasks=PluginStartupTasks.SKIP)

    return RunMainWithTransportOptionsCall(
        arg0_paths=arg0_paths,
        cli_config_overrides=CliConfigOverrides(),
        loader_overrides=loader_overrides_from_debug_env(environ),
        strict_config=app_args.strict_config,
        default_analytics_enabled=False,
        transport=_transport_from_listen_projection(app_args.listen),
        session_source=app_args.session_source,
        auth=_auth_settings_projection(app_args.auth),
        runtime_options=runtime_options,
    )


def _transport_from_listen_projection(listen: str) -> str:
    if listen == DEFAULT_LISTEN_URL:
        return "stdio"
    if listen == "off":
        return "off"
    if listen.startswith("unix://"):
        raw_path = listen.removeprefix("unix://")
        return "unix" if raw_path == "" else f"unix:{raw_path}"
    if listen.startswith("ws://"):
        return f"websocket:{listen.removeprefix('ws://')}"
    raise ValueError(
        "unsupported --listen URL; expected `stdio://`, `unix://`, `unix://PATH`, "
        "`ws://IP:PORT`, or `off`"
    )


def _auth_settings_projection(auth: Any) -> Any:
    try_into_settings = getattr(auth, "try_into_settings", None)
    if callable(try_into_settings):
        return try_into_settings()
    return auth


__all__ = [
    "AppServerArgsProjection",
    "DEFAULT_LISTEN_URL",
    "DISABLE_MANAGED_CONFIG_ENV_VAR",
    "MANAGED_CONFIG_PATH_ENV_VAR",
    "disable_managed_config_from_debug_env",
    "loader_overrides_from_debug_env",
    "main_runtime_call_projection",
    "managed_config_path_from_debug_env",
]
