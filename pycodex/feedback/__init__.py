"""Python interface for Rust ``codex-feedback``."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Mapping


DOCTOR_REPORT_ATTACHMENT_FILENAME = "codex-doctor-report.json"
WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME = "windows-sandbox.log"
FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME = "codex-connectivity-diagnostics.txt"
PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)


@dataclass(frozen=True)
class FeedbackRequestTags:
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


@dataclass(frozen=True)
class FeedbackDiagnostic:
    headline: str
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FeedbackDiagnostics:
    diagnostics: list[FeedbackDiagnostic] = field(default_factory=list)

    @classmethod
    def new(cls, diagnostics: Iterable[FeedbackDiagnostic]) -> "FeedbackDiagnostics":
        return cls(list(diagnostics))

    @classmethod
    def collect_from_env(cls, env: Mapping[str, str] | None = None) -> "FeedbackDiagnostics":
        return cls.collect_from_pairs((os.environ if env is None else env).items())

    @classmethod
    def collect_from_pairs(cls, pairs: Iterable[tuple[Any, Any]]) -> "FeedbackDiagnostics":
        env = {str(key): str(value) for key, value in pairs}
        proxy_details = [f"{key} = {env[key]}" for key in PROXY_ENV_VARS if key in env]
        if not proxy_details:
            return cls()
        return cls(
            [
                FeedbackDiagnostic(
                    headline="Proxy environment variables are set and may affect connectivity.",
                    details=proxy_details,
                )
            ]
        )

    def is_empty(self) -> bool:
        return not self.diagnostics

    def attachment_text(self) -> str | None:
        if not self.diagnostics:
            return None
        lines = ["Connectivity diagnostics", ""]
        for diagnostic in self.diagnostics:
            lines.append(f"- {diagnostic.headline}")
            lines.extend(f"  - {detail}" for detail in diagnostic.details)
        return "\n".join(lines)

    def to_json_text(self) -> str:
        return json.dumps(
            [
                {
                    "headline": diagnostic.headline,
                    "details": list(diagnostic.details),
                }
                for diagnostic in self.diagnostics
            ],
            ensure_ascii=False,
        )


@dataclass(frozen=True)
class FeedbackSnapshot:
    session_id: str | None
    logs: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FeedbackAttachmentPath:
    path: Path
    filename: str | None = None


@dataclass(frozen=True)
class FeedbackAttachment:
    filename: str
    data: bytes


@dataclass(frozen=True)
class FeedbackUploadOptions:
    endpoint: str | None = None
    attachments: list[FeedbackAttachment] = field(default_factory=list)
    include_logs: bool = True


class FeedbackMakeWriter:
    def __init__(self, feedback: "CodexFeedback") -> None:
        self.feedback = feedback

    def __call__(self) -> "FeedbackWriter":
        return FeedbackWriter(self.feedback)


class FeedbackWriter:
    def __init__(self, feedback: "CodexFeedback") -> None:
        self.feedback = feedback

    def write(self, data: str | bytes) -> int:
        text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
        self.feedback.write(text)
        return len(data)

    def flush(self) -> None:
        return None


class CodexFeedback:
    def __init__(self, capacity: int = 400) -> None:
        self._lines: deque[str] = deque(maxlen=capacity)
        self._metadata: dict[str, Any] = {}

    @classmethod
    def new(cls) -> "CodexFeedback":
        return cls()

    def write(self, text: str) -> None:
        for line in text.splitlines():
            self._lines.append(line)

    def make_writer(self) -> FeedbackMakeWriter:
        return FeedbackMakeWriter(self)

    def logger_layer(self, *args: Any, **kwargs: Any) -> "CodexFeedback":
        return self

    def metadata_layer(self, *args: Any, **kwargs: Any) -> "CodexFeedback":
        return self

    def snapshot(self, session_id: str | None = None) -> FeedbackSnapshot:
        return FeedbackSnapshot(session_id=session_id, logs="\n".join(self._lines), metadata=dict(self._metadata))


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
        raise NotImplementedError("codex-feedback upload backend is not ported")


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
    "FeedbackUploadOptions",
    "FeedbackWriter",
    "PROXY_ENV_VARS",
    "WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME",
    "emit_feedback_request_tags",
    "emit_feedback_request_tags_with_auth_env",
]
