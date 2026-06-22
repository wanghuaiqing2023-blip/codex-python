"""Reader loop for Rust ``codex-debug-client/src/reader.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
import threading
from typing import Any, TextIO

from .output import LabelColor, Output
from .state import PendingRequest, ReaderEvent, State


COMMAND_APPROVAL_METHOD = "item/commandExecution/requestApproval"
FILE_CHANGE_APPROVAL_METHOD = "item/fileChange/requestApproval"
ITEM_COMPLETED_METHOD = "item/completed"

ACCEPT = "accept"
DECLINE = "decline"


def start_reader(
    stdout: Iterable[str],
    stdin: TextIO | None,
    state: State,
    events: Any,
    output: Output,
    *,
    auto_approve: bool = False,
    filtered_output: bool = False,
) -> threading.Thread:
    """Spawn the debug-client reader loop.

    Rust owns this as a ``JoinHandle`` over ``BufReader<ChildStdout>``.  The
    Python port accepts any line iterable so tests and future process wrappers
    can share the same module-scoped behavior.
    """

    command_decision = ACCEPT if auto_approve else DECLINE
    file_decision = ACCEPT if auto_approve else DECLINE

    thread = threading.Thread(
        target=read_server_lines,
        args=(stdout, stdin, state, events, output, command_decision, file_decision, filtered_output),
        daemon=True,
    )
    thread.start()
    return thread


def read_server_lines(
    stdout: Iterable[str],
    stdin: TextIO | None,
    state: State,
    events: Any,
    output: Output,
    command_decision: str = DECLINE,
    file_decision: str = DECLINE,
    filtered_output: bool = False,
) -> None:
    for raw_line in stdout:
        line = str(raw_line).rstrip("\r\n")
        process_server_line(
            line,
            stdin,
            state,
            events,
            output,
            command_decision=command_decision,
            file_decision=file_decision,
            filtered_output=filtered_output,
        )


def process_server_line(
    line: str,
    stdin: TextIO | None,
    state: State,
    events: Any,
    output: Output,
    *,
    command_decision: str = DECLINE,
    file_decision: str = DECLINE,
    filtered_output: bool = False,
) -> None:
    if line:
        output.server_json_line(line, filtered_output)

    try:
        message = json.loads(line)
    except (TypeError, ValueError):
        return
    if not isinstance(message, Mapping):
        return

    if "method" in message and "id" in message:
        try:
            handle_server_request(message, command_decision, file_decision, stdin, output)
        except Exception as exc:  # pragma: no cover - defensive parity with Rust logging path.
            output.client_line(f"failed to handle server request: {exc}")
    elif "result" in message and "id" in message:
        try:
            handle_response(message, state, events)
        except Exception as exc:  # pragma: no cover - defensive parity with Rust logging path.
            output.client_line(f"failed to handle response: {exc}")
    elif "method" in message and filtered_output:
        try:
            handle_filtered_notification(message, output)
        except Exception as exc:  # pragma: no cover - defensive parity with Rust logging path.
            output.client_line(f"failed to filter notification: {exc}")


def handle_server_request(
    request: Mapping[str, Any],
    command_decision: str,
    file_decision: str,
    stdin: TextIO | None,
    output: Output,
) -> None:
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params")

    if method == COMMAND_APPROVAL_METHOD:
        decision = _normalize_decision(command_decision)
        output.client_line(
            f"auto-response for command approval {request_id!r}: {_decision_debug(decision)} ({params!r})"
        )
        send_response(stdin, request_id, {"decision": {"type": decision}})
    elif method == FILE_CHANGE_APPROVAL_METHOD:
        decision = _normalize_decision(file_decision)
        output.client_line(
            f"auto-response for file change approval {request_id!r}: {_decision_debug(decision)} ({params!r})"
        )
        send_response(stdin, request_id, {"decision": decision})


def handle_response(response: Mapping[str, Any], state: State, events: Any) -> None:
    request_id = str(response.get("id"))
    pending = state.pending.pop(request_id, None)
    if pending is None and response.get("id") in state.pending:
        pending = state.pending.pop(response.get("id"))  # type: ignore[arg-type]
    if pending is None:
        return
    if not isinstance(pending, PendingRequest):
        pending = PendingRequest(pending)

    result = response.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("response result must be an object")

    if pending in (PendingRequest.START, PendingRequest.RESUME):
        thread_id = _thread_id_from_result(result)
        state.thread_id = thread_id
        if thread_id not in state.known_threads:
            state.known_threads.append(thread_id)
        _emit_event(events, ReaderEvent.thread_ready(thread_id))
    elif pending is PendingRequest.LIST:
        data = result.get("data", [])
        if not isinstance(data, list):
            raise ValueError("thread/list response data must be a list")
        thread_ids = [_thread_id_from_value(thread) for thread in data]
        for thread_id in thread_ids:
            if thread_id not in state.known_threads:
                state.known_threads.append(thread_id)
        next_cursor = result.get("nextCursor", result.get("next_cursor"))
        _emit_event(events, ReaderEvent.thread_list(thread_ids, next_cursor))


def handle_filtered_notification(notification: Mapping[str, Any], output: Output) -> None:
    if notification.get("method") != ITEM_COMPLETED_METHOD:
        return
    params = notification.get("params")
    if not isinstance(params, Mapping):
        return
    item = params.get("item")
    thread_id = params.get("threadId", params.get("thread_id"))
    if isinstance(item, Mapping) and thread_id is not None:
        emit_filtered_item(item, str(thread_id), output)


def emit_filtered_item(item: Mapping[str, Any], thread_id: str, output: Output) -> None:
    thread_label = output.format_label(thread_id, LabelColor.THREAD)
    kind = _item_kind(item)

    if kind == "agentmessage":
        label = output.format_label("assistant", LabelColor.ASSISTANT)
        output.server_line(f"{thread_label} {label}: {item.get('text', '')}")
    elif kind == "plan":
        label = output.format_label("assistant", LabelColor.ASSISTANT)
        output.server_line(f"{thread_label} {label}: plan")
        write_multiline(output, thread_label, f"{label}:", str(item.get("text", "")))
    elif kind == "commandexecution":
        label = output.format_label("tool", LabelColor.TOOL)
        command = item.get("command", "")
        status = _status_debug(item.get("status"))
        output.server_line(f"{thread_label} {label}: command {command} ({status})")
        exit_code = item.get("exitCode", item.get("exit_code"))
        if exit_code is not None:
            exit_label = output.format_label("tool exit", LabelColor.TOOL_META)
            output.server_line(f"{thread_label} {exit_label}: {exit_code}")
        aggregated_output = item.get("aggregatedOutput", item.get("aggregated_output"))
        if aggregated_output is not None:
            output_label = output.format_label("tool output", LabelColor.TOOL_META)
            write_multiline(output, thread_label, f"{output_label}:", str(aggregated_output))
    elif kind == "filechange":
        label = output.format_label("tool", LabelColor.TOOL)
        changes = item.get("changes", [])
        change_count = len(changes) if hasattr(changes, "__len__") else 0
        status = _status_debug(item.get("status"))
        output.server_line(f"{thread_label} {label}: file change ({status}, {change_count} files)")
    elif kind == "mcptoolcall":
        label = output.format_label("tool", LabelColor.TOOL)
        status = _status_debug(item.get("status"))
        server = item.get("server", "")
        tool = item.get("tool", "")
        output.server_line(f"{thread_label} {label}: {server}.{tool} ({status})")
        arguments = item.get("arguments")
        if arguments is not None:
            args_label = output.format_label("tool args", LabelColor.TOOL_META)
            output.server_line(f"{thread_label} {args_label}: {_json_display(arguments)}")
        result = item.get("result")
        if result is not None:
            result_label = output.format_label("tool result", LabelColor.TOOL_META)
            output.server_line(f"{thread_label} {result_label}: {result!r}")
        error = item.get("error")
        if error is not None:
            error_label = output.format_label("tool error", LabelColor.TOOL_META)
            output.server_line(f"{thread_label} {error_label}: {error!r}")


def write_multiline(output: Output, thread_label: str, header: str, text: str) -> None:
    output.server_line(f"{thread_label} {header}")
    for line in text.splitlines():
        output.server_line(f"{thread_label}   {line}")


def send_response(stdin: TextIO | None, request_id: Any, response: Mapping[str, Any]) -> None:
    if stdin is None:
        raise RuntimeError("stdin already closed")
    message = {"id": request_id, "result": dict(response)}
    stdin.write(json.dumps(message, separators=(",", ":"), ensure_ascii=False))
    stdin.write("\n")
    stdin.flush()


def _normalize_decision(decision: str) -> str:
    value = str(decision).lower()
    if value in {"accept", "accepted"}:
        return ACCEPT
    if value in {"decline", "declined", "deny", "denied"}:
        return DECLINE
    raise ValueError(f"unknown approval decision: {decision}")


def _decision_debug(decision: str) -> str:
    return "Accept" if decision == ACCEPT else "Decline"


def _thread_id_from_result(result: Mapping[str, Any]) -> str:
    thread = result.get("thread")
    return _thread_id_from_value(thread)


def _thread_id_from_value(value: Any) -> str:
    if isinstance(value, Mapping):
        thread_id = value.get("id", value.get("threadId", value.get("thread_id")))
        if thread_id is not None:
            return str(thread_id)
    raise ValueError("missing thread id")


def _emit_event(events: Any, event: ReaderEvent) -> None:
    if hasattr(events, "send"):
        events.send(event)
    elif hasattr(events, "put"):
        events.put(event)
    elif hasattr(events, "append"):
        events.append(event)


def _item_kind(item: Mapping[str, Any]) -> str:
    raw = item.get("type", item.get("kind", item.get("itemType", "")))
    return "".join(ch for ch in str(raw).lower() if ch.isalnum())


def _status_debug(status: Any) -> str:
    return "" if status is None else str(status)


def _json_display(value: Any) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


__all__ = [
    "ACCEPT",
    "COMMAND_APPROVAL_METHOD",
    "DECLINE",
    "FILE_CHANGE_APPROVAL_METHOD",
    "ITEM_COMPLETED_METHOD",
    "emit_filtered_item",
    "handle_filtered_notification",
    "handle_response",
    "handle_server_request",
    "process_server_line",
    "read_server_lines",
    "send_response",
    "start_reader",
    "write_multiline",
]
