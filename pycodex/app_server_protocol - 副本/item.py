"""Item protocol types ported from ``protocol/v2/item.rs``.

The Rust module is primarily an app-server wire contract for thread items,
approval decisions, item lifecycle notifications, and tool-call request/response
payloads. Python keeps the same tagged/camelCase protocol shapes while leaving
neighbor-owned payloads as JSON-compatible mappings where appropriate.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path
from typing import Any

JsonValue = Any


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__} value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid {cls.__name__}: {raw}; expected one of: {choices}") from exc

    def to_mapping(self) -> str:
        return self.value


class CommandExecutionApprovalDecisionType(_StringEnum):
    ACCEPT = "accept"
    ACCEPT_FOR_SESSION = "acceptForSession"
    ACCEPT_WITH_EXECPOLICY_AMENDMENT = "acceptWithExecpolicyAmendment"
    APPLY_NETWORK_POLICY_AMENDMENT = "applyNetworkPolicyAmendment"
    DECLINE = "decline"
    CANCEL = "cancel"


class FileChangeApprovalDecision(_StringEnum):
    ACCEPT = "accept"
    ACCEPT_FOR_SESSION = "acceptForSession"
    DECLINE = "decline"
    CANCEL = "cancel"


class GuardianApprovalReviewStatus(_StringEnum):
    IN_PROGRESS = "inProgress"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timedOut"
    ABORTED = "aborted"


class AutoReviewDecisionSource(_StringEnum):
    AGENT = "agent"


class GuardianRiskLevel(_StringEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GuardianUserAuthorization(_StringEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GuardianCommandSource(_StringEnum):
    SHELL = "shell"
    UNIFIED_EXEC = "unifiedExec"


class CommandExecutionStatus(_StringEnum):
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"
    DECLINED = "declined"


class CommandExecutionSource(_StringEnum):
    AGENT = "agent"
    USER_SHELL = "userShell"
    UNIFIED_EXEC_STARTUP = "unifiedExecStartup"
    UNIFIED_EXEC_INTERACTION = "unifiedExecInteraction"


class CollabAgentTool(_StringEnum):
    SPAWN_AGENT = "spawnAgent"
    SEND_INPUT = "sendInput"
    RESUME_AGENT = "resumeAgent"
    WAIT = "wait"
    CLOSE_AGENT = "closeAgent"


class PatchApplyStatus(_StringEnum):
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"
    DECLINED = "declined"


class McpToolCallStatus(_StringEnum):
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"


class DynamicToolCallStatus(_StringEnum):
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"


class CollabAgentToolCallStatus(_StringEnum):
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"


class CollabAgentStatus(_StringEnum):
    PENDING_INIT = "pendingInit"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    ERRORED = "errored"
    SHUTDOWN = "shutdown"
    NOT_FOUND = "notFound"


@dataclass(frozen=True)
class TaggedPayload:
    type: str
    fields: Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _ensure_str(self.type, "type"))
        object.__setattr__(self, "fields", _deep_mapping(self.fields or {}, "fields"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TaggedPayload":
        data = dict(_mapping(value, cls.__name__))
        type_ = _ensure_str(data.pop("type"), "type")
        return cls(type=type_, fields=data)

    @classmethod
    def make(cls, type_: str, **fields_: JsonValue) -> "TaggedPayload":
        return cls(type=type_, fields=fields_)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"type": self.type, **_serialize_mapping(self.fields or {})}


class CommandExecutionApprovalDecision(TaggedPayload):
    @classmethod
    def accept(cls) -> "CommandExecutionApprovalDecision":
        return cls("accept")

    @classmethod
    def accept_for_session(cls) -> "CommandExecutionApprovalDecision":
        return cls("acceptForSession")

    @classmethod
    def accept_with_execpolicy_amendment(cls, execpolicy_amendment: JsonValue) -> "CommandExecutionApprovalDecision":
        return cls("acceptWithExecpolicyAmendment", {"execpolicyAmendment": execpolicy_amendment})

    @classmethod
    def apply_network_policy_amendment(cls, network_policy_amendment: JsonValue) -> "CommandExecutionApprovalDecision":
        return cls("applyNetworkPolicyAmendment", {"networkPolicyAmendment": network_policy_amendment})

    @classmethod
    def decline(cls) -> "CommandExecutionApprovalDecision":
        return cls("decline")

    @classmethod
    def cancel(cls) -> "CommandExecutionApprovalDecision":
        return cls("cancel")


class CommandAction(TaggedPayload):
    @classmethod
    def read(cls, command: str, name: str, path: Path | str) -> "CommandAction":
        return cls("read", {"command": _ensure_str(command, "command"), "name": _ensure_str(name, "name"), "path": _path_str(path, "path")})

    @classmethod
    def list_files(cls, command: str, path: str | None = None) -> "CommandAction":
        return cls("listFiles", {"command": _ensure_str(command, "command"), "path": _optional_str(path, "path")})

    @classmethod
    def search(cls, command: str, query: str | None = None, path: str | None = None) -> "CommandAction":
        return cls("search", {"command": _ensure_str(command, "command"), "query": _optional_str(query, "query"), "path": _optional_str(path, "path")})

    @classmethod
    def unknown(cls, command: str) -> "CommandAction":
        return cls("unknown", {"command": _ensure_str(command, "command")})

    def into_core(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class MemoryCitationEntry:
    path: str
    line_start: int
    line_end: int
    note: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _ensure_str(self.path, "path"))
        object.__setattr__(self, "line_start", _u32(self.line_start, "line_start"))
        object.__setattr__(self, "line_end", _u32(self.line_end, "line_end"))
        object.__setattr__(self, "note", _ensure_str(self.note, "note"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "MemoryCitationEntry":
        data = _mapping(value, "MemoryCitationEntry")
        return cls(
            path=_ensure_str(data["path"], "path"),
            line_start=_u32(_pick(data, "line_start", "lineStart"), "line_start"),
            line_end=_u32(_pick(data, "line_end", "lineEnd"), "line_end"),
            note=_ensure_str(data["note"], "note"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class MemoryCitation:
    entries: tuple[MemoryCitationEntry, ...]
    thread_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(_memory_citation_entry(entry) for entry in self.entries))
        object.__setattr__(self, "thread_ids", _str_tuple(self.thread_ids, "thread_ids"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "MemoryCitation":
        data = _mapping(value, "MemoryCitation")
        return cls(
            entries=tuple(MemoryCitationEntry.from_mapping(item) for item in _list(data["entries"], "entries")),
            thread_ids=_str_tuple(_pick(data, "thread_ids", "threadIds"), "thread_ids"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"entries": [entry.to_mapping() for entry in self.entries], "thread_ids": list(self.thread_ids)}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"entries": [entry.to_camel_mapping() for entry in self.entries], "threadIds": list(self.thread_ids)}


class ThreadItem(TaggedPayload):
    def id(self) -> str:
        return _ensure_str((self.fields or {}).get("id"), "id")

    @classmethod
    def user_message(cls, id: str, content: Iterable[JsonValue]) -> "ThreadItem":
        return cls("userMessage", {"id": id, "content": list(content)})

    @classmethod
    def agent_message(
        cls,
        id: str,
        text: str,
        *,
        phase: JsonValue | None = None,
        memory_citation: MemoryCitation | Mapping[str, JsonValue] | None = None,
    ) -> "ThreadItem":
        citation = _memory_citation(memory_citation).to_camel_mapping() if memory_citation is not None else None
        return cls("agentMessage", {"id": id, "text": text, "phase": phase, "memoryCitation": citation})

    @classmethod
    def reasoning(cls, id: str, summary: Iterable[str] = (), content: Iterable[str] = ()) -> "ThreadItem":
        return cls("reasoning", {"id": id, "summary": list(_str_tuple(summary, "summary")), "content": list(_str_tuple(content, "content"))})

    @classmethod
    def context_compaction(cls, id: str) -> "ThreadItem":
        return cls("contextCompaction", {"id": id})


@dataclass(frozen=True)
class HookPromptFragment:
    text: str
    hook_run_id: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "HookPromptFragment":
        data = _mapping(value, "HookPromptFragment")
        return cls(text=_ensure_str(data["text"], "text"), hook_run_id=_ensure_str(_pick(data, "hook_run_id", "hookRunId"), "hook_run_id"))

    def to_mapping(self) -> dict[str, str]:
        return {"text": self.text, "hook_run_id": self.hook_run_id}

    def to_camel_mapping(self) -> dict[str, str]:
        return {"text": self.text, "hookRunId": self.hook_run_id}


@dataclass(frozen=True)
class GuardianApprovalReview:
    status: GuardianApprovalReviewStatus | str
    risk_level: GuardianRiskLevel | str | None = None
    user_authorization: GuardianUserAuthorization | str | None = None
    rationale: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", GuardianApprovalReviewStatus.parse(self.status))
        object.__setattr__(self, "risk_level", GuardianRiskLevel.parse(self.risk_level) if self.risk_level is not None else None)
        object.__setattr__(self, "user_authorization", GuardianUserAuthorization.parse(self.user_authorization) if self.user_authorization is not None else None)
        object.__setattr__(self, "rationale", _optional_str(self.rationale, "rationale"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "GuardianApprovalReview":
        data = _mapping(value, "GuardianApprovalReview")
        return cls(
            status=data["status"],
            risk_level=_pick(data, "risk_level", "riskLevel"),
            user_authorization=_pick(data, "user_authorization", "userAuthorization"),
            rationale=_optional_str(data.get("rationale"), "rationale"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


class GuardianApprovalReviewAction(TaggedPayload):
    pass


class WebSearchAction(TaggedPayload):
    @classmethod
    def search(cls, query: str | None = None, queries: Iterable[str] | None = None) -> "WebSearchAction":
        return cls("search", {"query": _optional_str(query, "query"), "queries": list(_str_tuple(queries, "queries")) if queries is not None else None})

    @classmethod
    def open_page(cls, url: str | None = None) -> "WebSearchAction":
        return cls("openPage", {"url": _optional_str(url, "url")})

    @classmethod
    def find_in_page(cls, url: str | None = None, pattern: str | None = None) -> "WebSearchAction":
        return cls("findInPage", {"url": _optional_str(url, "url"), "pattern": _optional_str(pattern, "pattern")})

    @classmethod
    def other(cls) -> "WebSearchAction":
        return cls("other")


@dataclass(frozen=True)
class FileUpdateChange:
    path: str
    kind: JsonValue
    diff: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FileUpdateChange":
        data = _mapping(value, "FileUpdateChange")
        return cls(path=_ensure_str(data["path"], "path"), kind=copy.deepcopy(data["kind"]), diff=_ensure_str(data["diff"], "diff"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"path": self.path, "kind": _serialize(self.kind), "diff": self.diff}


class PatchChangeKind(TaggedPayload):
    @classmethod
    def add(cls) -> "PatchChangeKind":
        return cls("add")

    @classmethod
    def delete(cls) -> "PatchChangeKind":
        return cls("delete")

    @classmethod
    def update(cls, move_path: Path | str | None = None) -> "PatchChangeKind":
        return cls("update", {"movePath": _path_str(move_path, "move_path") if move_path is not None else None})


@dataclass(frozen=True)
class CollabAgentState:
    status: CollabAgentStatus | str
    message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", CollabAgentStatus.parse(self.status))
        object.__setattr__(self, "message", _optional_str(self.message, "message"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CollabAgentState":
        data = _mapping(value, "CollabAgentState")
        return cls(status=data["status"], message=_optional_str(data.get("message"), "message"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"status": self.status.value, "message": self.message}


@dataclass(frozen=True)
class ItemStartedNotification:
    item: ThreadItem | Mapping[str, JsonValue]
    thread_id: str
    turn_id: str
    started_at_ms: int

    def __post_init__(self) -> None:
        _validate_lifecycle(self)
        object.__setattr__(self, "item", _thread_item(self.item))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _notification_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _notification_camel_mapping(self)


@dataclass(frozen=True)
class ItemCompletedNotification:
    item: ThreadItem | Mapping[str, JsonValue]
    thread_id: str
    turn_id: str
    completed_at_ms: int

    def __post_init__(self) -> None:
        _validate_lifecycle(self)
        object.__setattr__(self, "item", _thread_item(self.item))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _notification_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _notification_camel_mapping(self)


@dataclass(frozen=True)
class RawResponseItemCompletedNotification:
    thread_id: str
    turn_id: str
    item: JsonValue

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class ItemGuardianApprovalReviewStartedNotification:
    thread_id: str
    turn_id: str
    started_at_ms: int
    review_id: str
    target_item_id: str | None
    review: GuardianApprovalReview | Mapping[str, JsonValue]
    action: GuardianApprovalReviewAction | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        _validate_review_lifecycle(self, completed=False)
        object.__setattr__(self, "review", _guardian_review(self.review))
        object.__setattr__(self, "action", _guardian_action(self.action))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _notification_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _notification_camel_mapping(self)


@dataclass(frozen=True)
class ItemGuardianApprovalReviewCompletedNotification:
    thread_id: str
    turn_id: str
    started_at_ms: int
    completed_at_ms: int
    review_id: str
    target_item_id: str | None
    decision_source: AutoReviewDecisionSource | str
    review: GuardianApprovalReview | Mapping[str, JsonValue]
    action: GuardianApprovalReviewAction | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        _validate_review_lifecycle(self, completed=True)
        object.__setattr__(self, "decision_source", AutoReviewDecisionSource.parse(self.decision_source))
        object.__setattr__(self, "review", _guardian_review(self.review))
        object.__setattr__(self, "action", _guardian_action(self.action))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _notification_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _notification_camel_mapping(self)


@dataclass(frozen=True)
class _DeltaNotification:
    thread_id: str
    turn_id: str
    item_id: str
    delta: str

    def __post_init__(self) -> None:
        _validate_thread_turn_item(self)
        object.__setattr__(self, "delta", _ensure_str(self.delta, "delta"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


class AgentMessageDeltaNotification(_DeltaNotification):
    pass


class PlanDeltaNotification(_DeltaNotification):
    pass


class CommandExecutionOutputDeltaNotification(_DeltaNotification):
    pass


class FileChangeOutputDeltaNotification(_DeltaNotification):
    pass


@dataclass(frozen=True)
class ReasoningSummaryTextDeltaNotification(_DeltaNotification):
    summary_index: int = 0

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "summary_index", _i64(self.summary_index, "summary_index"))


@dataclass(frozen=True)
class ReasoningSummaryPartAddedNotification:
    thread_id: str
    turn_id: str
    item_id: str
    summary_index: int

    def __post_init__(self) -> None:
        _validate_thread_turn_item(self)
        object.__setattr__(self, "summary_index", _i64(self.summary_index, "summary_index"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class ReasoningTextDeltaNotification(_DeltaNotification):
    content_index: int = 0

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "content_index", _i64(self.content_index, "content_index"))


@dataclass(frozen=True)
class TerminalInteractionNotification:
    thread_id: str
    turn_id: str
    item_id: str
    process_id: str
    stdin: str

    def __post_init__(self) -> None:
        _validate_thread_turn_item(self)
        object.__setattr__(self, "process_id", _ensure_str(self.process_id, "process_id"))
        object.__setattr__(self, "stdin", _ensure_str(self.stdin, "stdin"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class FileChangePatchUpdatedNotification:
    thread_id: str
    turn_id: str
    item_id: str
    changes: tuple[FileUpdateChange, ...]

    def __post_init__(self) -> None:
        _validate_thread_turn_item(self)
        object.__setattr__(self, "changes", tuple(_file_update_change(item) for item in self.changes))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "turn_id": self.turn_id, "item_id": self.item_id, "changes": [item.to_mapping() for item in self.changes]}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "turnId": self.turn_id, "itemId": self.item_id, "changes": [item.to_mapping() for item in self.changes]}


@dataclass(frozen=True)
class CommandExecutionRequestApprovalParams:
    thread_id: str
    turn_id: str
    item_id: str
    started_at_ms: int
    approval_id: str | None = None
    reason: str | None = None
    network_approval_context: JsonValue | None = None
    command: str | None = None
    cwd: Path | str | None = None
    command_actions: tuple[CommandAction, ...] | None = None
    additional_permissions: JsonValue | None = None
    proposed_execpolicy_amendment: JsonValue | None = None
    proposed_network_policy_amendments: tuple[JsonValue, ...] | None = None
    available_decisions: tuple[CommandExecutionApprovalDecision, ...] | None = None

    def __post_init__(self) -> None:
        _validate_thread_turn_item(self)
        object.__setattr__(self, "started_at_ms", _i64(self.started_at_ms, "started_at_ms"))
        object.__setattr__(self, "approval_id", _optional_str(self.approval_id, "approval_id"))
        object.__setattr__(self, "reason", _optional_str(self.reason, "reason"))
        object.__setattr__(self, "command", _optional_str(self.command, "command"))
        object.__setattr__(self, "cwd", _path_str(self.cwd, "cwd") if self.cwd is not None else None)
        if self.command_actions is not None:
            object.__setattr__(self, "command_actions", tuple(_command_action(item) for item in self.command_actions))
        if self.proposed_network_policy_amendments is not None:
            object.__setattr__(self, "proposed_network_policy_amendments", tuple(copy.deepcopy(item) for item in self.proposed_network_policy_amendments))
        if self.available_decisions is not None:
            object.__setattr__(self, "available_decisions", tuple(_approval_decision(item) for item in self.available_decisions))

    def strip_experimental_fields(self) -> None:
        object.__setattr__(self, "additional_permissions", None)

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class CommandExecutionRequestApprovalResponse:
    decision: CommandExecutionApprovalDecision | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", _approval_decision(self.decision))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"decision": self.decision.to_mapping()}


@dataclass(frozen=True)
class FileChangeRequestApprovalParams:
    thread_id: str
    turn_id: str
    item_id: str
    started_at_ms: int
    reason: str | None = None
    grant_root: Path | str | None = None

    def __post_init__(self) -> None:
        _validate_thread_turn_item(self)
        object.__setattr__(self, "started_at_ms", _i64(self.started_at_ms, "started_at_ms"))
        object.__setattr__(self, "reason", _optional_str(self.reason, "reason"))
        object.__setattr__(self, "grant_root", _path_str(self.grant_root, "grant_root") if self.grant_root is not None else None)

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class FileChangeRequestApprovalResponse:
    decision: FileChangeApprovalDecision | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", FileChangeApprovalDecision.parse(self.decision))

    def to_mapping(self) -> dict[str, str]:
        return {"decision": self.decision.value}


@dataclass(frozen=True)
class DynamicToolCallParams:
    thread_id: str
    turn_id: str
    call_id: str
    namespace: str | None
    tool: str
    arguments: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "call_id", _ensure_str(self.call_id, "call_id"))
        object.__setattr__(self, "namespace", _optional_str(self.namespace, "namespace"))
        object.__setattr__(self, "tool", _ensure_str(self.tool, "tool"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


class DynamicToolCallOutputContentItem(TaggedPayload):
    @classmethod
    def input_text(cls, text: str) -> "DynamicToolCallOutputContentItem":
        return cls("inputText", {"text": _ensure_str(text, "text")})

    @classmethod
    def input_image(cls, image_url: str) -> "DynamicToolCallOutputContentItem":
        return cls("inputImage", {"imageUrl": _ensure_str(image_url, "image_url")})


@dataclass(frozen=True)
class DynamicToolCallResponse:
    content_items: tuple[DynamicToolCallOutputContentItem, ...]
    success: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_items", tuple(_dynamic_content_item(item) for item in self.content_items))
        object.__setattr__(self, "success", _ensure_bool(self.success, "success"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"content_items": [item.to_mapping() for item in self.content_items], "success": self.success}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"contentItems": [item.to_mapping() for item in self.content_items], "success": self.success}


@dataclass(frozen=True)
class ToolRequestUserInputOption:
    label: str
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _ensure_str(self.label, "label"))
        object.__setattr__(self, "description", _ensure_str(self.description, "description"))

    def to_mapping(self) -> dict[str, str]:
        return {"label": self.label, "description": self.description}


@dataclass(frozen=True)
class ToolRequestUserInputQuestion:
    id: str
    header: str
    question: str
    is_other: bool = False
    is_secret: bool = False
    options: tuple[ToolRequestUserInputOption, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "header", _ensure_str(self.header, "header"))
        object.__setattr__(self, "question", _ensure_str(self.question, "question"))
        object.__setattr__(self, "is_other", _ensure_bool(self.is_other, "is_other"))
        object.__setattr__(self, "is_secret", _ensure_bool(self.is_secret, "is_secret"))
        if self.options is not None:
            object.__setattr__(self, "options", tuple(_tool_request_option(item) for item in self.options))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class ToolRequestUserInputParams:
    thread_id: str
    turn_id: str
    item_id: str
    questions: tuple[ToolRequestUserInputQuestion, ...]

    def __post_init__(self) -> None:
        _validate_thread_turn_item(self)
        object.__setattr__(self, "questions", tuple(_tool_request_question(item) for item in self.questions))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class ToolRequestUserInputAnswer:
    answers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "answers", _str_tuple(self.answers, "answers"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"answers": list(self.answers)}


@dataclass(frozen=True)
class ToolRequestUserInputResponse:
    answers: Mapping[str, ToolRequestUserInputAnswer | Mapping[str, JsonValue]]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "answers",
            {str(key): _tool_request_answer(value) for key, value in _mapping(self.answers, "answers").items()},
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"answers": {key: value.to_mapping() for key, value in self.answers.items()}}


def _validate_thread_turn_item(value: JsonValue) -> None:
    object.__setattr__(value, "thread_id", _ensure_str(getattr(value, "thread_id"), "thread_id"))
    object.__setattr__(value, "turn_id", _ensure_str(getattr(value, "turn_id"), "turn_id"))
    object.__setattr__(value, "item_id", _ensure_str(getattr(value, "item_id"), "item_id"))


def _validate_lifecycle(value: JsonValue) -> None:
    object.__setattr__(value, "thread_id", _ensure_str(getattr(value, "thread_id"), "thread_id"))
    object.__setattr__(value, "turn_id", _ensure_str(getattr(value, "turn_id"), "turn_id"))
    if hasattr(value, "started_at_ms"):
        object.__setattr__(value, "started_at_ms", _i64(getattr(value, "started_at_ms"), "started_at_ms"))
    if hasattr(value, "completed_at_ms"):
        object.__setattr__(value, "completed_at_ms", _i64(getattr(value, "completed_at_ms"), "completed_at_ms"))


def _validate_review_lifecycle(value: JsonValue, *, completed: bool) -> None:
    object.__setattr__(value, "thread_id", _ensure_str(getattr(value, "thread_id"), "thread_id"))
    object.__setattr__(value, "turn_id", _ensure_str(getattr(value, "turn_id"), "turn_id"))
    object.__setattr__(value, "started_at_ms", _i64(getattr(value, "started_at_ms"), "started_at_ms"))
    if completed:
        object.__setattr__(value, "completed_at_ms", _i64(getattr(value, "completed_at_ms"), "completed_at_ms"))
    object.__setattr__(value, "review_id", _ensure_str(getattr(value, "review_id"), "review_id"))
    object.__setattr__(value, "target_item_id", _optional_str(getattr(value, "target_item_id"), "target_item_id"))


def _mapping(value: JsonValue, type_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping")
    return value


def _deep_mapping(value: JsonValue, type_name: str) -> dict[str, JsonValue]:
    return copy.deepcopy(dict(_mapping(value, type_name)))


def _pick(data: Mapping[str, JsonValue], *keys: str, default: JsonValue = None) -> JsonValue:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _path_str(value: Path | str | None, field_name: str) -> str:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"{field_name} must be a path string")


def _u32(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 2**32 - 1:
        raise TypeError(f"{field_name} must be an unsigned 32-bit integer")
    return value


def _i64(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < -(2**63) or value > 2**63 - 1:
        raise TypeError(f"{field_name} must be a signed 64-bit integer")
    return value


def _list(value: JsonValue, field_name: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    return value


def _str_tuple(value: JsonValue, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result = tuple(value)
    if not all(isinstance(item, str) for item in result):
        raise TypeError(f"{field_name} must be an iterable of strings")
    return result


def _memory_citation_entry(value: MemoryCitationEntry | Mapping[str, JsonValue]) -> MemoryCitationEntry:
    if isinstance(value, MemoryCitationEntry):
        return value
    return MemoryCitationEntry.from_mapping(value)


def _memory_citation(value: MemoryCitation | Mapping[str, JsonValue]) -> MemoryCitation:
    if isinstance(value, MemoryCitation):
        return value
    return MemoryCitation.from_mapping(value)


def _thread_item(value: ThreadItem | Mapping[str, JsonValue]) -> ThreadItem:
    if isinstance(value, ThreadItem):
        return value
    return ThreadItem.from_mapping(value)


def _guardian_review(value: GuardianApprovalReview | Mapping[str, JsonValue]) -> GuardianApprovalReview:
    if isinstance(value, GuardianApprovalReview):
        return value
    return GuardianApprovalReview.from_mapping(value)


def _guardian_action(value: GuardianApprovalReviewAction | Mapping[str, JsonValue]) -> GuardianApprovalReviewAction:
    if isinstance(value, GuardianApprovalReviewAction):
        return value
    return GuardianApprovalReviewAction.from_mapping(value)


def _command_action(value: CommandAction | Mapping[str, JsonValue]) -> CommandAction:
    if isinstance(value, CommandAction):
        return value
    return CommandAction.from_mapping(value)


def _approval_decision(value: CommandExecutionApprovalDecision | Mapping[str, JsonValue]) -> CommandExecutionApprovalDecision:
    if isinstance(value, CommandExecutionApprovalDecision):
        return value
    return CommandExecutionApprovalDecision.from_mapping(value)


def _file_update_change(value: FileUpdateChange | Mapping[str, JsonValue]) -> FileUpdateChange:
    if isinstance(value, FileUpdateChange):
        return value
    return FileUpdateChange.from_mapping(value)


def _dynamic_content_item(value: DynamicToolCallOutputContentItem | Mapping[str, JsonValue]) -> DynamicToolCallOutputContentItem:
    if isinstance(value, DynamicToolCallOutputContentItem):
        return value
    return DynamicToolCallOutputContentItem.from_mapping(value)


def _tool_request_option(value: ToolRequestUserInputOption | Mapping[str, JsonValue]) -> ToolRequestUserInputOption:
    if isinstance(value, ToolRequestUserInputOption):
        return value
    data = _mapping(value, "ToolRequestUserInputOption")
    return ToolRequestUserInputOption(label=_ensure_str(data["label"], "label"), description=_ensure_str(data["description"], "description"))


def _tool_request_question(value: ToolRequestUserInputQuestion | Mapping[str, JsonValue]) -> ToolRequestUserInputQuestion:
    if isinstance(value, ToolRequestUserInputQuestion):
        return value
    data = _mapping(value, "ToolRequestUserInputQuestion")
    return ToolRequestUserInputQuestion(
        id=_ensure_str(data["id"], "id"),
        header=_ensure_str(data["header"], "header"),
        question=_ensure_str(data["question"], "question"),
        is_other=_ensure_bool(_pick(data, "is_other", "isOther", default=False), "is_other"),
        is_secret=_ensure_bool(_pick(data, "is_secret", "isSecret", default=False), "is_secret"),
        options=tuple(_tool_request_option(item) for item in data["options"]) if data.get("options") is not None else None,
    )


def _tool_request_answer(value: ToolRequestUserInputAnswer | Mapping[str, JsonValue]) -> ToolRequestUserInputAnswer:
    if isinstance(value, ToolRequestUserInputAnswer):
        return value
    data = _mapping(value, "ToolRequestUserInputAnswer")
    return ToolRequestUserInputAnswer(answers=_str_tuple(data["answers"], "answers"))


def _serialize(value: JsonValue) -> JsonValue:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return copy.deepcopy(value)


def _serialize_mapping(value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return {str(key): _serialize(item) for key, item in value.items()}


def _to_mapping(value: JsonValue) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for field in fields(value):
        result[field.name] = _serialize(getattr(value, field.name))
    return result


def _to_camel_mapping(value: JsonValue) -> dict[str, JsonValue]:
    return {_snake_to_camel(key): item for key, item in _to_mapping(value).items()}


def _notification_mapping(value: JsonValue) -> dict[str, JsonValue]:
    return _to_mapping(value)


def _notification_camel_mapping(value: JsonValue) -> dict[str, JsonValue]:
    return _to_camel_mapping(value)


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


__all__ = [
    "AgentMessageDeltaNotification",
    "AutoReviewDecisionSource",
    "CollabAgentState",
    "CollabAgentStatus",
    "CollabAgentTool",
    "CollabAgentToolCallStatus",
    "CommandAction",
    "CommandExecutionApprovalDecision",
    "CommandExecutionApprovalDecisionType",
    "CommandExecutionOutputDeltaNotification",
    "CommandExecutionRequestApprovalParams",
    "CommandExecutionRequestApprovalResponse",
    "CommandExecutionSource",
    "CommandExecutionStatus",
    "DynamicToolCallOutputContentItem",
    "DynamicToolCallParams",
    "DynamicToolCallResponse",
    "DynamicToolCallStatus",
    "FileChangeApprovalDecision",
    "FileChangeOutputDeltaNotification",
    "FileChangePatchUpdatedNotification",
    "FileChangeRequestApprovalParams",
    "FileChangeRequestApprovalResponse",
    "FileUpdateChange",
    "GuardianApprovalReview",
    "GuardianApprovalReviewAction",
    "GuardianApprovalReviewStatus",
    "GuardianCommandSource",
    "GuardianRiskLevel",
    "GuardianUserAuthorization",
    "HookPromptFragment",
    "ItemCompletedNotification",
    "ItemGuardianApprovalReviewCompletedNotification",
    "ItemGuardianApprovalReviewStartedNotification",
    "ItemStartedNotification",
    "McpToolCallStatus",
    "MemoryCitation",
    "MemoryCitationEntry",
    "PatchApplyStatus",
    "PatchChangeKind",
    "PlanDeltaNotification",
    "RawResponseItemCompletedNotification",
    "ReasoningSummaryPartAddedNotification",
    "ReasoningSummaryTextDeltaNotification",
    "ReasoningTextDeltaNotification",
    "TaggedPayload",
    "TerminalInteractionNotification",
    "ThreadItem",
    "ToolRequestUserInputAnswer",
    "ToolRequestUserInputOption",
    "ToolRequestUserInputParams",
    "ToolRequestUserInputQuestion",
    "ToolRequestUserInputResponse",
    "WebSearchAction",
]
