"""Common app-server protocol envelopes ported from ``protocol/common.rs``.

The Rust module owns the JSON-RPC request/notification enum layer, method
names, request serialization scopes, and the fuzzy-file-search payloads. Python
keeps this as a protocol boundary: payloads from neighboring v1/v2 modules are
accepted as JSON-compatible values instead of reimplementing their runtime
handlers here.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .account import AuthMode
from .item_builders import ServerNotification
from .jsonrpc_lite import JSONRPCNotification, JSONRPCRequest

JsonValue = Any


CLIENT_REQUEST_METHODS: dict[str, str] = {
    "Initialize": "initialize",
    "ThreadStart": "thread/start",
    "ThreadResume": "thread/resume",
    "ThreadFork": "thread/fork",
    "ThreadArchive": "thread/archive",
    "ThreadUnsubscribe": "thread/unsubscribe",
    "ThreadIncrementElicitation": "thread/increment_elicitation",
    "ThreadDecrementElicitation": "thread/decrement_elicitation",
    "ThreadSetName": "thread/name/set",
    "ThreadGoalSet": "thread/goal/set",
    "ThreadGoalGet": "thread/goal/get",
    "ThreadGoalClear": "thread/goal/clear",
    "ThreadMetadataUpdate": "thread/metadata/update",
    "ThreadSettingsUpdate": "thread/settings/update",
    "ThreadMemoryModeSet": "thread/memoryMode/set",
    "MemoryReset": "memory/reset",
    "ThreadUnarchive": "thread/unarchive",
    "ThreadCompactStart": "thread/compact/start",
    "ThreadShellCommand": "thread/shellCommand",
    "ThreadApproveGuardianDeniedAction": "thread/approveGuardianDeniedAction",
    "ThreadBackgroundTerminalsClean": "thread/backgroundTerminals/clean",
    "ThreadRollback": "thread/rollback",
    "ThreadList": "thread/list",
    "ThreadSearch": "thread/search",
    "ThreadLoadedList": "thread/loaded/list",
    "ThreadRead": "thread/read",
    "ThreadTurnsList": "thread/turns/list",
    "ThreadTurnsItemsList": "thread/turns/items/list",
    "ThreadInjectItems": "thread/inject_items",
    "SkillsList": "skills/list",
    "HooksList": "hooks/list",
    "MarketplaceAdd": "marketplace/add",
    "MarketplaceRemove": "marketplace/remove",
    "MarketplaceUpgrade": "marketplace/upgrade",
    "PluginList": "plugin/list",
    "PluginInstalled": "plugin/installed",
    "PluginRead": "plugin/read",
    "PluginSkillRead": "plugin/skill/read",
    "PluginShareSave": "plugin/share/save",
    "PluginShareUpdateTargets": "plugin/share/updateTargets",
    "PluginShareList": "plugin/share/list",
    "PluginShareCheckout": "plugin/share/checkout",
    "PluginShareDelete": "plugin/share/delete",
    "AppsList": "app/list",
    "FsReadFile": "fs/readFile",
    "FsWriteFile": "fs/writeFile",
    "FsCreateDirectory": "fs/createDirectory",
    "FsGetMetadata": "fs/getMetadata",
    "FsReadDirectory": "fs/readDirectory",
    "FsRemove": "fs/remove",
    "FsCopy": "fs/copy",
    "FsWatch": "fs/watch",
    "FsUnwatch": "fs/unwatch",
    "SkillsConfigWrite": "skills/config/write",
    "PluginInstall": "plugin/install",
    "PluginUninstall": "plugin/uninstall",
    "TurnStart": "turn/start",
    "TurnSteer": "turn/steer",
    "TurnInterrupt": "turn/interrupt",
    "ThreadRealtimeStart": "thread/realtime/start",
    "ThreadRealtimeAppendAudio": "thread/realtime/appendAudio",
    "ThreadRealtimeAppendText": "thread/realtime/appendText",
    "ThreadRealtimeStop": "thread/realtime/stop",
    "ThreadRealtimeListVoices": "thread/realtime/listVoices",
    "ReviewStart": "review/start",
    "ModelList": "model/list",
    "ModelProviderCapabilitiesRead": "modelProvider/capabilities/read",
    "ExperimentalFeatureList": "experimentalFeature/list",
    "PermissionProfileList": "permissionProfile/list",
    "ExperimentalFeatureEnablementSet": "experimentalFeature/enablement/set",
    "RemoteControlEnable": "remoteControl/enable",
    "RemoteControlDisable": "remoteControl/disable",
    "RemoteControlStatusRead": "remoteControl/status/read",
    "CollaborationModeList": "collaborationMode/list",
    "MockExperimentalMethod": "mock/experimentalMethod",
    "EnvironmentAdd": "environment/add",
    "McpServerOauthLogin": "mcpServer/oauth/login",
    "McpServerRefresh": "config/mcpServer/reload",
    "McpServerStatusList": "mcpServerStatus/list",
    "McpResourceRead": "mcpServer/resource/read",
    "McpServerToolCall": "mcpServer/tool/call",
    "WindowsSandboxSetupStart": "windowsSandbox/setupStart",
    "WindowsSandboxReadiness": "windowsSandbox/readiness",
    "LoginAccount": "account/login/start",
    "CancelLoginAccount": "account/login/cancel",
    "LogoutAccount": "account/logout",
    "GetAccountRateLimits": "account/rateLimits/read",
    "SendAddCreditsNudgeEmail": "account/sendAddCreditsNudgeEmail",
    "FeedbackUpload": "feedback/upload",
    "OneOffCommandExec": "command/exec",
    "CommandExecWrite": "command/exec/write",
    "CommandExecTerminate": "command/exec/terminate",
    "CommandExecResize": "command/exec/resize",
    "ProcessSpawn": "process/spawn",
    "ProcessWriteStdin": "process/writeStdin",
    "ProcessKill": "process/kill",
    "ProcessResizePty": "process/resizePty",
    "ConfigRead": "config/read",
    "ExternalAgentConfigDetect": "externalAgentConfig/detect",
    "ExternalAgentConfigImport": "externalAgentConfig/import",
    "ConfigValueWrite": "config/value/write",
    "ConfigBatchWrite": "config/batchWrite",
    "ConfigRequirementsRead": "configRequirements/read",
    "GetAccount": "account/read",
    "GetConversationSummary": "getConversationSummary",
    "GitDiffToRemote": "gitDiffToRemote",
    "GetAuthStatus": "getAuthStatus",
    "FuzzyFileSearch": "fuzzyFileSearch",
    "FuzzyFileSearchSessionStart": "fuzzyFileSearch/sessionStart",
    "FuzzyFileSearchSessionUpdate": "fuzzyFileSearch/sessionUpdate",
    "FuzzyFileSearchSessionStop": "fuzzyFileSearch/sessionStop",
}

CLIENT_REQUEST_VARIANTS_BY_METHOD = {method: variant for variant, method in CLIENT_REQUEST_METHODS.items()}

SERVER_REQUEST_METHODS: dict[str, str] = {
    "CommandExecutionRequestApproval": "item/commandExecution/requestApproval",
    "FileChangeRequestApproval": "item/fileChange/requestApproval",
    "ToolRequestUserInput": "item/tool/requestUserInput",
    "McpServerElicitationRequest": "mcpServer/elicitation/request",
    "PermissionsRequestApproval": "item/permissions/requestApproval",
    "DynamicToolCall": "item/tool/call",
    "ChatgptAuthTokensRefresh": "account/chatgptAuthTokens/refresh",
    "AttestationGenerate": "attestation/generate",
    "ApplyPatchApproval": "applyPatchApproval",
    "ExecCommandApproval": "execCommandApproval",
}

SERVER_REQUEST_VARIANTS_BY_METHOD = {method: variant for variant, method in SERVER_REQUEST_METHODS.items()}

SERVER_NOTIFICATION_METHODS: dict[str, str] = {
    "Error": "error",
    "ThreadStarted": "thread/started",
    "ThreadStatusChanged": "thread/status/changed",
    "ThreadArchived": "thread/archived",
    "ThreadUnarchived": "thread/unarchived",
    "ThreadClosed": "thread/closed",
    "SkillsChanged": "skills/changed",
    "ThreadNameUpdated": "thread/name/updated",
    "ThreadGoalUpdated": "thread/goal/updated",
    "ThreadGoalCleared": "thread/goal/cleared",
    "ThreadSettingsUpdated": "thread/settings/updated",
    "ThreadTokenUsageUpdated": "thread/tokenUsage/updated",
    "TurnStarted": "turn/started",
    "HookStarted": "hook/started",
    "TurnCompleted": "turn/completed",
    "HookCompleted": "hook/completed",
    "TurnDiffUpdated": "turn/diff/updated",
    "TurnPlanUpdated": "turn/plan/updated",
    "ItemStarted": "item/started",
    "ItemGuardianApprovalReviewStarted": "item/autoApprovalReview/started",
    "ItemGuardianApprovalReviewCompleted": "item/autoApprovalReview/completed",
    "ItemCompleted": "item/completed",
    "RawResponseItemCompleted": "rawResponseItem/completed",
    "AgentMessageDelta": "item/agentMessage/delta",
    "PlanDelta": "item/plan/delta",
    "CommandExecOutputDelta": "command/exec/outputDelta",
    "ProcessOutputDelta": "process/outputDelta",
    "ProcessExited": "process/exited",
    "CommandExecutionOutputDelta": "item/commandExecution/outputDelta",
    "TerminalInteraction": "item/commandExecution/terminalInteraction",
    "FileChangeOutputDelta": "item/fileChange/outputDelta",
    "FileChangePatchUpdated": "item/fileChange/patchUpdated",
    "ServerRequestResolved": "serverRequest/resolved",
    "McpToolCallProgress": "item/mcpToolCall/progress",
    "McpServerOauthLoginCompleted": "mcpServer/oauthLogin/completed",
    "McpServerStatusUpdated": "mcpServer/startupStatus/updated",
    "AccountUpdated": "account/updated",
    "AccountRateLimitsUpdated": "account/rateLimits/updated",
    "AppListUpdated": "app/list/updated",
    "RemoteControlStatusChanged": "remoteControl/status/changed",
    "ExternalAgentConfigImportCompleted": "externalAgentConfig/import/completed",
    "FsChanged": "fs/changed",
    "ReasoningSummaryTextDelta": "item/reasoning/summaryTextDelta",
    "ReasoningSummaryPartAdded": "item/reasoning/summaryPartAdded",
    "ReasoningTextDelta": "item/reasoning/textDelta",
    "ContextCompacted": "thread/compacted",
    "ModelRerouted": "model/rerouted",
    "ModelVerification": "model/verification",
    "Warning": "warning",
    "GuardianWarning": "guardianWarning",
    "DeprecationNotice": "deprecationNotice",
    "ConfigWarning": "configWarning",
    "FuzzyFileSearchSessionUpdated": "fuzzyFileSearch/sessionUpdated",
    "FuzzyFileSearchSessionCompleted": "fuzzyFileSearch/sessionCompleted",
    "ThreadRealtimeStarted": "thread/realtime/started",
    "ThreadRealtimeItemAdded": "thread/realtime/itemAdded",
    "ThreadRealtimeTranscriptDelta": "thread/realtime/transcript/delta",
    "ThreadRealtimeTranscriptDone": "thread/realtime/transcript/done",
    "ThreadRealtimeOutputAudioDelta": "thread/realtime/outputAudio/delta",
    "ThreadRealtimeSdp": "thread/realtime/sdp",
    "ThreadRealtimeError": "thread/realtime/error",
    "ThreadRealtimeClosed": "thread/realtime/closed",
    "WindowsWorldWritableWarning": "windows/worldWritableWarning",
    "WindowsSandboxSetupCompleted": "windowsSandbox/setupCompleted",
    "AccountLoginCompleted": "account/login/completed",
}

SERVER_NOTIFICATION_VARIANTS_BY_METHOD = {
    method: variant for variant, method in SERVER_NOTIFICATION_METHODS.items()
}

CLIENT_NOTIFICATION_METHODS: dict[str, str] = {"Initialized": "initialized"}
CLIENT_NOTIFICATION_VARIANTS_BY_METHOD = {
    method: variant for variant, method in CLIENT_NOTIFICATION_METHODS.items()
}


class FuzzyFileSearchMatchType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"


@dataclass(frozen=True)
class ClientRequestSerializationScope:
    type: str
    key: str | None = None
    thread_id: str | None = None
    path: str | None = None
    process_id: str | None = None
    process_handle: str | None = None
    session_id: str | None = None
    watch_id: str | None = None
    server_name: str | None = None

    @classmethod
    def global_(cls, key: str) -> "ClientRequestSerializationScope":
        return cls("Global", key=_ensure_str(key, "key"))

    @classmethod
    def global_shared_read(cls, key: str) -> "ClientRequestSerializationScope":
        return cls("GlobalSharedRead", key=_ensure_str(key, "key"))

    @classmethod
    def thread(cls, thread_id: str) -> "ClientRequestSerializationScope":
        return cls("Thread", thread_id=_ensure_str(thread_id, "thread_id"))

    @classmethod
    def thread_path(cls, path: str | Path) -> "ClientRequestSerializationScope":
        return cls("ThreadPath", path=str(path))

    @classmethod
    def command_exec_process(cls, process_id: str) -> "ClientRequestSerializationScope":
        return cls("CommandExecProcess", process_id=_ensure_str(process_id, "process_id"))

    @classmethod
    def process(cls, process_handle: str) -> "ClientRequestSerializationScope":
        return cls("Process", process_handle=_ensure_str(process_handle, "process_handle"))

    @classmethod
    def fuzzy_file_search_session(cls, session_id: str) -> "ClientRequestSerializationScope":
        return cls("FuzzyFileSearchSession", session_id=_ensure_str(session_id, "session_id"))

    @classmethod
    def fs_watch(cls, watch_id: str) -> "ClientRequestSerializationScope":
        return cls("FsWatch", watch_id=_ensure_str(watch_id, "watch_id"))

    @classmethod
    def mcp_oauth(cls, server_name: str) -> "ClientRequestSerializationScope":
        return cls("McpOauth", server_name=_ensure_str(server_name, "server_name"))

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"type": self.type}
        for key in (
            "key",
            "thread_id",
            "path",
            "process_id",
            "process_handle",
            "session_id",
            "watch_id",
            "server_name",
        ):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result


@dataclass(frozen=True)
class ClientRequest:
    type: str
    request_id: JsonValue
    params: JsonValue | None = None

    @classmethod
    def from_jsonrpc(cls, value: JSONRPCRequest | Mapping[str, JsonValue]) -> "ClientRequest":
        request = value if isinstance(value, JSONRPCRequest) else JSONRPCRequest.from_mapping(value)
        try:
            variant = CLIENT_REQUEST_VARIANTS_BY_METHOD[request.method]
        except KeyError as exc:
            raise ValueError(f"unknown client request method: {request.method}") from exc
        return cls(type=variant, request_id=request.id.to_json(), params=copy.deepcopy(request.params))

    def method(self) -> str:
        try:
            return CLIENT_REQUEST_METHODS[self.type]
        except KeyError as exc:
            raise ValueError(f"unknown ClientRequest variant: {self.type}") from exc

    def id(self) -> JsonValue:
        return copy.deepcopy(self.request_id)

    def serialization_scope(self) -> ClientRequestSerializationScope | None:
        params = _mapping_or_empty(self.params)
        match self.type:
            case "ThreadResume" | "ThreadFork":
                thread_id = _optional_str(_get(params, "thread_id", "threadId", default=""), "thread_id") or ""
                path = _get(params, "path", default=None)
                if thread_id:
                    return ClientRequestSerializationScope.thread(thread_id)
                if path is not None:
                    return ClientRequestSerializationScope.thread_path(path)
                return ClientRequestSerializationScope.thread(thread_id)
            case _ if self.type in _THREAD_ID_REQUESTS:
                return ClientRequestSerializationScope.thread(
                    _required_str(_get(params, "thread_id", "threadId"), "thread_id")
                )
            case _ if self.type in _FS_WATCH_REQUESTS:
                return ClientRequestSerializationScope.fs_watch(
                    _required_str(_get(params, "watch_id", "watchId"), "watch_id")
                )
            case _ if self.type in _COMMAND_PROCESS_REQUESTS:
                return ClientRequestSerializationScope.command_exec_process(
                    _required_str(_get(params, "process_id", "processId"), "process_id")
                )
            case "OneOffCommandExec":
                process_id = _optional_str(_get(params, "process_id", "processId", default=None), "process_id")
                return ClientRequestSerializationScope.command_exec_process(process_id) if process_id else None
            case _ if self.type in _PROCESS_HANDLE_REQUESTS:
                return ClientRequestSerializationScope.process(
                    _required_str(_get(params, "process_handle", "processHandle"), "process_handle")
                )
            case _ if self.type in _FUZZY_SESSION_REQUESTS:
                return ClientRequestSerializationScope.fuzzy_file_search_session(
                    _required_str(_get(params, "session_id", "sessionId"), "session_id")
                )
            case "McpServerOauthLogin":
                return ClientRequestSerializationScope.mcp_oauth(_required_str(_get(params, "name"), "name"))
            case "McpResourceRead":
                thread_id = _optional_str(_get(params, "thread_id", "threadId", default=None), "thread_id")
                return ClientRequestSerializationScope.thread(thread_id) if thread_id else None
            case _:
                scope = _FIXED_CLIENT_REQUEST_SCOPES.get(self.type)
                return scope() if scope else None

    def to_jsonrpc(self) -> JSONRPCRequest:
        return JSONRPCRequest(id=self.request_id, method=self.method(), params=copy.deepcopy(self.params))

    def to_mapping(self) -> dict[str, JsonValue]:
        return self.to_jsonrpc().to_mapping()


@dataclass(frozen=True)
class ClientNotification:
    type: str
    payload: JsonValue | None = None

    @classmethod
    def from_jsonrpc(cls, value: JSONRPCNotification | Mapping[str, JsonValue]) -> "ClientNotification":
        notification = value if isinstance(value, JSONRPCNotification) else JSONRPCNotification.from_mapping(value)
        try:
            variant = CLIENT_NOTIFICATION_VARIANTS_BY_METHOD[notification.method]
        except KeyError as exc:
            raise ValueError(f"unknown client notification method: {notification.method}") from exc
        return cls(type=variant, payload=copy.deepcopy(notification.params))

    def method(self) -> str:
        try:
            return CLIENT_NOTIFICATION_METHODS[self.type]
        except KeyError as exc:
            raise ValueError(f"unknown ClientNotification variant: {self.type}") from exc

    def to_jsonrpc(self) -> JSONRPCNotification:
        return JSONRPCNotification(method=self.method(), params=copy.deepcopy(self.payload))

    def to_mapping(self) -> dict[str, JsonValue]:
        return self.to_jsonrpc().to_mapping()


@dataclass(frozen=True)
class ServerRequest:
    type: str
    request_id: JsonValue
    params: JsonValue | None = None

    @classmethod
    def from_jsonrpc(cls, value: JSONRPCRequest | Mapping[str, JsonValue]) -> "ServerRequest":
        request = value if isinstance(value, JSONRPCRequest) else JSONRPCRequest.from_mapping(value)
        try:
            variant = SERVER_REQUEST_VARIANTS_BY_METHOD[request.method]
        except KeyError as exc:
            raise ValueError(f"unknown server request method: {request.method}") from exc
        return cls(type=variant, request_id=request.id.to_json(), params=copy.deepcopy(request.params))

    def method(self) -> str:
        try:
            return SERVER_REQUEST_METHODS[self.type]
        except KeyError as exc:
            raise ValueError(f"unknown ServerRequest variant: {self.type}") from exc

    def to_jsonrpc(self) -> JSONRPCRequest:
        return JSONRPCRequest(id=self.request_id, method=self.method(), params=copy.deepcopy(self.params))

    def to_mapping(self) -> dict[str, JsonValue]:
        return self.to_jsonrpc().to_mapping()


@dataclass(frozen=True)
class FuzzyFileSearchParams:
    query: str
    roots: list[str]
    cancellation_token: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FuzzyFileSearchParams":
        data = _mapping(value, "FuzzyFileSearchParams")
        return cls(
            query=_required_str(data.get("query"), "query"),
            roots=[_ensure_str(root, "roots[]") for root in data.get("roots", [])],
            cancellation_token=_optional_str(
                _get(data, "cancellation_token", "cancellationToken", default=None),
                "cancellation_token",
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"query": self.query, "roots": list(self.roots)}
        if self.cancellation_token is not None:
            result["cancellationToken"] = self.cancellation_token
        return result


@dataclass(frozen=True)
class FuzzyFileSearchResult:
    root: str
    path: str
    match_type: FuzzyFileSearchMatchType | str
    file_name: str
    score: int
    indices: list[int] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FuzzyFileSearchResult":
        data = _mapping(value, "FuzzyFileSearchResult")
        return cls(
            root=_required_str(data.get("root"), "root"),
            path=_required_str(data.get("path"), "path"),
            match_type=FuzzyFileSearchMatchType(_required_str(_get(data, "match_type", "matchType"), "match_type")),
            file_name=_required_str(_get(data, "file_name", "fileName"), "file_name"),
            score=_ensure_u32(data.get("score"), "score"),
            indices=[_ensure_u32(index, "indices[]") for index in data["indices"]]
            if data.get("indices") is not None
            else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "root": self.root,
            "path": self.path,
            "match_type": _enum_value(self.match_type),
            "file_name": self.file_name,
            "score": self.score,
        }
        if self.indices is not None:
            result["indices"] = list(self.indices)
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = self.to_mapping()
        result["matchType"] = result.pop("match_type")
        result["fileName"] = result.pop("file_name")
        return result


@dataclass(frozen=True)
class FuzzyFileSearchResponse:
    files: list[FuzzyFileSearchResult] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FuzzyFileSearchResponse":
        data = _mapping(value, "FuzzyFileSearchResponse")
        return cls(files=[FuzzyFileSearchResult.from_mapping(item) for item in data.get("files", [])])

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"files": [file.to_mapping() for file in self.files]}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"files": [file.to_camel_mapping() for file in self.files]}


@dataclass(frozen=True)
class FuzzyFileSearchSessionStartParams:
    session_id: str
    roots: list[str]

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FuzzyFileSearchSessionStartParams":
        data = _mapping(value, "FuzzyFileSearchSessionStartParams")
        return cls(
            session_id=_required_str(_get(data, "session_id", "sessionId"), "session_id"),
            roots=[_ensure_str(root, "roots[]") for root in data.get("roots", [])],
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"session_id": self.session_id, "roots": list(self.roots)}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"sessionId": self.session_id, "roots": list(self.roots)}


@dataclass(frozen=True)
class FuzzyFileSearchSessionStartResponse:
    def to_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class FuzzyFileSearchSessionUpdateParams:
    session_id: str
    query: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FuzzyFileSearchSessionUpdateParams":
        data = _mapping(value, "FuzzyFileSearchSessionUpdateParams")
        return cls(
            session_id=_required_str(_get(data, "session_id", "sessionId"), "session_id"),
            query=_required_str(data.get("query"), "query"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"session_id": self.session_id, "query": self.query}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"sessionId": self.session_id, "query": self.query}


@dataclass(frozen=True)
class FuzzyFileSearchSessionUpdateResponse:
    def to_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class FuzzyFileSearchSessionStopParams:
    session_id: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FuzzyFileSearchSessionStopParams":
        data = _mapping(value, "FuzzyFileSearchSessionStopParams")
        return cls(session_id=_required_str(_get(data, "session_id", "sessionId"), "session_id"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"session_id": self.session_id}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"sessionId": self.session_id}


@dataclass(frozen=True)
class FuzzyFileSearchSessionStopResponse:
    def to_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class FuzzyFileSearchSessionUpdatedNotification:
    session_id: str
    query: str
    files: list[FuzzyFileSearchResult] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FuzzyFileSearchSessionUpdatedNotification":
        data = _mapping(value, "FuzzyFileSearchSessionUpdatedNotification")
        return cls(
            session_id=_required_str(_get(data, "session_id", "sessionId"), "session_id"),
            query=_required_str(data.get("query"), "query"),
            files=[FuzzyFileSearchResult.from_mapping(item) for item in data.get("files", [])],
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "files": [file.to_mapping() for file in self.files],
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "sessionId": self.session_id,
            "query": self.query,
            "files": [file.to_camel_mapping() for file in self.files],
        }


@dataclass(frozen=True)
class FuzzyFileSearchSessionCompletedNotification:
    session_id: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FuzzyFileSearchSessionCompletedNotification":
        data = _mapping(value, "FuzzyFileSearchSessionCompletedNotification")
        return cls(session_id=_required_str(_get(data, "session_id", "sessionId"), "session_id"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"session_id": self.session_id}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"sessionId": self.session_id}


_THREAD_ID_REQUESTS = {
    "ThreadArchive",
    "ThreadUnsubscribe",
    "ThreadIncrementElicitation",
    "ThreadDecrementElicitation",
    "ThreadSetName",
    "ThreadGoalSet",
    "ThreadGoalGet",
    "ThreadGoalClear",
    "ThreadMetadataUpdate",
    "ThreadSettingsUpdate",
    "ThreadMemoryModeSet",
    "ThreadUnarchive",
    "ThreadCompactStart",
    "ThreadShellCommand",
    "ThreadApproveGuardianDeniedAction",
    "ThreadBackgroundTerminalsClean",
    "ThreadRollback",
    "ThreadRead",
    "ThreadInjectItems",
    "TurnStart",
    "TurnSteer",
    "TurnInterrupt",
    "ThreadRealtimeStart",
    "ThreadRealtimeAppendAudio",
    "ThreadRealtimeAppendText",
    "ThreadRealtimeStop",
    "ReviewStart",
    "McpServerToolCall",
}

_FS_WATCH_REQUESTS = {"FsWatch", "FsUnwatch"}
_COMMAND_PROCESS_REQUESTS = {"CommandExecWrite", "CommandExecTerminate", "CommandExecResize"}
_PROCESS_HANDLE_REQUESTS = {"ProcessSpawn", "ProcessWriteStdin", "ProcessKill", "ProcessResizePty"}
_FUZZY_SESSION_REQUESTS = {
    "FuzzyFileSearchSessionStart",
    "FuzzyFileSearchSessionUpdate",
    "FuzzyFileSearchSessionStop",
}

_FIXED_CLIENT_REQUEST_SCOPES = {
    "MemoryReset": lambda: ClientRequestSerializationScope.global_("memory"),
    "SkillsList": lambda: ClientRequestSerializationScope.global_shared_read("config"),
    "HooksList": lambda: ClientRequestSerializationScope.global_("config"),
    "MarketplaceAdd": lambda: ClientRequestSerializationScope.global_("config"),
    "MarketplaceRemove": lambda: ClientRequestSerializationScope.global_("config"),
    "MarketplaceUpgrade": lambda: ClientRequestSerializationScope.global_("config"),
    "PluginSkillRead": lambda: ClientRequestSerializationScope.global_("config"),
    "PluginShareSave": lambda: ClientRequestSerializationScope.global_("config"),
    "PluginShareUpdateTargets": lambda: ClientRequestSerializationScope.global_("config"),
    "PluginShareList": lambda: ClientRequestSerializationScope.global_("config"),
    "PluginShareCheckout": lambda: ClientRequestSerializationScope.global_("config"),
    "PluginShareDelete": lambda: ClientRequestSerializationScope.global_("config"),
    "SkillsConfigWrite": lambda: ClientRequestSerializationScope.global_("config"),
    "PluginInstall": lambda: ClientRequestSerializationScope.global_("config"),
    "PluginUninstall": lambda: ClientRequestSerializationScope.global_("config"),
    "ExperimentalFeatureList": lambda: ClientRequestSerializationScope.global_("config"),
    "PermissionProfileList": lambda: ClientRequestSerializationScope.global_shared_read("config"),
    "ExperimentalFeatureEnablementSet": lambda: ClientRequestSerializationScope.global_("config"),
    "RemoteControlEnable": lambda: ClientRequestSerializationScope.global_("remote-control"),
    "RemoteControlDisable": lambda: ClientRequestSerializationScope.global_("remote-control"),
    "RemoteControlStatusRead": lambda: ClientRequestSerializationScope.global_shared_read("remote-control"),
    "EnvironmentAdd": lambda: ClientRequestSerializationScope.global_("environment"),
    "McpServerRefresh": lambda: ClientRequestSerializationScope.global_("mcp-registry"),
    "McpServerStatusList": lambda: ClientRequestSerializationScope.global_("mcp-registry"),
    "WindowsSandboxSetupStart": lambda: ClientRequestSerializationScope.global_("windows-sandbox-setup"),
    "WindowsSandboxReadiness": lambda: ClientRequestSerializationScope.global_("config"),
    "LoginAccount": lambda: ClientRequestSerializationScope.global_("account-auth"),
    "CancelLoginAccount": lambda: ClientRequestSerializationScope.global_("account-auth"),
    "LogoutAccount": lambda: ClientRequestSerializationScope.global_("account-auth"),
    "SendAddCreditsNudgeEmail": lambda: ClientRequestSerializationScope.global_("account-auth"),
    "ConfigRead": lambda: ClientRequestSerializationScope.global_shared_read("config"),
    "ExternalAgentConfigDetect": lambda: ClientRequestSerializationScope.global_("config"),
    "ExternalAgentConfigImport": lambda: ClientRequestSerializationScope.global_("config"),
    "ConfigValueWrite": lambda: ClientRequestSerializationScope.global_("config"),
    "ConfigBatchWrite": lambda: ClientRequestSerializationScope.global_("config"),
    "ConfigRequirementsRead": lambda: ClientRequestSerializationScope.global_("config"),
    "GetAccount": lambda: ClientRequestSerializationScope.global_("account-auth"),
    "GetAuthStatus": lambda: ClientRequestSerializationScope.global_("account-auth"),
}


def server_notification_from_jsonrpc(value: JSONRPCNotification | Mapping[str, JsonValue]) -> ServerNotification:
    notification = value if isinstance(value, JSONRPCNotification) else JSONRPCNotification.from_mapping(value)
    try:
        variant = SERVER_NOTIFICATION_VARIANTS_BY_METHOD[notification.method]
    except KeyError as exc:
        raise ValueError(f"unknown server notification method: {notification.method}") from exc
    return ServerNotification(type=variant, payload=copy.deepcopy(notification.params))


def _mapping(value: JsonValue, name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


def _mapping_or_empty(value: JsonValue) -> Mapping[str, JsonValue]:
    if value is None:
        return {}
    return _mapping(value, "params")


def _get(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _ensure_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _required_str(value: JsonValue, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} is required")
    return _ensure_str(value, name)


def _optional_str(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, name)


def _ensure_u32(value: JsonValue, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2**32 - 1:
        raise TypeError(f"{name} must be a u32 integer")
    return value


def _enum_value(value: Enum | str) -> str:
    return value.value if isinstance(value, Enum) else value

