"""Feedback request processor ported from ``app-server/src/request_processors/feedback_processor.rs``."""

from __future__ import annotations

import inspect
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server.request_processors_feedback_doctor_report import doctor_feedback_report
from pycodex.app_server_protocol import FeedbackUploadParams, FeedbackUploadResponse, JSONRPCErrorError
from pycodex.feedback import (
    WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME,
    FeedbackAttachment,
    FeedbackAttachmentPath,
)

JsonValue = Any
DoctorReportFactory = Callable[[Any], Awaitable[Any] | Any]
WindowsSandboxLogResolver = Callable[[Path], Path | None]


@dataclass(frozen=True)
class AppServerFeedbackUploadOptions:
    """App-server projection of Rust ``codex_feedback::FeedbackUploadOptions``."""

    classification: str
    reason: str | None
    tags: dict[str, str] | None
    include_logs: bool
    extra_attachments: tuple[FeedbackAttachment, ...] = ()
    extra_attachment_paths: tuple[FeedbackAttachmentPath, ...] = ()
    session_source: str | None = None
    logs_override: Any | None = None


@dataclass
class FeedbackRequestProcessorError(Exception):
    error: JSONRPCErrorError

    def __post_init__(self) -> None:
        Exception.__init__(self, self.error.message)


@dataclass
class FeedbackRequestProcessor:
    auth_manager: Any
    thread_manager: Any
    config: Any
    feedback: Any
    log_db: Any | None = None
    state_db: Any | None = None
    doctor_report_factory: DoctorReportFactory | None = None
    windows_log_resolver: WindowsSandboxLogResolver | None = None

    @classmethod
    def new(
        cls,
        auth_manager: Any,
        thread_manager: Any,
        config: Any,
        feedback: Any,
        log_db: Any | None = None,
        state_db: Any | None = None,
    ) -> "FeedbackRequestProcessor":
        return cls(auth_manager, thread_manager, config, feedback, log_db, state_db)

    async def feedback_upload(
        self,
        params: FeedbackUploadParams | Mapping[str, JsonValue],
    ) -> FeedbackUploadResponse:
        parsed = params if isinstance(params, FeedbackUploadParams) else FeedbackUploadParams.from_mapping(params)
        return await self.upload_feedback_response(parsed)

    async def upload_feedback_response(self, params: FeedbackUploadParams) -> FeedbackUploadResponse:
        if not bool(_get(self.config, "feedback_enabled", True)):
            raise FeedbackRequestProcessorError(invalid_request("sending feedback is disabled by configuration"))

        conversation_id = _parse_thread_id(params.thread_id)
        if params.thread_id is not None and conversation_id is None:
            raise FeedbackRequestProcessorError(invalid_request("invalid thread id: empty thread id"))

        await self._emit_cached_auth_feedback_tags()
        snapshot = _call_or_get(self.feedback, "snapshot", conversation_id)
        response_thread_id = str(_get(snapshot, "thread_id", conversation_id or ""))

        upload_tags = dict(params.tags or {})
        feedback_thread_ids: list[str] = []
        sqlite_feedback_logs: Any | None = None
        state_db_ctx = self.state_db if params.include_logs else None

        if params.include_logs:
            await _call_optional(self.log_db, "flush")
            feedback_thread_ids = await self._feedback_thread_ids(conversation_id)
            sqlite_feedback_logs = await self._sqlite_feedback_logs(state_db_ctx, feedback_thread_ids)

        attachment_paths = await self._attachment_paths(
            include_logs=params.include_logs,
            conversation_id=conversation_id,
            feedback_thread_ids=feedback_thread_ids,
            state_db_ctx=state_db_ctx,
            extra_log_files=params.extra_log_files,
        )
        extra_attachments = await self._doctor_report_attachments(params.include_logs, upload_tags)
        session_source = _call_or_get(self.thread_manager, "session_source")

        options = AppServerFeedbackUploadOptions(
            classification=params.classification,
            reason=params.reason,
            tags=upload_tags or None,
            include_logs=params.include_logs,
            extra_attachments=tuple(extra_attachments),
            extra_attachment_paths=tuple(attachment_paths),
            session_source=None if session_source is None else str(session_source),
            logs_override=sqlite_feedback_logs,
        )

        try:
            await _maybe_await(_call_or_get(snapshot, "upload_feedback", options))
        except Exception as exc:
            raise FeedbackRequestProcessorError(internal_error(f"failed to upload feedback: {exc}")) from exc

        return FeedbackUploadResponse(thread_id=response_thread_id)

    async def resolve_rollout_path(self, conversation_id: str, state_db_ctx: Any | None = None) -> Path | None:
        try:
            conversation = await _maybe_await(self.thread_manager.get_thread(conversation_id))
        except Exception:
            conversation = None
        rollout_path = _call_or_get(conversation, "rollout_path")
        if rollout_path is not None:
            return Path(rollout_path)

        state_db_ctx = self.state_db if state_db_ctx is None else state_db_ctx
        if state_db_ctx is None:
            return None
        try:
            return _path_or_none(
                await _call_with_optional_args(
                    state_db_ctx,
                    "find_rollout_path_by_id",
                    (conversation_id, None),
                    (conversation_id,),
                )
            )
        except Exception:
            return None

    async def _emit_cached_auth_feedback_tags(self) -> None:
        auth_cached = await _maybe_await(_call_or_get(self.auth_manager, "auth_cached"))
        if auth_cached is None:
            return
        # Rust logs cached ChatGPT user/account ids for diagnostics. The Python
        # projection preserves the hook point without requiring auth internals.
        _call_or_get(auth_cached, "get_chatgpt_user_id")
        _call_or_get(auth_cached, "get_account_id")

    async def _feedback_thread_ids(self, conversation_id: str | None) -> list[str]:
        if conversation_id is None:
            return []
        try:
            ids = await _maybe_await(self.thread_manager.list_agent_subtree_thread_ids(conversation_id))
            return [str(thread_id) for thread_id in ids]
        except Exception:
            ids = [conversation_id]

        if self.state_db is None:
            return ids
        for status in ("Open", "Closed"):
            try:
                descendants = await _call_with_optional_args(
                    self.state_db,
                    "list_thread_spawn_descendants_with_status",
                    (conversation_id, status),
                    (conversation_id, status.lower()),
                )
            except Exception:
                continue
            ids.extend(str(thread_id) for thread_id in descendants or ())
        return _dedupe_strings(ids)

    async def _sqlite_feedback_logs(self, state_db_ctx: Any | None, feedback_thread_ids: Sequence[str]) -> Any | None:
        if state_db_ctx is None or not feedback_thread_ids:
            return None
        try:
            logs = await _maybe_await(state_db_ctx.query_feedback_logs_for_threads([str(item) for item in feedback_thread_ids]))
        except Exception:
            return None
        return logs or None

    async def _attachment_paths(
        self,
        *,
        include_logs: bool,
        conversation_id: str | None,
        feedback_thread_ids: Sequence[str],
        state_db_ctx: Any | None,
        extra_log_files: Sequence[Path] | None,
    ) -> list[FeedbackAttachmentPath]:
        paths: list[FeedbackAttachmentPath] = []
        seen: set[Path] = set()

        if include_logs:
            for thread_id in feedback_thread_ids:
                path = await self.resolve_rollout_path(str(thread_id), state_db_ctx)
                _append_attachment_path(paths, seen, path)

            if conversation_id is not None:
                guardian_path = await self._guardian_trunk_rollout_path(conversation_id)
                _append_attachment_path(
                    paths,
                    seen,
                    guardian_path,
                    filename=auto_review_rollout_filename(conversation_id),
                )

            sandbox_attachment = windows_sandbox_log_attachment(
                _path_or_none(_get(self.config, "codex_home")),
                resolver=self.windows_log_resolver,
            )
            if sandbox_attachment is not None:
                _append_attachment_path(
                    paths,
                    seen,
                    sandbox_attachment.path,
                    filename=sandbox_attachment.filename,
                )

        for path in extra_log_files or ():
            _append_attachment_path(paths, seen, path)
        return paths

    async def _guardian_trunk_rollout_path(self, conversation_id: str) -> Path | None:
        try:
            conversation = await _maybe_await(self.thread_manager.get_thread(conversation_id))
        except Exception:
            return None
        return _path_or_none(await _maybe_await(_call_or_get(conversation, "guardian_trunk_rollout_path")))

    async def _doctor_report_attachments(self, include_logs: bool, upload_tags: dict[str, str]) -> list[FeedbackAttachment]:
        if not include_logs:
            return []
        factory = self.doctor_report_factory or doctor_feedback_report
        report = await _maybe_await(factory(self.config))
        if report is None:
            return []
        for key, value in dict(_get(report, "tags", {})).items():
            upload_tags.setdefault(str(key), str(value))
        attachment = _get(report, "attachment")
        return [] if attachment is None else [attachment]


def auto_review_rollout_filename(thread_id: str) -> str:
    return f"auto-review-rollout-{thread_id}.jsonl"


def windows_sandbox_log_attachment(
    codex_home: Path | str | None,
    *,
    resolver: WindowsSandboxLogResolver | None = None,
) -> FeedbackAttachmentPath | None:
    if codex_home is None:
        return None
    codex_home_path = Path(codex_home)
    if resolver is None:
        if sys.platform != "win32":
            return None
        try:
            from pycodex.windows_sandbox import current_log_file_path_for_codex_home

            path = current_log_file_path_for_codex_home(codex_home_path)
        except Exception:
            return None
    else:
        path = resolver(codex_home_path)
    path = _path_or_none(path)
    if path is None or not path.is_file():
        return None
    return FeedbackAttachmentPath(path=path, filename=WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME)


def _parse_thread_id(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _append_attachment_path(
    paths: list[FeedbackAttachmentPath],
    seen: set[Path],
    path: Path | str | None,
    *,
    filename: str | None = None,
) -> None:
    normalized = _path_or_none(path)
    if normalized is None:
        return
    key = normalized.resolve(strict=False)
    if key in seen:
        return
    seen.add(key)
    paths.append(FeedbackAttachmentPath(path=normalized, filename=filename))


def _path_or_none(value: Any) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    return Path(value)


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


async def _call_optional(target: Any, method: str, *args: Any) -> Any:
    if target is None:
        return None
    return await _maybe_await(_call_or_get(target, method, *args))


async def _call_with_optional_args(target: Any, method: str, *candidates: tuple[Any, ...]) -> Any:
    func = _get(target, method)
    if not callable(func):
        return None
    last_type_error: TypeError | None = None
    for args in candidates:
        try:
            return await _maybe_await(func(*args))
        except TypeError as exc:
            last_type_error = exc
            continue
    if last_type_error is not None:
        raise last_type_error
    return None


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _call_or_get(target: Any, name: str, *args: Any) -> Any:
    value = _get(target, name)
    if callable(value):
        return value(*args)
    return value


def _get(target: Any, name: str, default: Any = None) -> Any:
    if target is None:
        return default
    if isinstance(target, Mapping):
        if name in target:
            return target[name]
        camel = _snake_to_camel(name)
        return target.get(camel, default)
    return getattr(target, name, default)


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


__all__ = [
    "AppServerFeedbackUploadOptions",
    "FeedbackRequestProcessor",
    "FeedbackRequestProcessorError",
    "auto_review_rollout_filename",
    "windows_sandbox_log_attachment",
]
