from pathlib import Path
from types import SimpleNamespace

from pycodex.app_server import PluginStartupTasks
from pycodex.app_server.main import (
    AppServerArgsProjection,
    DISABLE_MANAGED_CONFIG_ENV_VAR,
    MANAGED_CONFIG_PATH_ENV_VAR,
    disable_managed_config_from_debug_env,
    loader_overrides_from_debug_env,
    main_runtime_call_projection,
    managed_config_path_from_debug_env,
)
from pycodex.protocol import SessionSource


def test_disable_managed_config_from_debug_env_matches_rust_truth_table() -> None:
    # Rust: codex-app-server/src/main.rs::disable_managed_config_from_debug_env.
    for value in ("1", "true", "TRUE", "yes", "YES"):
        assert disable_managed_config_from_debug_env({DISABLE_MANAGED_CONFIG_ENV_VAR: value}) is True

    for value in ("0", "false", "True", "YES ", ""):
        assert disable_managed_config_from_debug_env({DISABLE_MANAGED_CONFIG_ENV_VAR: value}) is False

    assert disable_managed_config_from_debug_env({}) is False


def test_managed_config_path_from_debug_env_empty_is_none() -> None:
    # Rust: codex-app-server/src/main.rs::managed_config_path_from_debug_env.
    assert managed_config_path_from_debug_env({}) is None
    assert managed_config_path_from_debug_env({MANAGED_CONFIG_PATH_ENV_VAR: ""}) is None
    assert managed_config_path_from_debug_env({MANAGED_CONFIG_PATH_ENV_VAR: "managed.toml"}) == Path(
        "managed.toml"
    )


def test_loader_overrides_debug_env_disable_takes_precedence() -> None:
    overrides = loader_overrides_from_debug_env(
        {
            DISABLE_MANAGED_CONFIG_ENV_VAR: "yes",
            MANAGED_CONFIG_PATH_ENV_VAR: "custom-managed.toml",
        }
    )

    assert str(overrides.managed_config_path).endswith("managed_config.toml")
    assert overrides.macos_managed_config_requirements_base64 == ""


def test_loader_overrides_debug_env_uses_managed_config_path() -> None:
    overrides = loader_overrides_from_debug_env({MANAGED_CONFIG_PATH_ENV_VAR: "custom-managed.toml"})

    assert overrides.managed_config_path == Path("custom-managed.toml")
    assert str(overrides.system_config_path).endswith("config.toml")


def test_main_runtime_call_projection_matches_rust_main_defaults() -> None:
    call = main_runtime_call_projection(arg0_paths="arg0", environ={})

    assert call.arg0_paths == "arg0"
    assert call.cli_config_overrides.raw_overrides == []
    assert call.loader_overrides.managed_config_path is None
    assert call.strict_config is False
    assert call.default_analytics_enabled is False
    assert call.transport == "stdio"
    assert call.session_source == SessionSource.vscode()
    assert call.auth == "default"
    assert call.runtime_options.plugin_startup_tasks is PluginStartupTasks.START
    assert call.runtime_options.remote_control_enabled is False


def test_main_runtime_call_projection_applies_cli_fields_and_auth_conversion() -> None:
    auth = SimpleNamespace(try_into_settings=lambda: {"auth": "settings"})
    args = AppServerArgsProjection(
        listen="ws://127.0.0.1:9999",
        session_source=SessionSource.cli(),
        auth=auth,
        strict_config=True,
        disable_plugin_startup_tasks_for_tests=True,
        remote_control=True,
    )

    call = main_runtime_call_projection(arg0_paths="arg0", args=args, environ={})

    assert call.transport == "websocket:127.0.0.1:9999"
    assert call.session_source == SessionSource.cli()
    assert call.auth == {"auth": "settings"}
    assert call.strict_config is True
    assert call.runtime_options.plugin_startup_tasks is PluginStartupTasks.SKIP
    assert call.runtime_options.remote_control_enabled is True


def test_main_runtime_call_projection_release_ignores_debug_plugin_skip() -> None:
    args = AppServerArgsProjection(disable_plugin_startup_tasks_for_tests=True)

    call = main_runtime_call_projection(arg0_paths="arg0", args=args, environ={}, debug_assertions=False)

    assert call.runtime_options.plugin_startup_tasks is PluginStartupTasks.START


def test_main_runtime_call_projection_projects_supported_listen_urls() -> None:
    assert main_runtime_call_projection("arg0", AppServerArgsProjection(listen="off"), environ={}).transport == "off"
    assert (
        main_runtime_call_projection("arg0", AppServerArgsProjection(listen="unix://"), environ={}).transport
        == "unix"
    )
    assert (
        main_runtime_call_projection("arg0", AppServerArgsProjection(listen="unix://socket"), environ={}).transport
        == "unix:socket"
    )
