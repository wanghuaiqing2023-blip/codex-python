"""Delegated sub-agent event bridge ported from ``codex_delegate.rs``.

The Rust module starts a child Codex session, forwards normal events to the
caller, and intercepts approval/input/permission events so the parent session can
answer them. This Python port keeps that boundary injectable: callers provide a
spawned Codex-like object with ``next_event`` and ``submit`` methods, while this
module preserves the routing and cancellation behavior.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, MutableMapping, Sequence

from pycodex.core.guardian.review import (
    GUARDIAN_APPROVAL_REQUEST_SOURCE_DELEGATED_SUBAGENT,
    GuardianApplyPatchApprovalRequest,
    GuardianShellApprovalRequest,
    SANDBOX_PERMISSIONS_USE_DEFAULT,
    SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS,
    apply_patch_files_for_guardian,
    format_apply_patch_changes_for_guardian,
    routes_approval_to_guardian,
)
from pycodex.core.mcp_tool_call import (
    MCP_TOOL_APPROVAL_ACCEPT,
    MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION,
    MCP_TOOL_APPROVAL_DECLINE_SYNTHETIC,
    MCP_TOOL_APPROVAL_QUESTION_ID_PREFIX,
    is_mcp_tool_approval_question_id,
)
from pycodex.core.tools.handlers.utils import normalize_request_permissions_response
from pycodex.protocol import (
    Event,
    EventMsg,
    Op,
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsResponse,
    RequestUserInputAnswer,
    RequestUserInputArgs,
    RequestUserInputResponse,
    ReviewDecision,
)


SUBMISSION_CHANNEL_CAPACITY = 1024


class CancellationToken:
    """Small asyncio equivalent of tokio_util's cancellation token."""

    def __init__(self, parent: "CancellationToken | None" = None) -> None:
        self._event = asyncio.Event()
        self._parent = parent

    def cancel(self) -> None:
        self._event.set()

    def child_token(self) -> "CancellationToken":
        return CancellationToken(self)

    def is_cancelled(self) -> bool:
        return self._event.is_set() or bool(self._parent and self._parent.is_cancelled())

    async def cancelled(self) -> None:
        if self.is_cancelled():
            return
        own = asyncio.create_task(self._event.wait())
        tasks = [own]
        if self._parent is not None:
            tasks.append(asyncio.create_task(self._parent.cancelled()))
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            await task


@dataclass(slots=True)
class CodexDelegateIo:
    """I/O handles returned for an interactive delegated Codex thread."""

    codex: Any
    events_rx: asyncio.Queue[Event]
    ops_tx: asyncio.Queue[Any]
    event_task: asyncio.Task[Any] | None = None
    ops_task: asyncio.Task[Any] | None = None

    async def next_event(self) -> Event:
        return await self.events_rx.get()

    async def submit(self, op: Any) -> None:
        await self.ops_tx.put(op)


SpawnCodexThread = Callable[..., Any | Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class RunCodexThreadOptions:
    config: Any
    auth_manager: Any = None
    models_manager: Any = None
    parent_session: Any = None
    parent_ctx: Any = None
    cancel_token: CancellationToken = field(default_factory=CancellationToken)
    subagent_source: Any = None
    initial_history: Any = None
    spawn_codex: SpawnCodexThread | None = None


async def run_codex_thread_interactive(options: RunCodexThreadOptions) -> CodexDelegateIo:
    """Start an interactive delegated thread using an injected spawn function."""

    if options.spawn_codex is None:
        raise TypeError("spawn_codex is required until the Python Codex runtime is ported")
    codex = options.spawn_codex(
        config=options.config,
        auth_manager=options.auth_manager,
        models_manager=options.models_manager,
        parent_session=options.parent_session,
        parent_ctx=options.parent_ctx,
        subagent_source=options.subagent_source,
        initial_history=options.initial_history,
    )
    if inspect.isawaitable(codex):
        codex = await codex

    events_rx: asyncio.Queue[Event] = asyncio.Queue(maxsize=SUBMISSION_CHANNEL_CAPACITY)
    ops_tx: asyncio.Queue[Any] = asyncio.Queue(maxsize=SUBMISSION_CHANNEL_CAPACITY)
    pending_mcp_invocations: dict[str, Any] = {}
    event_task = asyncio.create_task(
        forward_events(
            codex,
            events_rx,
            options.parent_session,
            options.parent_ctx,
            pending_mcp_invocations,
            options.cancel_token.child_token(),
        )
    )
    ops_task = asyncio.create_task(forward_ops(codex, ops_tx, options.cancel_token.child_token()))
    return CodexDelegateIo(codex=codex, events_rx=events_rx, ops_tx=ops_tx, event_task=event_task, ops_task=ops_task)


async def run_codex_thread_one_shot(
    options: RunCodexThreadOptions,
    input_items: Sequence[Any],
    *,
    final_output_json_schema: Any = None,
) -> CodexDelegateIo:
    """Start a delegate and immediately submit one user-input turn."""

    child_cancel = options.cancel_token.child_token()
    interactive = await run_codex_thread_interactive(
        RunCodexThreadOptions(
            config=options.config,
            auth_manager=options.auth_manager,
            models_manager=options.models_manager,
            parent_session=options.parent_session,
            parent_ctx=options.parent_ctx,
            cancel_token=child_cancel,
            subagent_source=options.subagent_source,
            initial_history=options.initial_history,
            spawn_codex=options.spawn_codex,
        )
    )
    await submit_to_codex(
        interactive.codex,
        Op.user_input(items=input_items, final_output_json_schema=final_output_json_schema),
    )
    return interactive


async def forward_events(
    codex: Any,
    tx_sub: asyncio.Queue[Event],
    parent_session: Any,
    parent_ctx: Any,
    pending_mcp_invocations: MutableMapping[str, Any] | None,
    cancel_token: CancellationToken,
) -> None:
    """Forward child events, handling approval-like events through the parent."""

    pending_mcp_invocations = pending_mcp_invocations if pending_mcp_invocations is not None else {}
    while not cancel_token.is_cancelled():
        try:
            event = await await_with_cancel(_call(codex.next_event), cancel_token)
        except asyncio.CancelledError:
            break
        except Exception:
            break
        if event is None:
            break

        kind = event_kind(event)
        payload = event_payload(event)
        if kind in {"token_count", "session_configured"}:
            continue
        if kind == "exec_approval_request":
            await handle_exec_approval(codex, event.id, parent_session, parent_ctx, payload, cancel_token)
            continue
        if kind == "apply_patch_approval_request":
            await handle_patch_approval(codex, event.id, parent_session, parent_ctx, payload, cancel_token)
            continue
        if kind == "request_permissions":
            await handle_request_permissions(codex, parent_session, parent_ctx, payload, cancel_token)
            continue
        if kind == "request_user_input":
            await handle_request_user_input(
                codex,
                event.id,
                parent_session,
                parent_ctx,
                pending_mcp_invocations,
                payload,
                cancel_token,
            )
            continue
        if kind == "mcp_tool_call_begin":
            call_id = getattr(payload, "call_id", None) or _mapping_get(payload, "call_id")
            invocation = getattr(payload, "invocation", None) or _mapping_get(payload, "invocation")
            if call_id is not None and invocation is not None:
                pending_mcp_invocations[str(call_id)] = invocation
        elif kind == "mcp_tool_call_end":
            call_id = getattr(payload, "call_id", None) or _mapping_get(payload, "call_id")
            if call_id is not None:
                pending_mcp_invocations.pop(str(call_id), None)

        if not await forward_event_or_shutdown(codex, tx_sub, cancel_token, event):
            break


async def forward_ops(codex: Any, rx_ops: asyncio.Queue[Any], cancel_token: CancellationToken) -> None:
    """Forward caller submissions to the child Codex object."""

    while not cancel_token.is_cancelled():
        try:
            submission = await await_with_cancel(rx_ops.get(), cancel_token)
        except asyncio.CancelledError:
            break
        if submission is None:
            break
        submit_with_id = getattr(codex, "submit_with_id", None)
        if callable(submit_with_id):
            await _maybe_await(submit_with_id(submission))
        else:
            await submit_to_codex(codex, submission)


async def shutdown_delegate(codex: Any) -> None:
    """Ask the delegate to interrupt and then shut down."""

    await submit_to_codex(codex, Op("interrupt", {}))
    await submit_to_codex(codex, Op("shutdown", {}))


async def forward_event_or_shutdown(
    codex: Any,
    tx_sub: asyncio.Queue[Event],
    cancel_token: CancellationToken,
    event: Event,
) -> bool:
    try:
        await await_with_cancel(tx_sub.put(event), cancel_token)
        return True
    except asyncio.CancelledError:
        await shutdown_delegate(codex)
        return False


async def handle_exec_approval(
    codex: Any,
    turn_id: str,
    parent_session: Any,
    parent_ctx: Any,
    event: Any,
    cancel_token: CancellationToken,
) -> ReviewDecision:
    approval_id = _effective_approval_id(event)
    call_id = getattr(event, "call_id", _mapping_get(event, "call_id"))
    raw_approval_id = getattr(event, "approval_id", _mapping_get(event, "approval_id"))
    command = getattr(event, "command", _mapping_get(event, "command"))
    cwd = getattr(event, "cwd", _mapping_get(event, "cwd"))
    reason = getattr(event, "reason", _mapping_get(event, "reason"))
    additional_permissions = getattr(event, "additional_permissions", _mapping_get(event, "additional_permissions"))
    if routes_approval_to_guardian(parent_ctx):
        reviewer = getattr(parent_session, "review_command_approval", None)
        if callable(reviewer):
            review_cancel = cancel_token.child_token()
            decision = await await_approval_with_cancel(
                reviewer(
                    parent_ctx,
                    GuardianShellApprovalRequest(
                        id=str(call_id),
                        command=command,
                        cwd=cwd,
                        sandbox_permissions=(
                            SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS
                            if additional_permissions is not None
                            else SANDBOX_PERMISSIONS_USE_DEFAULT
                        ),
                        additional_permissions=additional_permissions,
                        justification=None,
                    ),
                    reason,
                    GUARDIAN_APPROVAL_REQUEST_SOURCE_DELEGATED_SUBAGENT,
                    review_cancel,
                ),
                parent_session,
                approval_id,
                cancel_token,
                review_cancel,
            )
            await submit_to_codex(codex, Op.exec_approval(id=approval_id, turn_id=turn_id, decision=decision))
            return decision

    requester = getattr(parent_session, "request_command_approval", None)
    decision = ReviewDecision.denied()
    if callable(requester):
        decision = await await_approval_with_cancel(
            requester(
                parent_ctx,
                call_id,
                raw_approval_id,
                command,
                cwd,
                reason,
                getattr(event, "network_approval_context", _mapping_get(event, "network_approval_context")),
                getattr(event, "proposed_execpolicy_amendment", _mapping_get(event, "proposed_execpolicy_amendment")),
                additional_permissions,
                getattr(event, "available_decisions", _mapping_get(event, "available_decisions")),
            ),
            parent_session,
            approval_id,
            cancel_token,
        )
    await submit_to_codex(codex, Op.exec_approval(id=approval_id, turn_id=turn_id, decision=decision))
    return decision


async def handle_patch_approval(
    codex: Any,
    _id: str,
    parent_session: Any,
    parent_ctx: Any,
    event: Any,
    cancel_token: CancellationToken,
) -> ReviewDecision:
    call_id = str(getattr(event, "call_id", _mapping_get(event, "call_id")))
    changes = getattr(event, "changes", _mapping_get(event, "changes"))
    reason = getattr(event, "reason", _mapping_get(event, "reason"))
    grant_root = getattr(event, "grant_root", _mapping_get(event, "grant_root"))
    if routes_approval_to_guardian(parent_ctx):
        reviewer = getattr(parent_session, "review_patch_approval", None)
        if callable(reviewer):
            review_cancel = cancel_token.child_token()
            decision = await await_approval_with_cancel(
                reviewer(
                    parent_ctx,
                    GuardianApplyPatchApprovalRequest(
                        id=call_id,
                        cwd=getattr(parent_ctx, "cwd", _mapping_get(parent_ctx, "cwd")),
                        files=apply_patch_files_for_guardian(getattr(parent_ctx, "cwd", _mapping_get(parent_ctx, "cwd")), changes),
                        patch=format_apply_patch_changes_for_guardian(changes),
                    ),
                    reason,
                    GUARDIAN_APPROVAL_REQUEST_SOURCE_DELEGATED_SUBAGENT,
                    review_cancel,
                ),
                parent_session,
                call_id,
                cancel_token,
                review_cancel,
            )
            await submit_to_codex(codex, Op.patch_approval(id=call_id, decision=decision))
            return decision

    requester = getattr(parent_session, "request_patch_approval", None)
    decision = ReviewDecision.denied()
    if callable(requester):
        decision_rx = requester(
            parent_ctx,
            call_id,
            changes,
            reason,
            grant_root,
        )
        decision = await await_approval_with_cancel(decision_rx, parent_session, call_id, cancel_token)
    await submit_to_codex(codex, Op.patch_approval(id=call_id, decision=decision))
    return decision


async def handle_request_user_input(
    codex: Any,
    id: str,
    parent_session: Any,
    parent_ctx: Any,
    pending_mcp_invocations: Mapping[str, Any],
    event: Any,
    cancel_token: CancellationToken,
) -> RequestUserInputResponse:
    response = await maybe_auto_review_mcp_request_user_input(
        parent_session,
        parent_ctx,
        pending_mcp_invocations,
        event,
        cancel_token,
    )
    if response is None:
        requester = getattr(parent_session, "request_user_input", None)
        if callable(requester):
            sub_id = getattr(parent_ctx, "sub_id", "")
            questions = tuple(getattr(event, "questions", _mapping_get(event, "questions", ())))
            response = await await_user_input_with_cancel(
                requester(parent_ctx, sub_id, RequestUserInputArgs(questions=questions)),
                parent_session,
                str(sub_id),
                cancel_token,
            )
        else:
            response = RequestUserInputResponse({})
    await submit_to_codex(codex, Op.user_input_answer(id=id, response=response))
    return response


async def maybe_auto_review_mcp_request_user_input(
    parent_session: Any,
    parent_ctx: Any,
    pending_mcp_invocations: Mapping[str, Any],
    event: Any,
    cancel_token: CancellationToken,
) -> RequestUserInputResponse | None:
    """Programmatically answer delegated MCP approval prompts when possible."""

    if not routes_approval_to_guardian(parent_ctx):
        return None

    questions = tuple(getattr(event, "questions", _mapping_get(event, "questions", ())))
    question = next((item for item in questions if is_mcp_tool_approval_question_id(getattr(item, "id", ""))), None)
    if question is None:
        return None
    call_id = str(getattr(event, "call_id", _mapping_get(event, "call_id", "")))
    if call_id not in pending_mcp_invocations:
        return None

    reviewer = getattr(parent_session, "review_mcp_tool_invocation", None)
    decision = ReviewDecision.denied()
    if callable(reviewer):
        decision = await await_approval_with_cancel(
            reviewer(parent_ctx, call_id, pending_mcp_invocations[call_id]),
            parent_session,
            call_id,
            cancel_token,
        )

    selected_label = mcp_selected_label_for_decision(decision, getattr(question, "options", None))
    return RequestUserInputResponse({question.id: RequestUserInputAnswer((selected_label,))})


async def handle_request_permissions(
    codex: Any,
    parent_session: Any,
    parent_ctx: Any,
    event: Any,
    cancel_token: CancellationToken,
) -> RequestPermissionsResponse:
    call_id = str(getattr(event, "call_id", _mapping_get(event, "call_id")))
    requester = getattr(parent_session, "request_permissions_for_cwd", None)
    response = RequestPermissionsResponse(RequestPermissionProfile(), PermissionGrantScope.TURN, False)
    if callable(requester):
        args = RequestPermissionsArgs(
            reason=getattr(event, "reason", _mapping_get(event, "reason")),
            permissions=getattr(event, "permissions", _mapping_get(event, "permissions")),
        )
        cwd = getattr(event, "cwd", _mapping_get(event, "cwd", None)) or getattr(parent_ctx, "cwd", None)
        response = await await_request_permissions_with_cancel(
            requester(parent_ctx, call_id, args, cwd, cancel_token),
            parent_session,
            call_id,
            cancel_token,
        )
        response = normalize_request_permissions_response(
            args.permissions,
            response,
            cwd,
        )
    await submit_to_codex(codex, Op.request_permissions_response(id=call_id, response=response))
    return response


async def await_user_input_with_cancel(
    fut: Any,
    parent_session: Any,
    sub_id: str,
    cancel_token: CancellationToken,
) -> RequestUserInputResponse:
    empty = RequestUserInputResponse({})

    async def on_cancel() -> RequestUserInputResponse:
        notifier = getattr(parent_session, "notify_user_input_response", None)
        if callable(notifier):
            await _maybe_await(notifier(sub_id, empty))
        return empty

    response = await _await_or_cancel(fut, cancel_token, on_cancel)
    return response if isinstance(response, RequestUserInputResponse) else empty


async def await_request_permissions_with_cancel(
    fut: Any,
    parent_session: Any,
    call_id: str,
    cancel_token: CancellationToken,
) -> RequestPermissionsResponse:
    empty = RequestPermissionsResponse(RequestPermissionProfile(), PermissionGrantScope.TURN, False)

    async def on_cancel() -> RequestPermissionsResponse:
        notifier = getattr(parent_session, "notify_request_permissions_response", None)
        if callable(notifier):
            await _maybe_await(notifier(call_id, empty))
        return empty

    response = await _await_or_cancel(fut, cancel_token, on_cancel)
    return response if isinstance(response, RequestPermissionsResponse) else empty


async def await_approval_with_cancel(
    fut: Any,
    parent_session: Any,
    approval_id: str,
    cancel_token: CancellationToken,
    review_cancel_token: CancellationToken | None = None,
) -> ReviewDecision:
    async def on_cancel() -> ReviewDecision:
        if review_cancel_token is not None:
            review_cancel_token.cancel()
        notifier = getattr(parent_session, "notify_approval", None)
        if callable(notifier):
            await _maybe_await(notifier(approval_id, ReviewDecision.abort()))
        return ReviewDecision.abort()

    decision = await _await_or_cancel(fut, cancel_token, on_cancel)
    if decision is None:
        return ReviewDecision.denied()
    return ReviewDecision.from_mapping(decision)


def event_kind(event: Event | Any) -> str:
    msg = getattr(event, "msg", None)
    if isinstance(msg, EventMsg):
        return msg.type
    kind = getattr(msg, "type", None) or getattr(msg, "kind", None)
    if callable(kind):
        kind = kind()
    if kind is None and isinstance(msg, Mapping):
        kind = msg.get("type")
    return str(kind or "")


def event_payload(event: Event | Any) -> Any:
    msg = getattr(event, "msg", None)
    if isinstance(msg, EventMsg):
        return msg.payload
    return getattr(msg, "payload", msg)


def mcp_selected_label_for_decision(decision: ReviewDecision, options: Sequence[Any] | None = None) -> str:
    if decision.type == "approved_for_session":
        labels = tuple(str(getattr(option, "label", option)) for option in (options or ()))
        if MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION in labels:
            return MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION
        return MCP_TOOL_APPROVAL_ACCEPT
    if decision.type in {"approved", "approved_execpolicy_amendment", "network_policy_amendment"}:
        return MCP_TOOL_APPROVAL_ACCEPT
    return MCP_TOOL_APPROVAL_DECLINE_SYNTHETIC


async def submit_to_codex(codex: Any, op: Op | Any) -> None:
    submit = getattr(codex, "submit", None)
    if not callable(submit):
        raise TypeError("codex object must provide submit")
    await _maybe_await(submit(op))


async def await_with_cancel(awaitable: Any, cancel_token: CancellationToken) -> Any:
    return await _await_or_cancel(awaitable, cancel_token, _raise_cancelled)


async def _await_or_cancel(awaitable: Any, cancel_token: CancellationToken, on_cancel: Callable[[], Any]) -> Any:
    task = asyncio.ensure_future(_maybe_await(awaitable))
    cancel_task = asyncio.create_task(cancel_token.cancelled())
    done, pending = await asyncio.wait((task, cancel_task), return_when=asyncio.FIRST_COMPLETED)
    for pending_task in pending:
        pending_task.cancel()
    if cancel_task in done and task not in done:
        task.cancel()
        return await _maybe_await(on_cancel())
    return task.result()


async def _raise_cancelled() -> None:
    raise asyncio.CancelledError


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return await _maybe_await(fn(*args, **kwargs))


def _effective_approval_id(event: Any) -> str:
    method = getattr(event, "effective_approval_id", None)
    if callable(method):
        return str(method())
    approval_id = getattr(event, "approval_id", _mapping_get(event, "approval_id"))
    call_id = getattr(event, "call_id", _mapping_get(event, "call_id"))
    return str(approval_id or call_id)


def _mapping_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return default


__all__ = [
    "MCP_TOOL_APPROVAL_ACCEPT",
    "MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION",
    "MCP_TOOL_APPROVAL_DECLINE_SYNTHETIC",
    "MCP_TOOL_APPROVAL_QUESTION_ID_PREFIX",
    "SUBMISSION_CHANNEL_CAPACITY",
    "CancellationToken",
    "CodexDelegateIo",
    "GUARDIAN_APPROVAL_REQUEST_SOURCE_DELEGATED_SUBAGENT",
    "GuardianShellApprovalRequest",
    "RunCodexThreadOptions",
    "SANDBOX_PERMISSIONS_USE_DEFAULT",
    "SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS",
    "await_approval_with_cancel",
    "await_request_permissions_with_cancel",
    "await_user_input_with_cancel",
    "event_kind",
    "event_payload",
    "forward_event_or_shutdown",
    "forward_events",
    "forward_ops",
    "handle_exec_approval",
    "handle_patch_approval",
    "handle_request_permissions",
    "handle_request_user_input",
    "is_mcp_tool_approval_question_id",
    "mcp_selected_label_for_decision",
    "maybe_auto_review_mcp_request_user_input",
    "routes_approval_to_guardian",
    "run_codex_thread_interactive",
    "run_codex_thread_one_shot",
    "shutdown_delegate",
    "submit_to_codex",
]

