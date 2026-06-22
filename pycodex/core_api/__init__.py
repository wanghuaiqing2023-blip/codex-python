"""Public facade for thread management APIs ported from ``codex-rs/core-api``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.analytics import AnalyticsEventsClient
from pycodex.app_server_protocol import ServerNotification, item_event_to_server_notification
from pycodex.arg0 import Arg0DispatchPaths, arg0_dispatch_or_else
from pycodex.config import (
    AuthCredentialsStoreMode,
    ConfigLayerStack,
    History,
    MemoriesConfig,
    ModelAvailabilityNuxConfig,
    Notice,
    OAuthCredentialsStoreMode,
    OtelConfig,
    ProjectConfig,
    RealtimeAudioConfig,
    RealtimeConfig,
    SessionPickerViewMode,
    ToolSuggestConfig,
    TuiKeymap,
    TuiNotificationSettings,
    TuiPetAnchor,
    UriBasedFileOpener,
)
from pycodex.core import (
    CodexThread,
    ForkSnapshot,
    McpManager,
    NewThread,
    StartThreadOptions,
    StateDbHandle,
    ThreadManager,
    ThreadShutdownReport,
    find_codex_home,
    init_state_db,
    resolve_installation_id,
    thread_store_from_config,
)
from pycodex.core import Config
from pycodex.core.config import GhostSnapshotConfig, ThreadStoreConfig
from pycodex.exec_server import EnvironmentManager, ExecServerRuntimePaths
from pycodex.extension_api import empty_extension_registry
from pycodex.features import Feature, Features
from pycodex.login.auth.default_client import set_default_originator
from pycodex.model_provider_info import OPENAI_PROVIDER_ID, built_in_model_providers
from pycodex.models_manager.manager import RefreshStrategy
from pycodex.protocol import (
    AltScreenMode,
    ApprovalsReviewer,
    AskForApproval,
    AutoCompactTokenLimitScope,
    CollaborationModeMask,
    DynamicToolSpec,
    EventMsg,
    InitialHistory,
    McpServerRefreshConfig,
    ModelPreset,
    Op,
    PermissionProfile,
    SessionConfiguredEvent,
    SessionSource,
    ShellEnvironmentPolicy,
    ThreadId,
    TurnEnvironmentSelection,
    UserInput,
    W3cTraceContext,
    WebSearchMode,
)
from pycodex.utils.absolute_path import AbsolutePathBuf


@dataclass(frozen=True)
class Constrained:
    """Facade placeholder for ``codex_core::config::Constrained``."""

    value: Any = None


@dataclass(frozen=True)
class MultiAgentV2Config:
    """Facade placeholder for ``codex_core::config::MultiAgentV2Config``."""

    enabled: bool = False


@dataclass(frozen=True)
class Permissions:
    """Facade placeholder for ``codex_core::config::Permissions``."""

    value: Any = None


@dataclass(frozen=True)
class TerminalResizeReflowConfig:
    """Facade placeholder for ``codex_core::config::TerminalResizeReflowConfig``."""

    enabled: bool = True


class SkillsManager:
    """Facade placeholder for ``codex_core::skills::SkillsManager``."""


class AuthManager:
    """Facade placeholder for ``codex_login::AuthManager``."""


class SharedModelsManager:
    """Facade placeholder for ``codex_models_manager::manager::SharedModelsManager``."""


__all__ = [
    "AbsolutePathBuf",
    "AltScreenMode",
    "AnalyticsEventsClient",
    "ApprovalsReviewer",
    "Arg0DispatchPaths",
    "AskForApproval",
    "AuthCredentialsStoreMode",
    "AuthManager",
    "AutoCompactTokenLimitScope",
    "CodexResult",
    "CodexThread",
    "CollaborationModeMask",
    "Config",
    "ConfigLayerStack",
    "Constrained",
    "DynamicToolSpec",
    "EnvironmentManager",
    "EventMsg",
    "ExecServerRuntimePaths",
    "Feature",
    "Features",
    "ForkSnapshot",
    "GhostSnapshotConfig",
    "History",
    "InitialHistory",
    "McpManager",
    "McpServerRefreshConfig",
    "MemoriesConfig",
    "ModelAvailabilityNuxConfig",
    "ModelPreset",
    "MultiAgentV2Config",
    "NewThread",
    "Notice",
    "OPENAI_PROVIDER_ID",
    "OAuthCredentialsStoreMode",
    "Op",
    "OtelConfig",
    "PermissionProfile",
    "Permissions",
    "ProjectConfig",
    "RealtimeAudioConfig",
    "RealtimeConfig",
    "RefreshStrategy",
    "ServerNotification",
    "SessionConfiguredEvent",
    "SessionPickerViewMode",
    "SessionSource",
    "SharedModelsManager",
    "ShellEnvironmentPolicy",
    "SkillsManager",
    "StartThreadOptions",
    "StateDbHandle",
    "TerminalResizeReflowConfig",
    "ThreadId",
    "ThreadManager",
    "ThreadShutdownReport",
    "ThreadStoreConfig",
    "ToolSuggestConfig",
    "TuiKeymap",
    "TuiNotificationSettings",
    "TuiPetAnchor",
    "TurnEnvironmentSelection",
    "UriBasedFileOpener",
    "UserInput",
    "W3cTraceContext",
    "WebSearchMode",
    "arg0_dispatch_or_else",
    "built_in_model_providers",
    "empty_extension_registry",
    "find_codex_home",
    "init_state_db",
    "item_event_to_server_notification",
    "resolve_installation_id",
    "set_default_originator",
    "thread_store_from_config",
]

CodexResult = object
