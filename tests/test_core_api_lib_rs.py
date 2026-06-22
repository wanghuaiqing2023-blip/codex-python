import pycodex.core_api as core_api


def test_core_api_reexports_existing_facade_targets() -> None:
    # Rust crate: codex-core-api
    # Rust module: src/lib.rs
    # Contract: public facade re-exports selected app-server, arg0, config,
    # core, exec-server, features, model-provider, protocol, and absolute-path
    # symbols.
    from pycodex import app_server_protocol, arg0, config, core, exec_server, features, model_provider_info, protocol
    from pycodex.utils.absolute_path import AbsolutePathBuf

    assert core_api.ServerNotification is app_server_protocol.ServerNotification
    assert core_api.item_event_to_server_notification is app_server_protocol.item_event_to_server_notification
    assert core_api.Arg0DispatchPaths is arg0.Arg0DispatchPaths
    assert core_api.arg0_dispatch_or_else is arg0.arg0_dispatch_or_else
    assert core_api.ConfigLayerStack is config.ConfigLayerStack
    assert core_api.ProjectConfig is config.ProjectConfig
    assert core_api.CodexThread is core.CodexThread
    assert core_api.ThreadManager is core.ThreadManager
    assert core_api.EnvironmentManager is exec_server.EnvironmentManager
    assert core_api.ExecServerRuntimePaths is exec_server.ExecServerRuntimePaths
    assert core_api.Feature is features.Feature
    assert core_api.Features is features.Features
    assert core_api.OPENAI_PROVIDER_ID == model_provider_info.OPENAI_PROVIDER_ID
    assert core_api.ThreadId is protocol.ThreadId
    assert core_api.SessionSource is protocol.SessionSource
    assert core_api.UserInput is protocol.UserInput
    assert core_api.AbsolutePathBuf is AbsolutePathBuf


def test_core_api_exports_rust_lib_rs_symbol_names() -> None:
    # Rust crate: codex-core-api
    # Rust module: src/lib.rs
    # Contract: all Rust pub-use names are importable from the Python facade.
    expected = {
        "AnalyticsEventsClient",
        "ServerNotification",
        "item_event_to_server_notification",
        "Arg0DispatchPaths",
        "arg0_dispatch_or_else",
        "ConfigLayerStack",
        "ProjectConfig",
        "RealtimeAudioConfig",
        "RealtimeConfig",
        "AuthCredentialsStoreMode",
        "History",
        "MemoriesConfig",
        "ModelAvailabilityNuxConfig",
        "Notice",
        "OAuthCredentialsStoreMode",
        "OtelConfig",
        "SessionPickerViewMode",
        "ToolSuggestConfig",
        "TuiKeymap",
        "TuiNotificationSettings",
        "TuiPetAnchor",
        "UriBasedFileOpener",
        "CodexThread",
        "ForkSnapshot",
        "McpManager",
        "NewThread",
        "StartThreadOptions",
        "StateDbHandle",
        "ThreadManager",
        "ThreadShutdownReport",
        "Config",
        "Constrained",
        "GhostSnapshotConfig",
        "MultiAgentV2Config",
        "Permissions",
        "TerminalResizeReflowConfig",
        "ThreadStoreConfig",
        "find_codex_home",
        "init_state_db",
        "resolve_installation_id",
        "SkillsManager",
        "thread_store_from_config",
        "EnvironmentManager",
        "ExecServerRuntimePaths",
        "empty_extension_registry",
        "Feature",
        "Features",
        "AuthManager",
        "set_default_originator",
        "OPENAI_PROVIDER_ID",
        "built_in_model_providers",
        "RefreshStrategy",
        "SharedModelsManager",
        "ThreadId",
        "AltScreenMode",
        "ApprovalsReviewer",
        "AutoCompactTokenLimitScope",
        "CollaborationModeMask",
        "ShellEnvironmentPolicy",
        "WebSearchMode",
        "DynamicToolSpec",
        "CodexResult",
        "PermissionProfile",
        "ModelPreset",
        "AskForApproval",
        "EventMsg",
        "InitialHistory",
        "McpServerRefreshConfig",
        "Op",
        "SessionConfiguredEvent",
        "SessionSource",
        "TurnEnvironmentSelection",
        "W3cTraceContext",
        "UserInput",
        "AbsolutePathBuf",
    }

    assert expected.issubset(set(core_api.__all__))
    for name in expected:
        assert hasattr(core_api, name), name


def test_core_api_placeholders_are_explicit_facade_types() -> None:
    # Rust crate: codex-core-api
    # Rust module: src/lib.rs
    # Contract: neighboring not-yet-ported concrete types are still explicit
    # facade exports rather than missing names.
    assert core_api.Constrained("value").value == "value"
    assert core_api.MultiAgentV2Config().enabled is False
    assert core_api.Permissions().value is None
    assert core_api.TerminalResizeReflowConfig().enabled is True
    assert core_api.SkillsManager.__name__ == "SkillsManager"
    assert core_api.AuthManager.__name__ == "AuthManager"
    assert core_api.SharedModelsManager.__name__ == "SharedModelsManager"
