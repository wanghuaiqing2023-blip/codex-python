"""Python interface for Rust ``codex-feedback``."""

from __future__ import annotations

from collections import OrderedDict
from collections import deque
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from .feedback_diagnostics import (
    FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME,
    PROXY_ENV_VARS,
    FeedbackDiagnostic,
    FeedbackDiagnostics,
)


DOCTOR_REPORT_ATTACHMENT_FILENAME = "codex-doctor-report.json"
WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME = "windows-sandbox.log"
DEFAULT_MAX_BYTES = 4 * 1024 * 1024
FEEDBACK_TAGS_TARGET = "feedback_tags"
MAX_FEEDBACK_TAGS = 64
_RESERVED_UPLOAD_TAGS = frozenset({"thread_id", "classification", "cli_version", "session_source", "reason"})


@dataclass(frozen=True)
class FeedbackRequestTags:
    endpoint: str = ""
    auth_header_attached: bool = False
    auth_header_name: str | None = None
    auth_mode: str | None = None
    auth_retry_after_unauthorized: bool | None = None
    auth_recovery_mode: str | None = None
    auth_recovery_phase: str | None = None
    auth_connection_reused: bool | None = None
    auth_request_id: str | None = None
    auth_cf_ray: str | None = None
    auth_error: str | None = None
    auth_error_code: str | None = None
    auth_recovery_followup_success: bool | None = None
    auth_recovery_followup_status: int | None = None
    # Compatibility fields retained from the earlier Python facade.
    client: str | None = None
    codex_version: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    account_id: str | None = None


_LAST_FEEDBACK_REQUEST_TAGS: FeedbackRequestTags | None = None


def emit_feedback_request_tags(tags: FeedbackRequestTags) -> None:
    global _LAST_FEEDBACK_REQUEST_TAGS
    _LAST_FEEDBACK_REQUEST_TAGS = tags


def emit_feedback_request_tags_with_auth_env(tags: FeedbackRequestTags, auth_env: Any | None = None) -> None:
    emit_feedback_request_tags(tags)


def feedback_request_tags_snapshot(tags: FeedbackRequestTags, auth_env: Any | None = None) -> dict[str, str]:
    snapshot = {
        "endpoint": tags.endpoint,
        "auth_header_attached": _rust_bool(tags.auth_header_attached),
        "auth_header_name": tags.auth_header_name or "",
        "auth_mode": tags.auth_mode or "",
        "auth_retry_after_unauthorized": _optional_bool(tags.auth_retry_after_unauthorized),
        "auth_recovery_mode": tags.auth_recovery_mode or "",
        "auth_recovery_phase": tags.auth_recovery_phase or "",
        "auth_connection_reused": _optional_bool(tags.auth_connection_reused),
        "auth_request_id": tags.auth_request_id or "",
        "auth_cf_ray": tags.auth_cf_ray or "",
        "auth_error": tags.auth_error or "",
        "auth_error_code": tags.auth_error_code or "",
        "auth_recovery_followup_success": _optional_bool(tags.auth_recovery_followup_success),
        "auth_recovery_followup_status": "" if tags.auth_recovery_followup_status is None else str(tags.auth_recovery_followup_status),
    }
    if auth_env is not None:
        snapshot.update(
            {
                "auth_env_openai_api_key_present": _rust_bool(_get_value(auth_env, "openai_api_key_env_present", False)),
                "auth_env_codex_api_key_present": _rust_bool(_get_value(auth_env, "codex_api_key_env_present", False)),
                "auth_env_codex_api_key_enabled": _rust_bool(_get_value(auth_env, "codex_api_key_env_enabled", False)),
                "auth_env_provider_key_name": str(_get_value(auth_env, "provider_env_key_name", "") or ""),
                "auth_env_provider_key_present": _optional_bool(_get_value(auth_env, "provider_env_key_present", None)),
                "auth_env_refresh_token_url_override_present": _rust_bool(
                    _get_value(auth_env, "refresh_token_url_override_present", False)
                ),
            }
        )
    for key in ("client", "codex_version", "session_id", "user_id", "account_id"):
        value = getattr(tags, key)
        if value is not None:
            snapshot[key] = str(value)
    return snapshot


def feedback_diagnostics_to_json_text(diagnostics: FeedbackDiagnostics) -> str:
    return json.dumps(
        [
            {
                "headline": diagnostic.headline,
                "details": list(diagnostic.details),
            }
            for diagnostic in diagnostics.diagnostics
        ],
        ensure_ascii=False,
    )


@dataclass(frozen=True)
class FeedbackSnapshot:
    thread_id: str
    bytes: bytes = b""
    tags: dict[str, str] = field(default_factory=dict)
    feedback_diagnostics: FeedbackDiagnostics = field(default_factory=FeedbackDiagnostics)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def session_id(self) -> str:
        return self.thread_id

    @property
    def logs(self) -> str:
        return self.bytes.decode("utf-8", errors="replace")

    def as_bytes(self) -> bytes:
        return bytes(self.bytes)

    def with_feedback_diagnostics(self, feedback_diagnostics: FeedbackDiagnostics) -> "FeedbackSnapshot":
        return FeedbackSnapshot(
            thread_id=self.thread_id,
            bytes=self.bytes,
            tags=dict(self.tags),
            feedback_diagnostics=feedback_diagnostics,
            metadata=dict(self.metadata),
        )

    def feedback_diagnostics_attachment_text(self, include_logs: bool) -> str | None:
        if not include_logs:
            return None
        return self.feedback_diagnostics.attachment_text()

    def save_to_temp_file(self) -> Path:
        path = Path(os.getenv("TMP", os.getenv("TEMP", "."))) / f"codex-feedback-{self.thread_id}.log"
        path.write_bytes(self.as_bytes())
        return path

    def upload_tags(
        self,
        classification: str,
        reason: str | None = None,
        client_tags: Mapping[str, str] | None = None,
        session_source: Any | None = None,
    ) -> dict[str, str]:
        tags: "OrderedDict[str, str]" = OrderedDict(
            [
                ("thread_id", self.thread_id),
                ("classification", classification),
                ("cli_version", _cli_version()),
            ]
        )
        if session_source is not None:
            tags["session_source"] = str(session_source)
        if reason is not None:
            tags["reason"] = reason

        for source in (client_tags or {}, self.tags):
            for key, value in source.items():
                key = str(key)
                if key in _RESERVED_UPLOAD_TAGS or key in tags:
                    continue
                tags[key] = str(value)
        return dict(tags)

    def feedback_attachments(
        self,
        include_logs: bool,
        extra_attachments: Sequence["FeedbackAttachment"] = (),
        extra_attachment_paths: Sequence["FeedbackAttachmentPath"] = (),
        logs_override: bytes | bytearray | str | None = None,
    ) -> list["FeedbackAttachment"]:
        attachments: list[FeedbackAttachment] = []
        if include_logs:
            attachments.append(
                FeedbackAttachment(
                    filename="codex-logs.log",
                    content_type="text/plain",
                    data=_bytes_or_default(logs_override, self.as_bytes()),
                )
            )
        attachments.extend(extra_attachments)
        diagnostics_text = self.feedback_diagnostics_attachment_text(include_logs)
        if diagnostics_text is not None:
            attachments.append(
                FeedbackAttachment(
                    filename=FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME,
                    content_type="text/plain",
                    data=diagnostics_text.encode("utf-8"),
                )
            )
        for attachment_path in extra_attachment_paths:
            try:
                data = Path(attachment_path.path).read_bytes()
            except OSError:
                continue
            attachments.append(
                FeedbackAttachment(
                    filename=attachment_path.attachment_filename_override
                    or (Path(attachment_path.path).name or "extra-log.log"),
                    content_type="text/plain",
                    data=data,
                )
            )
        return attachments

    def upload_feedback(self, options: "FeedbackUploadOptions") -> None:
        classification = _get_value(options, "classification", "other")
        reason = _get_value(options, "reason", None)
        tags = _get_value(options, "tags", None)
        include_logs = bool(_get_value(options, "include_logs", True))
        extra_attachments = _get_value(options, "extra_attachments", ())
        extra_attachment_paths = _get_value(options, "extra_attachment_paths", ())
        logs_override = _get_value(options, "logs_override", None)
        session_source = _get_value(options, "session_source", None)
        event = FeedbackUploadEvent(
            level="error" if classification in {"bug", "bad_result", "safety_check"} else "info",
            message=f"[{display_classification(classification)}]: Codex session {self.thread_id}",
            tags=self.upload_tags(classification, reason, tags, session_source),
            exception_value=reason,
            attachments=self.feedback_attachments(
                include_logs,
                extra_attachments,
                extra_attachment_paths,
                logs_override,
            ),
        )
        sender = _get_value(options, "sender", None)
        if sender is not None:
            sender(event)
        object.__setattr__(self, "_last_upload_event", event)


@dataclass(frozen=True)
class FeedbackAttachmentPath:
    path: Path
    filename: str | None = None
    attachment_filename_override: str | None = None

    def __post_init__(self) -> None:
        if self.attachment_filename_override is None and self.filename is not None:
            object.__setattr__(self, "attachment_filename_override", self.filename)


@dataclass(frozen=True)
class FeedbackAttachment:
    filename: str
    data: bytes = b""
    content_type: str | None = None
    buffer: bytes | None = None

    def __post_init__(self) -> None:
        if self.buffer is not None and self.data == b"":
            object.__setattr__(self, "data", bytes(self.buffer))
        else:
            object.__setattr__(self, "data", _bytes_or_default(self.data, b""))
        object.__setattr__(self, "buffer", self.data)


@dataclass(frozen=True)
class FeedbackUploadOptions:
    classification: str = "other"
    reason: str | None = None
    tags: Mapping[str, str] | None = None
    include_logs: bool = True
    extra_attachments: Sequence[FeedbackAttachment] = ()
    extra_attachment_paths: Sequence[FeedbackAttachmentPath] = ()
    session_source: Any | None = None
    logs_override: bytes | bytearray | str | None = None
    sender: Any | None = None
    # Compatibility fields from the earlier Python facade.
    endpoint: str | None = None
    attachments: list[FeedbackAttachment] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.attachments and not self.extra_attachments:
            object.__setattr__(self, "extra_attachments", tuple(self.attachments))


@dataclass(frozen=True)
class FeedbackUploadEvent:
    level: str
    message: str
    tags: dict[str, str]
    exception_value: str | None = None
    attachments: list[FeedbackAttachment] = field(default_factory=list)


class FeedbackMakeWriter:
    def __init__(self, feedback: "CodexFeedback") -> None:
        self.feedback = feedback

    def __call__(self) -> "FeedbackWriter":
        return FeedbackWriter(self.feedback)

    def make_writer(self) -> "FeedbackWriter":
        return FeedbackWriter(self.feedback)


class FeedbackWriter:
    def __init__(self, feedback: "CodexFeedback") -> None:
        self.feedback = feedback

    def write(self, data: str | bytes) -> int:
        self.feedback.push_bytes(data)
        return len(data)

    def flush(self) -> None:
        return None


class CodexFeedback:
    def __init__(self, capacity: int = DEFAULT_MAX_BYTES) -> None:
        self._max_bytes = max(0, int(capacity))
        self._bytes: deque[int] = deque()
        self._tags: "OrderedDict[str, str]" = OrderedDict()

    @classmethod
    def new(cls) -> "CodexFeedback":
        return cls()

    @classmethod
    def with_capacity(cls, max_bytes: int) -> "CodexFeedback":
        return cls(max_bytes)

    def write(self, text: str) -> None:
        self.push_bytes(text.encode("utf-8"))

    def push_bytes(self, data: bytes | bytearray | str) -> None:
        chunk = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if not chunk or self._max_bytes == 0:
            return
        if len(chunk) >= self._max_bytes:
            self._bytes.clear()
            self._bytes.extend(chunk[-self._max_bytes :])
            return
        needed = len(self._bytes) + len(chunk)
        if needed > self._max_bytes:
            for _ in range(needed - self._max_bytes):
                self._bytes.popleft()
        self._bytes.extend(chunk)

    def make_writer(self) -> FeedbackMakeWriter:
        return FeedbackMakeWriter(self)

    def logger_layer(self, *args: Any, **kwargs: Any) -> "CodexFeedback":
        return self

    def metadata_layer(self, *args: Any, **kwargs: Any) -> "CodexFeedback":
        return self

    def record_tags(self, tags: Mapping[str, Any]) -> None:
        for key, value in tags.items():
            key = str(key)
            if len(self._tags) >= MAX_FEEDBACK_TAGS and key not in self._tags:
                continue
            self._tags[key] = _rust_value(value)

    def snapshot(self, session_id: str | None = None) -> FeedbackSnapshot:
        thread_id = str(session_id) if session_id is not None else f"no-active-thread-{uuid4()}"
        return FeedbackSnapshot(
            thread_id=thread_id,
            bytes=bytes(self._bytes),
            tags=dict(self._tags),
            feedback_diagnostics=FeedbackDiagnostics.collect_from_env(),
            metadata=dict(self._tags),
        )


@dataclass
class FeedbackUpload:
    diagnostics: FeedbackDiagnostics = field(default_factory=FeedbackDiagnostics)

    def feedback_diagnostics(self) -> FeedbackDiagnostics:
        return self.diagnostics

    def with_feedback_diagnostics(self, feedback_diagnostics: FeedbackDiagnostics) -> "FeedbackUpload":
        self.diagnostics = feedback_diagnostics
        return self

    def feedback_diagnostics_attachment_text(self, include_logs: bool) -> str | None:
        if not include_logs:
            return None
        return self.diagnostics.attachment_text()

    def save_to_temp_file(self) -> Path:
        handle = NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8")
        with handle:
            handle.write(self.diagnostics.attachment_text() or "")
        return Path(handle.name)

    def upload_feedback(self, options: FeedbackUploadOptions) -> None:
        FeedbackSnapshot(
            thread_id=f"no-active-thread-{uuid4()}",
            feedback_diagnostics=self.diagnostics,
        ).upload_feedback(options)


def display_classification(classification: str) -> str:
    if classification == "bug":
        return "Bug"
    if classification == "bad_result":
        return "Bad result"
    if classification == "good_result":
        return "Good result"
    if classification == "safety_check":
        return "Safety check"
    return "Other"


def _cli_version() -> str:
    return os.getenv("CODEX_PYTHON_VERSION", "0.0.0")


def _bytes_or_default(value: bytes | bytearray | str | None, default: bytes) -> bytes:
    if value is None:
        return bytes(default)
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)


def _rust_bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _optional_bool(value: Any) -> str:
    return "" if value is None else _rust_bool(value)


def _rust_value(value: Any) -> str:
    if isinstance(value, bool):
        return _rust_bool(value)
    return str(value)


def _get_value(target: Any, name: str, default: Any = None) -> Any:
    if isinstance(target, Mapping):
        return target.get(name, default)
    return getattr(target, name, default)


__all__ = [
    "CodexFeedback",
    "DOCTOR_REPORT_ATTACHMENT_FILENAME",
    "FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME",
    "FeedbackAttachment",
    "FeedbackAttachmentPath",
    "FeedbackDiagnostic",
    "FeedbackDiagnostics",
    "FeedbackMakeWriter",
    "FeedbackRequestTags",
    "FeedbackSnapshot",
    "FeedbackUpload",
    "FeedbackUploadEvent",
    "FeedbackUploadOptions",
    "FeedbackWriter",
    "PROXY_ENV_VARS",
    "WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME",
    "display_classification",
    "emit_feedback_request_tags",
    "emit_feedback_request_tags_with_auth_env",
    "feedback_request_tags_snapshot",
]
