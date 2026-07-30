"""Codex tool-call worker owned by ``codex_tool_runner.rs``."""

from __future__ import annotations

import inspect
from typing import Any, MutableMapping

from pycodex.protocol import Op, Submission, UserInput

from .exec_approval import handle_exec_approval_request
from .outgoing_message import OutgoingMessageSender, OutgoingNotificationMeta
from .patch_approval import handle_patch_approval_request


def create_call_tool_result_with_thread_id(
    thread_id: str,
    text: str,
    is_error: bool | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": {"threadId": str(thread_id), "content": text},
    }
    if is_error is not None:
        result["isError"] = bool(is_error)
    return result


async def run_codex_tool_session(
    request_id: Any,
    initial_prompt: str,
    config: Any,
    outgoing: OutgoingMessageSender,
    thread_manager: Any,
    running_requests: MutableMapping[Any, str],
) -> None:
    try:
        created = await _maybe_await(thread_manager.start_thread(config))
    except Exception as exc:
        await outgoing.send_response(
            request_id,
            _error_result(f"Failed to start Codex session: {exc}"),
        )
        return

    thread_id = str(getattr(created, "thread_id"))
    thread = getattr(created, "thread")
    session_configured = getattr(created, "session_configured", None)
    await outgoing.send_event_as_notification(
        {"id": "", "msg": _mapping(session_configured, default_type="session_configured")},
        OutgoingNotificationMeta(request_id=request_id, thread_id=thread_id),
    )

    running_requests[request_id] = thread_id
    submission = Submission(
        id=str(request_id),
        op=Op.user_input((UserInput.text_input(initial_prompt),)),
    )
    try:
        submit_with_id = getattr(thread, "submit_with_id")
        await _maybe_await(submit_with_id(submission))
    except Exception as exc:
        running_requests.pop(request_id, None)
        await outgoing.send_response(
            request_id,
            create_call_tool_result_with_thread_id(
                thread_id,
                f"Failed to submit initial prompt: {exc}",
                True,
            ),
        )
        return
    await _run_codex_tool_session_inner(
        thread_id,
        thread,
        outgoing,
        request_id,
        running_requests,
    )


async def run_codex_tool_session_reply(
    thread_id: str,
    thread: Any,
    outgoing: OutgoingMessageSender,
    request_id: Any,
    prompt: str,
    running_requests: MutableMapping[Any, str],
) -> None:
    running_requests[request_id] = str(thread_id)
    try:
        await _maybe_await(thread.submit(Op.user_input((UserInput.text_input(prompt),))))
    except Exception as exc:
        running_requests.pop(request_id, None)
        await outgoing.send_response(
            request_id,
            create_call_tool_result_with_thread_id(
                str(thread_id),
                f"Failed to submit user input: {exc}",
                True,
            ),
        )
        return
    await _run_codex_tool_session_inner(
        str(thread_id),
        thread,
        outgoing,
        request_id,
        running_requests,
    )


async def _run_codex_tool_session_inner(
    thread_id: str,
    thread: Any,
    outgoing: OutgoingMessageSender,
    request_id: Any,
    running_requests: MutableMapping[Any, str],
) -> None:
    try:
        while True:
            event = await _maybe_await(thread.next_event())
            await outgoing.send_event_as_notification(
                event,
                OutgoingNotificationMeta(request_id=request_id, thread_id=thread_id),
            )
            kind, payload, event_id = _event_parts(event)
            if kind == "exec_approval_request":
                await handle_exec_approval_request(
                    _field(payload, "command", ()),
                    _field(payload, "cwd", "."),
                    outgoing,
                    thread,
                    request_id,
                    str(request_id),
                    event_id,
                    str(_field(payload, "call_id", "")),
                    str(_field(payload, "approval_id", _field(payload, "call_id", ""))),
                    _field(payload, "parsed_cmd", ()),
                    thread_id,
                )
                continue
            if kind == "apply_patch_approval_request":
                await handle_patch_approval_request(
                    str(_field(payload, "call_id", "")),
                    _field(payload, "reason"),
                    _field(payload, "grant_root"),
                    _field(payload, "changes", {}),
                    outgoing,
                    thread,
                    request_id,
                    str(request_id),
                    event_id,
                    thread_id,
                )
                continue
            if kind == "error":
                await outgoing.send_response(
                    request_id,
                    create_call_tool_result_with_thread_id(
                        thread_id,
                        str(_field(payload, "message", "")),
                        True,
                    ),
                )
                return
            if kind in {"task_complete", "turn_complete"}:
                await outgoing.send_response(
                    request_id,
                    create_call_tool_result_with_thread_id(
                        thread_id,
                        str(_field(payload, "last_agent_message", "") or ""),
                        None,
                    ),
                )
                return
    except Exception as exc:
        await outgoing.send_response(
            request_id,
            create_call_tool_result_with_thread_id(
                thread_id,
                f"Codex runtime error: {exc}",
                True,
            ),
        )
    finally:
        running_requests.pop(request_id, None)


def _error_result(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _event_parts(event: Any) -> tuple[str, Any, str]:
    event_id = str(_field(event, "id", ""))
    msg = _field(event, "msg", {})
    kind = _field(msg, "type", "")
    payload = _field(msg, "payload", None)
    if payload is None and isinstance(msg, dict):
        payload = {key: value for key, value in msg.items() if key != "type"}
    return str(kind), payload, event_id


def _field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _mapping(value: Any, *, default_type: str | None = None) -> Any:
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        return to_mapping()
    if isinstance(value, dict):
        return dict(value)
    if value is None and default_type is not None:
        return {"type": default_type}
    return value


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value
