"""V1 app-server protocol types ported from ``protocol/v1.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol import AskForApproval, FileChange, GitSha, ReviewDecision, SessionSource, ThreadId, TurnAbortReason
from pycodex.protocol.config_types import ForcedLoginMethod, ReasoningEffort, ReasoningSummary, SandboxMode, Verbosity
from pycodex.protocol.models import SandboxPolicy
from pycodex.protocol.parse_command import ParsedCommand

from .account import AuthMode
from .config import ForcedChatgptWorkspaceIds

JsonValue = Any


@dataclass(frozen=True)
class ClientInfo:
    name: str = ""
    title: str | None = None
    version: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _str(self.name, "name"))
        object.__setattr__(self, "title", _optional_str(self.title, "title"))
        object.__setattr__(self, "version", _str(self.version, "version"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ClientInfo":
        data = _mapping(value, "ClientInfo")
        return cls(name=_str(data.get("name", ""), "name"), title=_optional_str(data.get("title"), "title"), version=_str(data.get("version", ""), "version"))

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"name": self.name, "title": self.title, "version": self.version}


@dataclass(frozen=True)
class InitializeCapabilities:
    experimental_api: bool = False
    request_attestation: bool = False
    opt_out_notification_methods: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "experimental_api", _bool(self.experimental_api, "experimental_api"))
        object.__setattr__(self, "request_attestation", _bool(self.request_attestation, "request_attestation"))
        methods = self.opt_out_notification_methods
        if methods is not None:
            object.__setattr__(self, "opt_out_notification_methods", tuple(_str(item, "opt_out_notification_methods") for item in methods))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "InitializeCapabilities":
        data = _mapping(value, "InitializeCapabilities")
        return cls(
            experimental_api=_bool(_pick(data, "experimental_api", "experimentalApi", default=False), "experimental_api"),
            request_attestation=_bool(_pick(data, "request_attestation", "requestAttestation", default=False), "request_attestation"),
            opt_out_notification_methods=_optional_str_tuple(_pick(data, "opt_out_notification_methods", "optOutNotificationMethods"), "opt_out_notification_methods"),
        )

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "experimentalApi": self.experimental_api,
            "requestAttestation": self.request_attestation,
            "optOutNotificationMethods": None if self.opt_out_notification_methods is None else list(self.opt_out_notification_methods),
        }


@dataclass(frozen=True)
class InitializeParams:
    client_info: ClientInfo = field(default_factory=ClientInfo)
    capabilities: InitializeCapabilities | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "client_info", self.client_info if isinstance(self.client_info, ClientInfo) else ClientInfo.from_mapping(self.client_info))
        if self.capabilities is not None and not isinstance(self.capabilities, InitializeCapabilities):
            object.__setattr__(self, "capabilities", InitializeCapabilities.from_mapping(self.capabilities))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "InitializeParams":
        data = _mapping(value, "InitializeParams")
        return cls(
            client_info=ClientInfo.from_mapping(_mapping(_pick(data, "client_info", "clientInfo", default={}), "client_info")),
            capabilities=None if _pick(data, "capabilities") is None else InitializeCapabilities.from_mapping(_mapping(data["capabilities"], "capabilities")),
        )

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"clientInfo": self.client_info.to_camel_mapping()}
        if self.capabilities is not None:
            result["capabilities"] = self.capabilities.to_camel_mapping()
        return result


@dataclass(frozen=True)
class InitializeResponse:
    user_agent: str
    codex_home: Path | str
    platform_family: str
    platform_os: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_agent", _str(self.user_agent, "user_agent"))
        object.__setattr__(self, "codex_home", Path(self.codex_home))
        object.__setattr__(self, "platform_family", _str(self.platform_family, "platform_family"))
        object.__setattr__(self, "platform_os", _str(self.platform_os, "platform_os"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "InitializeResponse":
        data = _mapping(value, "InitializeResponse")
        return cls(
            user_agent=_str(_pick(data, "user_agent", "userAgent"), "user_agent"),
            codex_home=_path(_pick(data, "codex_home", "codexHome"), "codex_home"),
            platform_family=_str(_pick(data, "platform_family", "platformFamily"), "platform_family"),
            platform_os=_str(_pick(data, "platform_os", "platformOs"), "platform_os"),
        )

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"userAgent": self.user_agent, "codexHome": str(self.codex_home), "platformFamily": self.platform_family, "platformOs": self.platform_os}


@dataclass(frozen=True)
class GetConversationSummaryParams:
    rollout_path: Path | None = None
    conversation_id: ThreadId | None = None

    def __post_init__(self) -> None:
        if (self.rollout_path is None) == (self.conversation_id is None):
            raise ValueError("exactly one of rollout_path or conversation_id is required")
        if self.rollout_path is not None:
            object.__setattr__(self, "rollout_path", Path(self.rollout_path))
        if self.conversation_id is not None:
            object.__setattr__(self, "conversation_id", _thread_id(self.conversation_id))

    @classmethod
    def rollout(cls, path: Path | str) -> "GetConversationSummaryParams":
        return cls(rollout_path=Path(path))

    @classmethod
    def thread(cls, thread_id: ThreadId | str) -> "GetConversationSummaryParams":
        return cls(conversation_id=_thread_id(thread_id))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "GetConversationSummaryParams":
        data = _mapping(value, "GetConversationSummaryParams")
        rollout_path = _pick(data, "rollout_path", "rolloutPath")
        if rollout_path is not None:
            return cls.rollout(_path(rollout_path, "rollout_path"))
        return cls.thread(_str(_pick(data, "conversation_id", "conversationId"), "conversation_id"))

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        if self.rollout_path is not None:
            return {"rolloutPath": str(self.rollout_path)}
        return {"conversationId": str(self.conversation_id)}


@dataclass(frozen=True)
class ConversationGitInfo:
    sha: str | None = None
    branch: str | None = None
    origin_url: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConversationGitInfo":
        data = _mapping(value, "ConversationGitInfo")
        return cls(sha=_optional_str(data.get("sha"), "sha"), branch=_optional_str(data.get("branch"), "branch"), origin_url=_optional_str(_pick(data, "origin_url", "originUrl"), "origin_url"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"sha": self.sha, "branch": self.branch, "origin_url": self.origin_url}


@dataclass(frozen=True)
class ConversationSummary:
    conversation_id: ThreadId | str
    path: Path | str
    preview: str
    timestamp: str | None
    updated_at: str | None
    model_provider: str
    cwd: Path | str
    cli_version: str
    source: SessionSource | str | Mapping[str, JsonValue]
    git_info: ConversationGitInfo | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "conversation_id", _thread_id(self.conversation_id))
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "preview", _str(self.preview, "preview"))
        object.__setattr__(self, "timestamp", _optional_str(self.timestamp, "timestamp"))
        object.__setattr__(self, "updated_at", _optional_str(self.updated_at, "updated_at"))
        object.__setattr__(self, "model_provider", _str(self.model_provider, "model_provider"))
        object.__setattr__(self, "cwd", Path(self.cwd))
        object.__setattr__(self, "cli_version", _str(self.cli_version, "cli_version"))
        object.__setattr__(self, "source", _session_source(self.source))
        if self.git_info is not None and not isinstance(self.git_info, ConversationGitInfo):
            object.__setattr__(self, "git_info", ConversationGitInfo.from_mapping(self.git_info))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ConversationSummary":
        data = _mapping(value, "ConversationSummary")
        return cls(
            conversation_id=_str(_pick(data, "conversation_id", "conversationId"), "conversation_id"),
            path=_path(data["path"], "path"),
            preview=_str(data["preview"], "preview"),
            timestamp=_optional_str(data.get("timestamp"), "timestamp"),
            updated_at=_optional_str(_pick(data, "updated_at", "updatedAt"), "updated_at"),
            model_provider=_str(_pick(data, "model_provider", "modelProvider"), "model_provider"),
            cwd=_path(data["cwd"], "cwd"),
            cli_version=_str(_pick(data, "cli_version", "cliVersion"), "cli_version"),
            source=_pick(data, "source"),
            git_info=None if _pick(data, "git_info", "gitInfo") is None else ConversationGitInfo.from_mapping(_mapping(_pick(data, "git_info", "gitInfo"), "git_info")),
        )

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "conversationId": str(self.conversation_id),
            "path": str(self.path),
            "preview": self.preview,
            "timestamp": self.timestamp,
            "updatedAt": self.updated_at,
            "modelProvider": self.model_provider,
            "cwd": str(self.cwd),
            "cliVersion": self.cli_version,
            "source": _json(self.source),
            "gitInfo": None if self.git_info is None else self.git_info.to_mapping(),
        }


@dataclass(frozen=True)
class GetConversationSummaryResponse:
    summary: ConversationSummary

    def __post_init__(self) -> None:
        if not isinstance(self.summary, ConversationSummary):
            object.__setattr__(self, "summary", ConversationSummary.from_mapping(self.summary))

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"summary": self.summary.to_camel_mapping()}


@dataclass(frozen=True)
class LoginApiKeyParams:
    api_key: str

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"apiKey": _str(self.api_key, "api_key")}


@dataclass(frozen=True)
class GitDiffToRemoteResponse:
    sha: GitSha | str
    diff: str

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"sha": _json(self.sha), "diff": _str(self.diff, "diff")}


@dataclass(frozen=True)
class ApplyPatchApprovalParams:
    conversation_id: ThreadId | str
    call_id: str
    file_changes: Mapping[Path | str, FileChange | Mapping[str, JsonValue]]
    reason: str | None = None
    grant_root: Path | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "conversation_id", _thread_id(self.conversation_id))
        object.__setattr__(self, "call_id", _str(self.call_id, "call_id"))
        changes = {Path(path): _file_change(change) for path, change in self.file_changes.items()}
        object.__setattr__(self, "file_changes", changes)
        object.__setattr__(self, "reason", _optional_str(self.reason, "reason"))
        if self.grant_root is not None:
            object.__setattr__(self, "grant_root", Path(self.grant_root))

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "conversationId": str(self.conversation_id),
            "callId": self.call_id,
            "fileChanges": {str(path): _json(change) for path, change in self.file_changes.items()},
            "reason": self.reason,
            "grantRoot": None if self.grant_root is None else str(self.grant_root),
        }


@dataclass(frozen=True)
class ApplyPatchApprovalResponse:
    decision: ReviewDecision | str | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", ReviewDecision.from_mapping(self.decision))

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"decision": _json(self.decision)}


@dataclass(frozen=True)
class ExecCommandApprovalParams:
    conversation_id: ThreadId | str
    call_id: str
    approval_id: str | None
    command: tuple[str, ...] | list[str]
    cwd: Path | str
    reason: str | None
    parsed_cmd: tuple[ParsedCommand, ...] | list[ParsedCommand | Mapping[str, JsonValue]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "conversation_id", _thread_id(self.conversation_id))
        object.__setattr__(self, "call_id", _str(self.call_id, "call_id"))
        object.__setattr__(self, "approval_id", _optional_str(self.approval_id, "approval_id"))
        object.__setattr__(self, "command", tuple(_str(item, "command") for item in self.command))
        object.__setattr__(self, "cwd", Path(self.cwd))
        object.__setattr__(self, "reason", _optional_str(self.reason, "reason"))
        object.__setattr__(self, "parsed_cmd", tuple(_parsed_command(item) for item in self.parsed_cmd))

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "conversationId": str(self.conversation_id),
            "callId": self.call_id,
            "approvalId": self.approval_id,
            "command": list(self.command),
            "cwd": str(self.cwd),
            "reason": self.reason,
            "parsedCmd": [_json(item) for item in self.parsed_cmd],
        }


@dataclass(frozen=True)
class ExecCommandApprovalResponse:
    decision: ReviewDecision | str | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", ReviewDecision.from_mapping(self.decision))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"decision": _json(self.decision)}


@dataclass(frozen=True)
class GitDiffToRemoteParams:
    cwd: Path | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "cwd", Path(self.cwd))

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"cwd": str(self.cwd)}


@dataclass(frozen=True)
class GetAuthStatusParams:
    include_token: bool | None = None
    refresh_token: bool | None = None

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"includeToken": self.include_token, "refreshToken": self.refresh_token}


@dataclass(frozen=True)
class ExecOneOffCommandParams:
    command: tuple[str, ...] | list[str]
    timeout_ms: int | None = None
    cwd: Path | str | None = None
    sandbox_policy: SandboxPolicy | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(_str(item, "command") for item in self.command))
        if self.timeout_ms is not None:
            object.__setattr__(self, "timeout_ms", _u64(self.timeout_ms, "timeout_ms"))
        if self.cwd is not None:
            object.__setattr__(self, "cwd", Path(self.cwd))

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"command": list(self.command), "timeoutMs": self.timeout_ms, "cwd": None if self.cwd is None else str(self.cwd), "sandboxPolicy": _json(self.sandbox_policy)}


@dataclass(frozen=True)
class GetAuthStatusResponse:
    auth_method: AuthMode | str | None = None
    auth_token: str | None = None
    requires_openai_auth: bool | None = None

    def __post_init__(self) -> None:
        if self.auth_method is not None:
            object.__setattr__(self, "auth_method", AuthMode.parse(self.auth_method))

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"authMethod": _json(self.auth_method), "authToken": self.auth_token, "requiresOpenaiAuth": self.requires_openai_auth}


@dataclass(frozen=True)
class Tools:
    web_search: bool | None = None

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"webSearch": self.web_search}


@dataclass(frozen=True)
class SandboxSettings:
    writable_roots: tuple[Path, ...] = ()
    network_access: bool | None = None
    exclude_tmpdir_env_var: bool | None = None
    exclude_slash_tmp: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "writable_roots", tuple(Path(path) for path in self.writable_roots))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "SandboxSettings":
        data = _mapping(value, "SandboxSettings")
        return cls(
            writable_roots=tuple(Path(item) for item in _pick(data, "writable_roots", "writableRoots", default=())),
            network_access=_optional_bool(_pick(data, "network_access", "networkAccess"), "network_access"),
            exclude_tmpdir_env_var=_optional_bool(_pick(data, "exclude_tmpdir_env_var", "excludeTmpdirEnvVar"), "exclude_tmpdir_env_var"),
            exclude_slash_tmp=_optional_bool(_pick(data, "exclude_slash_tmp", "excludeSlashTmp"), "exclude_slash_tmp"),
        )

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "writableRoots": [str(path) for path in self.writable_roots],
            "networkAccess": self.network_access,
            "excludeTmpdirEnvVar": self.exclude_tmpdir_env_var,
            "excludeSlashTmp": self.exclude_slash_tmp,
        }


@dataclass(frozen=True)
class UserSavedConfig:
    approval_policy: AskForApproval | str | None = None
    sandbox_mode: SandboxMode | str | None = None
    sandbox_settings: SandboxSettings | Mapping[str, JsonValue] | None = None
    forced_chatgpt_workspace_id: ForcedChatgptWorkspaceIds | Mapping[str, JsonValue] | None = None
    forced_login_method: ForcedLoginMethod | str | None = None
    model: str | None = None
    model_reasoning_effort: ReasoningEffort | str | None = None
    model_reasoning_summary: ReasoningSummary | str | None = None
    model_verbosity: Verbosity | str | None = None
    tools: Tools | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval_policy", _optional_enum(self.approval_policy, AskForApproval))
        object.__setattr__(self, "sandbox_mode", _optional_enum(self.sandbox_mode, SandboxMode))
        if self.sandbox_settings is not None and not isinstance(self.sandbox_settings, SandboxSettings):
            object.__setattr__(self, "sandbox_settings", SandboxSettings.from_mapping(self.sandbox_settings))
        if self.forced_login_method is not None:
            object.__setattr__(self, "forced_login_method", _optional_enum(self.forced_login_method, ForcedLoginMethod))
        object.__setattr__(self, "model", _optional_str(self.model, "model"))
        object.__setattr__(self, "model_reasoning_effort", _optional_enum(self.model_reasoning_effort, ReasoningEffort))
        object.__setattr__(self, "model_reasoning_summary", _optional_enum(self.model_reasoning_summary, ReasoningSummary))
        object.__setattr__(self, "model_verbosity", _optional_enum(self.model_verbosity, Verbosity))
        if self.tools is not None and not isinstance(self.tools, Tools):
            object.__setattr__(self, "tools", Tools(web_search=_optional_bool(_pick(self.tools, "web_search", "webSearch"), "web_search")))

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "approvalPolicy": _json(self.approval_policy),
            "sandboxMode": _json(self.sandbox_mode),
            "sandboxSettings": None if self.sandbox_settings is None else self.sandbox_settings.to_camel_mapping(),
            "forcedChatgptWorkspaceId": _json(self.forced_chatgpt_workspace_id),
            "forcedLoginMethod": _json(self.forced_login_method),
            "model": self.model,
            "modelReasoningEffort": _json(self.model_reasoning_effort),
            "modelReasoningSummary": _json(self.model_reasoning_summary),
            "modelVerbosity": _json(self.model_verbosity),
            "tools": None if self.tools is None else self.tools.to_camel_mapping(),
        }


@dataclass(frozen=True)
class InterruptConversationResponse:
    abort_reason: TurnAbortReason | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "abort_reason", TurnAbortReason(self.abort_reason))

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"abortReason": self.abort_reason.value}


def _mapping(value: JsonValue, name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


def _pick(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _optional_str(value: JsonValue, name: str) -> str | None:
    return None if value is None else _str(value, name)


def _bool(value: JsonValue, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool")
    return value


def _optional_bool(value: JsonValue, name: str) -> bool | None:
    return None if value is None else _bool(value, name)


def _optional_str_tuple(value: JsonValue, name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a list")
    return tuple(_str(item, name) for item in value)


def _path(value: JsonValue, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a path string")
    return Path(value)


def _u64(value: JsonValue, name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise TypeError(f"{name} must be a non-negative integer")
    return value


def _thread_id(value: ThreadId | str) -> ThreadId:
    return value if isinstance(value, ThreadId) else ThreadId.from_string(_str(value, "thread_id"))


def _session_source(value: SessionSource | str | Mapping[str, JsonValue]) -> SessionSource | str | Mapping[str, JsonValue]:
    if isinstance(value, SessionSource):
        return value
    if isinstance(value, (str, Mapping)):
        return value
    raise TypeError("source must be SessionSource, string, or mapping")


def _file_change(value: FileChange | Mapping[str, JsonValue]) -> FileChange | Mapping[str, JsonValue]:
    if isinstance(value, FileChange) or isinstance(value, Mapping):
        return value
    raise TypeError("file change must be FileChange or mapping")


def _parsed_command(value: ParsedCommand | Mapping[str, JsonValue]) -> ParsedCommand:
    if isinstance(value, ParsedCommand):
        return value
    return ParsedCommand.from_mapping(value)


def _optional_enum(value: JsonValue, enum_cls: type[Enum]) -> Any:
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value
    parse = getattr(enum_cls, "parse", None)
    return parse(str(value)) if callable(parse) else enum_cls(str(value))


def _json(value: JsonValue) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ThreadId):
        return str(value)
    if hasattr(value, "to_camel_mapping"):
        return value.to_camel_mapping()
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if hasattr(value, "to_json"):
        return value.to_json()
    return value


__all__ = [
    "ApplyPatchApprovalParams",
    "ApplyPatchApprovalResponse",
    "ClientInfo",
    "ConversationGitInfo",
    "ConversationSummary",
    "ExecCommandApprovalParams",
    "ExecCommandApprovalResponse",
    "ExecOneOffCommandParams",
    "GetAuthStatusParams",
    "GetAuthStatusResponse",
    "GetConversationSummaryParams",
    "GetConversationSummaryResponse",
    "GitDiffToRemoteParams",
    "GitDiffToRemoteResponse",
    "GitSha",
    "InitializeCapabilities",
    "InitializeParams",
    "InitializeResponse",
    "InterruptConversationResponse",
    "LoginApiKeyParams",
    "SandboxSettings",
    "Tools",
    "UserSavedConfig",
]
