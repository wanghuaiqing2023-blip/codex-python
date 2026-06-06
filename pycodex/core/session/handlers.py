"""Session operation handlers aligned with ``codex-rs/core/src/session/handlers.rs``."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.protocol import (
    CodexErrorInfo,
    ConversationAudioParams,
    ConversationStartParams,
    ConversationTextParams,
    ElicitationAction,
    ErrorEvent,
    Event,
    EventMsg,
    ContentItem,
    GuardianAssessmentEvent,
    GuardianAssessmentStatus,
    InterAgentCommunication,
    Op,
    RealtimeConversationListVoicesResponseEvent,
    RealtimeVoicesList,
    ResponseInputItem,
    ResponseItem,
    ReviewDecision,
    ReviewRequest,
    RequestId,
    ThreadMemoryMode,
    ThreadSettingsOverrides,
    ThreadRolledBackEvent,
    WarningEvent,
)
from pycodex.rollout import (
    append_event_msg_to_rollout,
    read_rollout_reconstruction_from_rollout,
)


USER_SHELL_COMMAND_MODE_ACTIVE_TURN_AUXILIARY = "active_turn_auxiliary"
AUTO_REVIEW_DENIED_ACTION_APPROVAL_DEVELOPER_PREFIX = (
    "The user has manually approved a specific action that was previously `Rejected`."
)


@dataclass(frozen=True)
class UserShellCommandTask:
    command: str


@dataclass(frozen=True)
class CompactTask:
    pass


@dataclass(frozen=True)
class RegularTask:
    pass


@dataclass(frozen=True)
class ResponseItemTurnInput:
    item: Any


@dataclass(frozen=True)
class UserInputTurnInput:
    items: tuple[Any, ...]


class NoActiveTurnForUserInput(Exception):
    """Python boundary equivalent of Rust ``SteerInputError::NoActiveTurn``."""

    def __init__(self, items: Any) -> None:
        super().__init__("no active turn")
        self.items = tuple(items)


async def interrupt(sess: Any) -> None:
    """Interrupt the active session task.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``interrupt``
    """

    await _maybe_await(getattr(sess, "interrupt_task")())


async def clean_background_terminals(sess: Any) -> None:
    """Close background unified exec processes.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``clean_background_terminals``
    """

    await _maybe_await(getattr(sess, "close_unified_exec_processes")())


async def realtime_conversation_list_voices(sess: Any, sub_id: str) -> None:
    """Emit the built-in realtime voice list.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``realtime_conversation_list_voices``
    """

    await _emit_raw_event(
        sess,
        Event(
            id=sub_id,
            msg=EventMsg.with_payload(
                "realtime_conversation_list_voices_response",
                RealtimeConversationListVoicesResponseEvent(
                    voices=RealtimeVoicesList.builtin(),
                ),
            ),
        ),
    )


async def realtime_conversation_start(sess: Any, sub_id: str, params: ConversationStartParams) -> None:
    """Delegate realtime conversation startup and emit Rust-shaped errors."""

    try:
        await _maybe_await(getattr(sess, "handle_realtime_conversation_start")(sub_id, params))
    except Exception as exc:  # noqa: BLE001 - mirror Rust submission-loop error event conversion.
        await _emit_raw_event(
            sess,
            Event(
                id=sub_id,
                msg=EventMsg.with_payload(
                    "error",
                    ErrorEvent(message=str(exc), codex_error_info=CodexErrorInfo.other()),
                ),
            ),
        )


async def realtime_conversation_audio(sess: Any, sub_id: str, params: ConversationAudioParams) -> None:
    """Delegate realtime audio input handling."""

    await _maybe_await(getattr(sess, "handle_realtime_conversation_audio")(sub_id, params))


async def realtime_conversation_text(sess: Any, sub_id: str, params: ConversationTextParams) -> None:
    """Delegate realtime text input handling."""

    await _maybe_await(getattr(sess, "handle_realtime_conversation_text")(sub_id, params))


async def realtime_conversation_close(sess: Any, sub_id: str) -> None:
    """Delegate realtime conversation close handling."""

    await _maybe_await(getattr(sess, "handle_realtime_conversation_close")(sub_id))


async def approve_guardian_denied_action(sess: Any, event: GuardianAssessmentEvent) -> None:
    """Inject approval for an exact Guardian-denied action.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``approve_guardian_denied_action``
    """

    if event.status != GuardianAssessmentStatus.DENIED:
        return

    approved_action_json = json.dumps(
        {
            "action": _guardian_action_mapping(event.action),
            "outcome": "allowed",
        },
        indent=2,
    )
    text = (
        f"{AUTO_REVIEW_DENIED_ACTION_APPROVAL_DEVELOPER_PREFIX}\n\n"
        "Treat this as approval to perform that exact action in the same context in which it was originally requested.\n"
        "Do not assume this also authorizes similar operations with different payloads.\n\n"
        "Approved action:\n"
        f"{approved_action_json}"
    )
    items = [
        ResponseItem.from_response_input_item(
            ResponseInputItem.message(
                "developer",
                (ContentItem.input_text(text),),
            )
        )
    ]
    await _maybe_await(getattr(sess, "inject_no_new_turn")(items, None))


async def inter_agent_communication(sess: Any, sub_id: str, communication: InterAgentCommunication) -> None:
    """Record inter-agent mail and optionally start pending work.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``inter_agent_communication``
    """

    trigger_turn = bool(communication.trigger_turn)
    input_queue = getattr(sess, "input_queue", None)
    enqueue = getattr(input_queue, "enqueue_mailbox_communication", None)
    if callable(enqueue):
        await _maybe_await(enqueue(communication))
    else:
        enqueue = getattr(sess, "enqueue_mailbox_communication")
        await _maybe_await(enqueue(communication))
    if trigger_turn:
        starter = getattr(sess, "maybe_start_turn_for_pending_work_with_sub_id")
        await _maybe_await(starter(sub_id))


async def reload_user_config(sess: Any) -> None:
    """Reload the user config layer for the active session.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``reload_user_config``
    """

    await _maybe_await(getattr(sess, "reload_user_config_layer")())


async def update_thread_settings(sess: Any, sub_id: str, thread_settings: ThreadSettingsOverrides) -> None:
    """Apply thread setting overrides and emit the resulting protocol event.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``update_thread_settings``
    """

    updates = await thread_settings_update(sess, thread_settings)
    try:
        await _maybe_await(getattr(sess, "update_settings")(updates))
    except Exception as exc:  # noqa: BLE001 - mirror Rust bad-request event conversion.
        msg = EventMsg.with_payload(
            "error",
            ErrorEvent(
                message=f"invalid thread settings override: {exc}",
                codex_error_info=CodexErrorInfo.bad_request(),
            ),
        )
    else:
        msg = await thread_settings_applied_event(sess)
    await _emit_raw_event(sess, Event(id=sub_id, msg=msg))


async def persist_thread_memory_mode_update(sess: Any, mode: ThreadMemoryMode) -> None:
    """Persist thread-level memory mode metadata for the active session."""

    updater = getattr(sess, "persist_thread_memory_mode_update", None)
    if callable(updater):
        await _maybe_await(updater(mode))
        return

    live_thread_getter = getattr(sess, "live_thread_for_persistence")
    live_thread = await _maybe_await(live_thread_getter("update thread memory mode"))
    await _maybe_await(getattr(live_thread, "persist")())
    await _maybe_await(getattr(live_thread, "flush")())
    await _maybe_await(getattr(live_thread, "update_memory_mode")(mode, False))
    await _maybe_await(getattr(live_thread, "flush")())


async def set_thread_memory_mode(sess: Any, sub_id: str, mode: ThreadMemoryMode) -> None:
    """Persist thread-level memory mode metadata.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``set_thread_memory_mode``
    """

    try:
        await persist_thread_memory_mode_update(sess, mode)
    except Exception as exc:  # noqa: BLE001 - mirror Rust error-event-and-continue branch.
        await _emit_raw_event(
            sess,
            Event(
                id=sub_id,
                msg=EventMsg.with_payload(
                    "error",
                    ErrorEvent(
                        message=str(exc),
                        codex_error_info=CodexErrorInfo.other(),
                    ),
                ),
            ),
        )


async def user_input_or_turn(sess: Any, sub_id: str, op: Op) -> None:
    """Handle a user input op by steering an active turn or spawning a regular task."""

    await user_input_or_turn_inner(sess, sub_id, op, mirror_user_text_to_realtime=True)


async def user_input_or_turn_inner(
    sess: Any,
    sub_id: str,
    op: Op,
    *,
    mirror_user_text_to_realtime: bool = True,
) -> None:
    """Session handler boundary for Rust ``user_input_or_turn_inner``."""

    fields = op.fields or {}
    items = tuple(fields.get("items", ()))
    environments = fields.get("environments")
    final_output_json_schema = fields.get("final_output_json_schema")
    responsesapi_client_metadata = fields.get("responsesapi_client_metadata")
    additional_context = fields.get("additional_context")
    thread_settings = _thread_settings_overrides(
        fields.get("thread_settings", ThreadSettingsOverrides.default())
    )

    emit_thread_settings_applied = thread_settings != ThreadSettingsOverrides.default()
    updates = await thread_settings_update(sess, thread_settings) if emit_thread_settings_applied else {}
    updates["final_output_json_schema"] = final_output_json_schema
    updates["environments"] = environments

    try:
        current_context = await _maybe_await(getattr(sess, "new_turn_with_sub_id")(sub_id, updates))
    except Exception:  # noqa: BLE001 - Rust relies on new_turn_with_sub_id to emit its own error event.
        return
    if current_context is None:
        return

    if emit_thread_settings_applied:
        await _emit_raw_event(sess, Event(id=sub_id, msg=await thread_settings_applied_event(sess)))

    unknown_model_warning = getattr(sess, "maybe_emit_unknown_model_warning_for_turn", None)
    if callable(unknown_model_warning):
        await _maybe_await(unknown_model_warning(current_context))

    accepted_items: tuple[Any, ...] | None
    try:
        await _maybe_await(
            getattr(sess, "steer_input")(
                items,
                additional_context,
                None,
                responsesapi_client_metadata,
            )
        )
    except Exception as exc:  # noqa: BLE001 - map only the local handler boundary.
        no_active_items = _no_active_turn_items(exc)
        if no_active_items is None:
            await _emit_raw_event(sess, Event(id=sub_id, msg=EventMsg.with_payload("error", _steer_input_error_event(exc))))
            accepted_items = None
        else:
            accepted_items = tuple(no_active_items)
            await _record_responsesapi_client_metadata(current_context, responsesapi_client_metadata)
            await _record_user_prompt_telemetry(current_context, accepted_items)
            await _refresh_mcp_servers_if_requested(sess, current_context)
            task_input = [ResponseItemTurnInput(item) for item in await _merge_additional_context(sess, additional_context)]
            if accepted_items:
                task_input.append(UserInputTurnInput(accepted_items))
            await _maybe_await(getattr(sess, "spawn_task")(current_context, task_input, RegularTask()))
    else:
        accepted_items = items
        await _record_user_prompt_telemetry(current_context, items)

    if accepted_items is not None and mirror_user_text_to_realtime:
        await _mirror_user_text_to_realtime(sess, accepted_items)


async def thread_settings_update(sess: Any, thread_settings: ThreadSettingsOverrides) -> dict[str, Any]:
    """Build a session settings update from thread setting overrides."""

    builder = getattr(sess, "thread_settings_update", None)
    if callable(builder):
        return await _maybe_await(builder(thread_settings))

    collaboration_mode = thread_settings.collaboration_mode
    if collaboration_mode is None:
        current_mode = await _current_collaboration_mode(sess)
        with_updates = getattr(current_mode, "with_updates", None)
        if callable(with_updates):
            collaboration_mode = await _maybe_await(with_updates(thread_settings.model, thread_settings.effort, None))
        else:
            collaboration_mode = current_mode

    return {
        "cwd": thread_settings.cwd,
        "workspace_roots": thread_settings.workspace_roots,
        "profile_workspace_roots": thread_settings.profile_workspace_roots,
        "approval_policy": thread_settings.approval_policy,
        "approvals_reviewer": thread_settings.approvals_reviewer,
        "sandbox_policy": thread_settings.sandbox_policy,
        "permission_profile": thread_settings.permission_profile,
        "active_permission_profile": thread_settings.active_permission_profile,
        "windows_sandbox_level": thread_settings.windows_sandbox_level,
        "collaboration_mode": collaboration_mode,
        "reasoning_summary": thread_settings.summary,
        "service_tier": thread_settings.service_tier,
        "personality": thread_settings.personality,
    }


async def thread_settings_applied_event(sess: Any) -> EventMsg:
    """Build a ``thread_settings_applied`` event from the current session snapshot."""

    event_builder = getattr(sess, "thread_settings_applied_event", None)
    if callable(event_builder):
        event = await _maybe_await(event_builder())
        if isinstance(event, EventMsg):
            return event
        return EventMsg.with_payload("thread_settings_applied", event)

    snapshot_getter = getattr(sess, "thread_config_snapshot", None)
    snapshot = await _maybe_await(snapshot_getter()) if callable(snapshot_getter) else getattr(sess, "thread_settings_snapshot", None)
    if snapshot is None:
        snapshot = {}
    return EventMsg.with_payload("thread_settings_applied", {"thread_settings": snapshot})


async def shutdown_session_runtime(sess: Any) -> None:
    """Shut down session-owned runtime resources.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``shutdown_session_runtime``
    """

    abort_all_tasks = getattr(sess, "abort_all_tasks", None)
    if callable(abort_all_tasks):
        await _maybe_await(abort_all_tasks("interrupted"))

    conversation = getattr(sess, "conversation", None)
    conversation_shutdown = getattr(conversation, "shutdown", None)
    if callable(conversation_shutdown):
        try:
            await _maybe_await(conversation_shutdown())
        except Exception:  # noqa: BLE001 - Rust ignores this shutdown result.
            pass

    services = getattr(sess, "services", None)
    unified_exec_manager = getattr(services, "unified_exec_manager", None)
    terminate_processes = getattr(unified_exec_manager, "terminate_all_processes", None)
    if callable(terminate_processes):
        await _maybe_await(terminate_processes())

    mcp_connection_manager = getattr(services, "mcp_connection_manager", None)
    mcp_manager = mcp_connection_manager
    write_lock = getattr(mcp_connection_manager, "write", None)
    if callable(write_lock):
        mcp_manager = await _maybe_await(write_lock())
    begin_shutdown = getattr(mcp_manager, "begin_shutdown", None)
    if callable(begin_shutdown):
        shutdown_waiter = await _maybe_await(begin_shutdown())
        await _maybe_await(shutdown_waiter)

    guardian_review_session = getattr(sess, "guardian_review_session", None)
    guardian_shutdown = getattr(guardian_review_session, "shutdown", None)
    if callable(guardian_shutdown):
        await _maybe_await(guardian_shutdown())


async def emit_thread_stop_lifecycle(sess: Any) -> None:
    """Emit extension thread-stop lifecycle callbacks when available."""

    explicit_emitter = getattr(sess, "emit_thread_stop_lifecycle", None)
    if callable(explicit_emitter):
        await _maybe_await(explicit_emitter())
        return

    services = getattr(sess, "services", None)
    extensions = getattr(services, "extensions", None)
    contributors_getter = getattr(extensions, "thread_lifecycle_contributors", None)
    if not callable(contributors_getter):
        return
    contributors = await _maybe_await(contributors_getter())
    session_store = getattr(services, "session_extension_data", None)
    thread_store = getattr(services, "thread_extension_data", None)
    thread_stop_input = {"session_store": session_store, "thread_store": thread_store}
    for contributor in contributors:
        on_thread_stop = getattr(contributor, "on_thread_stop", None)
        if callable(on_thread_stop):
            await _maybe_await(on_thread_stop(thread_stop_input))


async def shutdown(sess: Any, sub_id: str) -> bool:
    """Shut down the session and signal the submission loop to exit.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``shutdown``
    """

    await shutdown_session_runtime(sess)
    await _record_shutdown_turn_count(sess)
    await emit_thread_stop_lifecycle(sess)
    await _shutdown_live_thread(sess, sub_id)

    event = Event(id=sub_id, msg=EventMsg.with_payload("shutdown_complete"))
    await _record_rollout_protocol_event(sess, event.msg)
    await _emit_raw_event(sess, event, prefer_deliver=True)
    await _record_rollout_ended(sess)
    return True


async def thread_rollback(sess: Any, sub_id: str, num_turns: int) -> None:
    """Roll a persisted thread history back by ``num_turns`` user turns.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``thread_rollback``
    - tests: ``thread_rollback_*`` in ``core/src/session/tests.rs``
    """

    if num_turns == 0:
        await _send_thread_rollback_error(sess, sub_id, "num_turns must be >= 1")
        return

    if _has_active_turn(sess):
        await _send_thread_rollback_error(sess, sub_id, "Cannot rollback while a turn is in progress.")
        return

    rollout_path = _session_rollout_path(sess)
    if rollout_path is None:
        await _send_thread_rollback_error(
            sess,
            sub_id,
            "thread rollback requires persisted thread history",
        )
        return
    if not rollout_path.exists():
        await _send_thread_rollback_error(
            sess,
            sub_id,
            f"failed to load thread history for rollback replay: {rollout_path}",
        )
        return

    rollback_msg = EventMsg.with_payload(
        "thread_rolled_back",
        ThreadRolledBackEvent(num_turns=num_turns),
    )
    try:
        reconstruction = _read_reconstruction_with_rollback_marker(rollout_path, rollback_msg)
    except OSError as exc:
        await _send_thread_rollback_error(
            sess,
            sub_id,
            f"failed to load thread history for rollback replay: {exc}",
        )
        return

    replace_history = getattr(sess, "replace_history", None)
    if callable(replace_history):
        await _maybe_await(replace_history(reconstruction.history, reconstruction.reference_context_item))

    set_previous_turn_settings = getattr(sess, "set_previous_turn_settings", None)
    if callable(set_previous_turn_settings):
        await _maybe_await(set_previous_turn_settings(reconstruction.previous_turn_settings))

    recompute_token_usage = getattr(sess, "recompute_token_usage", None)
    if callable(recompute_token_usage):
        await _maybe_await(recompute_token_usage())

    try:
        persist_rollout_items = getattr(sess, "persist_rollout_items", None)
        if callable(persist_rollout_items):
            await _maybe_await(persist_rollout_items([rollback_msg]))
        else:
            append_event_msg_to_rollout(rollout_path, rollback_msg)
        flush_rollout = getattr(sess, "flush_rollout", None)
        if callable(flush_rollout):
            await _maybe_await(flush_rollout())
    except (OSError, ValueError) as exc:
        await _emit_raw_event(
            sess,
            Event(
                id=sub_id,
                msg=EventMsg.with_payload(
                    "warning",
                    WarningEvent(
                        "Rolled the thread back, but failed to save the rollback marker. "
                        f"Codex will continue retrying. Error: {exc}"
                    ),
                ),
            ),
        )

    await _emit_raw_event(sess, Event(id=sub_id, msg=rollback_msg), prefer_deliver=True)


async def request_permissions_response(sess: Any, id: str, response: Any) -> None:
    """Propagate a permission response to the active session request.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``request_permissions_response``
    """

    notify = getattr(sess, "notify_request_permissions_response")
    await _maybe_await(notify(id, response))


async def patch_approval(sess: Any, id: str, decision: ReviewDecision) -> None:
    """Propagate an apply-patch approval decision.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``patch_approval``
    """

    if decision == ReviewDecision.abort():
        interrupt_task = getattr(sess, "interrupt_task")
        await _maybe_await(interrupt_task())
        return
    notify = getattr(sess, "notify_approval")
    await _maybe_await(notify(id, decision))


async def exec_approval(sess: Any, approval_id: str, turn_id: str | None, decision: ReviewDecision) -> None:
    """Propagate an exec approval decision and optional execpolicy amendment.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``exec_approval``
    """

    event_turn_id = turn_id or approval_id
    amendment = getattr(decision, "proposed_execpolicy_amendment", None)
    if getattr(decision, "type", None) == "approved_execpolicy_amendment" and amendment is not None:
        persist = getattr(sess, "persist_execpolicy_amendment", None)
        persisted = True
        if callable(persist):
            try:
                await _maybe_await(persist(amendment))
            except Exception as exc:  # noqa: BLE001 - mirror Rust warning-and-continue path.
                persisted = False
                await _emit_raw_event(
                    sess,
                    Event(
                        id=event_turn_id,
                        msg=EventMsg.with_payload(
                            "warning",
                            WarningEvent(f"Failed to apply execpolicy amendment: {exc}"),
                        ),
                    ),
                )
        if persisted:
            recorder = getattr(sess, "record_execpolicy_amendment_message", None)
            if callable(recorder):
                await _maybe_await(recorder(event_turn_id, amendment))

    if decision == ReviewDecision.abort():
        interrupt_task = getattr(sess, "interrupt_task")
        await _maybe_await(interrupt_task())
        return
    notify = getattr(sess, "notify_approval")
    await _maybe_await(notify(approval_id, decision))


async def request_user_input_response(sess: Any, id: str, response: Any) -> None:
    """Propagate a user-input response to the session.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``request_user_input_response``
    """

    notify = getattr(sess, "notify_user_input_response")
    await _maybe_await(notify(id, response))


async def dynamic_tool_response(sess: Any, id: str, response: Any) -> None:
    """Propagate a dynamic-tool response to the session.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``dynamic_tool_response``
    """

    notify = getattr(sess, "notify_dynamic_tool_response")
    await _maybe_await(notify(id, response))


async def refresh_mcp_servers(sess: Any, refresh_config: Any) -> None:
    """Record a pending MCP server refresh config for the next turn.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``refresh_mcp_servers``
    """

    setter = getattr(sess, "set_pending_mcp_server_refresh_config", None)
    if callable(setter):
        await _maybe_await(setter(refresh_config))
        return

    pending = getattr(sess, "pending_mcp_server_refresh_config", None)
    set_value = getattr(pending, "set", None)
    if callable(set_value):
        await _maybe_await(set_value(refresh_config))
        return
    if pending is not None and hasattr(pending, "value"):
        setattr(pending, "value", refresh_config)
        return

    setattr(sess, "pending_mcp_server_refresh_config", refresh_config)


async def resolve_elicitation(
    sess: Any,
    server_name: str,
    request_id: RequestId | str | int,
    decision: ElicitationAction | str,
    content: Any | None,
    meta: Any | None,
) -> None:
    """Resolve a pending MCP elicitation request.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``resolve_elicitation``
    """

    from pycodex.core.mcp_tool_call import ElicitationResponse

    action = decision if isinstance(decision, ElicitationAction) else ElicitationAction(str(decision))
    response_content = content if action == ElicitationAction.ACCEPT else None
    if action == ElicitationAction.ACCEPT and response_content is None:
        response_content = {}
    protocol_request_id = RequestId.from_value(request_id)
    response = ElicitationResponse(action=action, content=response_content, meta=meta)
    try:
        await _maybe_await(getattr(sess, "resolve_elicitation")(server_name, protocol_request_id.value, response))
    except Exception:  # noqa: BLE001 - mirror Rust warn-and-continue behavior.
        return


async def review(sess: Any, config: Any, sub_id: str, review_request: ReviewRequest) -> None:
    """Start a review turn for a resolved review request.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``review``
    """

    from pycodex.core.review_prompts import resolve_review_request

    turn_context = await _maybe_await(getattr(sess, "new_default_turn_with_sub_id")(sub_id))

    unknown_model_warning = getattr(sess, "maybe_emit_unknown_model_warning_for_turn", None)
    if callable(unknown_model_warning):
        await _maybe_await(unknown_model_warning(turn_context))

    await _refresh_mcp_servers_if_requested(sess, turn_context)

    try:
        resolved = resolve_review_request(review_request, getattr(turn_context, "cwd"))
    except Exception as exc:  # noqa: BLE001 - mirror Rust error-event branch.
        await _emit_session_event(
            sess,
            turn_context,
            EventMsg.with_payload(
                "error",
                ErrorEvent(
                    message=str(exc),
                    codex_error_info=CodexErrorInfo.other(),
                ),
            ),
        )
        return

    spawn_review = getattr(sess, "spawn_review_thread")
    await _maybe_await(spawn_review(config, turn_context, sub_id, resolved))


async def run_user_shell_command(sess: Any, sub_id: str, command: str) -> None:
    """Run a user shell command in the active turn or a new session task.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``run_user_shell_command``
    """

    active_getter = getattr(sess, "active_turn_context_and_cancellation_token", None)
    if callable(active_getter):
        active = await _maybe_await(active_getter())
        if active is not None:
            turn_context, cancellation_token = active
            executor = getattr(sess, "execute_user_shell_command", None)
            if callable(executor):
                await _maybe_await(
                    executor(
                        turn_context,
                        command,
                        cancellation_token,
                        USER_SHELL_COMMAND_MODE_ACTIVE_TURN_AUXILIARY,
                    )
                )
                return
            auxiliary = getattr(sess, "run_user_shell_command_active_turn_auxiliary", None)
            if callable(auxiliary):
                await _maybe_await(auxiliary(turn_context, command, cancellation_token))
                return

    new_turn = getattr(sess, "new_default_turn_with_sub_id", None)
    if callable(new_turn):
        turn_context = await _maybe_await(new_turn(sub_id))
    else:
        turn_context = await _maybe_await(getattr(sess, "new_default_turn")())
    spawn_task = getattr(sess, "spawn_task")
    await _maybe_await(spawn_task(turn_context, [], UserShellCommandTask(command)))


async def compact(sess: Any, sub_id: str) -> None:
    """Spawn a compact task for a new default turn.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``compact``
    """

    turn_context = await _maybe_await(getattr(sess, "new_default_turn_with_sub_id")(sub_id))
    await _maybe_await(getattr(sess, "spawn_task")(turn_context, [], CompactTask()))


async def dispatch_session_op(sess: Any, sub_id: str, op: Op | dict[str, Any]) -> bool:
    """Dispatch one session operation.

    Rust source:
    - crate: ``codex-core``
    - module: ``session::handlers``
    - item: ``submission_loop`` arm ``Op::ThreadRollback { num_turns }``

    The return value mirrors the Rust submission loop's ``should_exit`` flag.
    The thread rollback arm always returns ``false`` after delegating to
    ``thread_rollback``.
    """

    operation = op if isinstance(op, Op) else Op.from_mapping(op)
    if operation.type == "interrupt":
        await interrupt(sess)
        return False
    if operation.type == "clean_background_terminals":
        await clean_background_terminals(sess)
        return False
    if operation.type == "realtime_conversation_list_voices":
        await realtime_conversation_list_voices(sess, sub_id)
        return False
    if operation.type == "realtime_conversation_start":
        fields = operation.fields or {}
        await realtime_conversation_start(sess, sub_id, ConversationStartParams.from_mapping(fields))
        return False
    if operation.type == "realtime_conversation_audio":
        fields = operation.fields or {}
        await realtime_conversation_audio(sess, sub_id, ConversationAudioParams.from_mapping(fields))
        return False
    if operation.type == "realtime_conversation_text":
        fields = operation.fields or {}
        await realtime_conversation_text(sess, sub_id, ConversationTextParams.from_mapping(fields))
        return False
    if operation.type == "realtime_conversation_close":
        await realtime_conversation_close(sess, sub_id)
        return False
    if operation.type == "reload_user_config":
        await reload_user_config(sess)
        return False
    if operation.type == "user_input":
        await user_input_or_turn(sess, sub_id, operation)
        return False
    if operation.type == "shutdown":
        return await shutdown(sess, sub_id)
    if operation.type == "thread_settings":
        fields = operation.fields or {}
        await update_thread_settings(sess, sub_id, _thread_settings_overrides(fields["thread_settings"]))
        return False
    if operation.type == "set_thread_memory_mode":
        fields = operation.fields or {}
        await set_thread_memory_mode(sess, sub_id, _thread_memory_mode(fields["mode"]))
        return False
    if operation.type == "thread_rollback":
        fields = operation.fields or {}
        await thread_rollback(sess, sub_id, int(fields["num_turns"]))
        return False
    if operation.type == "request_permissions_response":
        fields = operation.fields or {}
        await request_permissions_response(sess, str(fields["id"]), fields["response"])
        return False
    if operation.type == "patch_approval":
        fields = operation.fields or {}
        await patch_approval(sess, str(fields["id"]), ReviewDecision.from_mapping(fields["decision"]))
        return False
    if operation.type == "exec_approval":
        fields = operation.fields or {}
        await exec_approval(
            sess,
            str(fields["id"]),
            str(fields["turn_id"]) if fields.get("turn_id") is not None else None,
            ReviewDecision.from_mapping(fields["decision"]),
        )
        return False
    if operation.type == "user_input_answer":
        fields = operation.fields or {}
        await request_user_input_response(sess, str(fields["id"]), fields["response"])
        return False
    if operation.type == "dynamic_tool_response":
        fields = operation.fields or {}
        await dynamic_tool_response(sess, str(fields["id"]), fields["response"])
        return False
    if operation.type == "refresh_mcp_servers":
        fields = operation.fields or {}
        await refresh_mcp_servers(sess, fields["config"])
        return False
    if operation.type == "resolve_elicitation":
        fields = operation.fields or {}
        await resolve_elicitation(
            sess,
            str(fields["server_name"]),
            fields["request_id"],
            fields["decision"],
            fields.get("content"),
            fields.get("meta"),
        )
        return False
    if operation.type == "review":
        fields = operation.fields or {}
        await review(sess, getattr(sess, "config", None), sub_id, fields["review_request"])
        return False
    if operation.type == "inter_agent_communication":
        fields = operation.fields or {}
        await inter_agent_communication(sess, sub_id, _inter_agent_communication(fields["communication"]))
        return False
    if operation.type == "approve_guardian_denied_action":
        fields = operation.fields or {}
        await approve_guardian_denied_action(sess, _guardian_assessment_event(fields["event"]))
        return False
    if operation.type == "run_user_shell_command":
        fields = operation.fields or {}
        await run_user_shell_command(sess, sub_id, str(fields["command"]))
        return False
    if operation.type == "compact":
        await compact(sess, sub_id)
        return False
    return False


def _read_reconstruction_with_rollback_marker(path: Path, rollback_msg: EventMsg):
    fd, tmp_name = tempfile.mkstemp(prefix="pycodex-thread-rollback-", suffix=".jsonl")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_bytes(path.read_bytes())
        append_event_msg_to_rollout(tmp_path, rollback_msg)
        return read_rollout_reconstruction_from_rollout(tmp_path)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _session_rollout_path(sess: Any) -> Path | None:
    for name in ("rollout_path", "thread_rollout_path", "persisted_thread_history_path"):
        value = getattr(sess, name, None)
        if callable(value):
            value = value()
        if value is not None:
            return Path(value)
    return None


def _has_active_turn(sess: Any) -> bool:
    explicit = getattr(sess, "active_turn_in_progress", None)
    if explicit is not None:
        return bool(explicit)
    active_turn = getattr(sess, "active_turn", None)
    if isinstance(active_turn, bool):
        return active_turn
    if active_turn is None:
        return False
    for name in ("in_progress", "is_active", "active", "turn_in_progress"):
        value = getattr(active_turn, name, None)
        if callable(value):
            value = value()
        if value is not None:
            return bool(value)
    return False


async def _send_thread_rollback_error(sess: Any, sub_id: str, message: str) -> None:
    await _emit_raw_event(
        sess,
        Event(
            id=sub_id,
            msg=EventMsg.with_payload(
                "error",
                ErrorEvent(
                    message=message,
                    codex_error_info=CodexErrorInfo.thread_rollback_failed(),
                ),
            ),
        ),
    )


async def _current_collaboration_mode(sess: Any) -> Any:
    getter = getattr(sess, "current_collaboration_mode", None)
    if callable(getter):
        return await _maybe_await(getter())
    state = getattr(sess, "state", None)
    configuration = getattr(state, "session_configuration", None)
    if configuration is not None:
        mode = getattr(configuration, "collaboration_mode", None)
        if mode is not None:
            return mode
    configuration = getattr(sess, "session_configuration", None)
    return getattr(configuration, "collaboration_mode", None)


def _thread_settings_overrides(value: Any) -> ThreadSettingsOverrides:
    if isinstance(value, ThreadSettingsOverrides):
        return value
    return ThreadSettingsOverrides.from_mapping(value)


def _thread_memory_mode(value: Any) -> ThreadMemoryMode:
    if isinstance(value, ThreadMemoryMode):
        return value
    return ThreadMemoryMode(str(value))


def _guardian_assessment_event(value: Any) -> GuardianAssessmentEvent:
    if isinstance(value, GuardianAssessmentEvent):
        return value
    return GuardianAssessmentEvent.from_mapping(value)


def _inter_agent_communication(value: Any) -> InterAgentCommunication:
    if isinstance(value, InterAgentCommunication):
        return value
    return InterAgentCommunication.from_mapping(value)


def _guardian_action_mapping(value: Any) -> Any:
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        return to_mapping()
    return value


def _no_active_turn_items(exc: Exception) -> tuple[Any, ...] | None:
    if isinstance(exc, NoActiveTurnForUserInput):
        return exc.items
    items = getattr(exc, "items", None)
    if getattr(exc, "type", None) == "no_active_turn" and items is not None:
        return tuple(items)
    return None


def _steer_input_error_event(exc: Exception) -> ErrorEvent:
    to_error_event = getattr(exc, "to_error_event", None)
    if callable(to_error_event):
        return to_error_event()
    return ErrorEvent(message=str(exc), codex_error_info=CodexErrorInfo.other())


async def _record_responsesapi_client_metadata(current_context: Any, metadata: Any) -> None:
    if metadata is None:
        return
    state = getattr(current_context, "turn_metadata_state", None)
    setter = getattr(state, "set_responsesapi_client_metadata", None)
    if callable(setter):
        await _maybe_await(setter(metadata))


async def _record_user_prompt_telemetry(current_context: Any, items: tuple[Any, ...]) -> None:
    telemetry = getattr(current_context, "session_telemetry", None)
    user_prompt = getattr(telemetry, "user_prompt", None)
    if callable(user_prompt):
        await _maybe_await(user_prompt(items))


async def _refresh_mcp_servers_if_requested(sess: Any, current_context: Any) -> None:
    refresh = getattr(sess, "refresh_mcp_servers_if_requested", None)
    if not callable(refresh):
        return
    reviewer_getter = getattr(sess, "mcp_elicitation_reviewer", None)
    reviewer = await _maybe_await(reviewer_getter()) if callable(reviewer_getter) else None
    await _maybe_await(refresh(current_context, reviewer))


async def _merge_additional_context(sess: Any, additional_context: Any) -> tuple[Any, ...]:
    merger = getattr(sess, "merge_additional_context", None)
    if callable(merger):
        return tuple(await _maybe_await(merger(additional_context)))
    state = getattr(sess, "state", None)
    context_store = getattr(state, "additional_context", None)
    merge = getattr(context_store, "merge", None)
    if callable(merge):
        return tuple(await _maybe_await(merge(additional_context)))
    if additional_context is None:
        return ()
    if isinstance(additional_context, dict):
        return tuple(additional_context.values())
    return tuple(additional_context)


async def _mirror_user_text_to_realtime(sess: Any, items: tuple[Any, ...]) -> None:
    mirror = getattr(sess, "mirror_user_text_to_realtime", None)
    if callable(mirror):
        await _maybe_await(mirror(items))


async def _record_shutdown_turn_count(sess: Any) -> None:
    services = getattr(sess, "services", None)
    telemetry = getattr(services, "session_telemetry", None) or getattr(sess, "session_telemetry", None)
    counter = getattr(telemetry, "counter", None)
    if not callable(counter):
        return

    turn_count = 0
    clone_history = getattr(sess, "clone_history", None)
    if callable(clone_history):
        history = await _maybe_await(clone_history())
        raw_items_getter = getattr(history, "raw_items", None)
        raw_items = await _maybe_await(raw_items_getter()) if callable(raw_items_getter) else getattr(history, "raw_items", ())
        turn_count = sum(1 for item in raw_items if _is_user_turn_boundary_like(item))

    await _maybe_await(counter("codex.conversation.turn.count", int(turn_count), []))


def _is_user_turn_boundary_like(item: Any) -> bool:
    if isinstance(item, dict):
        return item.get("role") == "user"
    role = getattr(item, "role", None)
    if role is not None:
        return str(role) == "user"
    return False


async def _shutdown_live_thread(sess: Any, sub_id: str) -> None:
    live_thread_getter = getattr(sess, "live_thread", None)
    live_thread = await _maybe_await(live_thread_getter()) if callable(live_thread_getter) else live_thread_getter
    if live_thread is None:
        return

    shutdown_live_thread = getattr(live_thread, "shutdown", None)
    if not callable(shutdown_live_thread):
        return
    try:
        await _maybe_await(shutdown_live_thread())
    except Exception:  # noqa: BLE001 - mirror Rust error event and continue to ShutdownComplete.
        await _emit_raw_event(
            sess,
            Event(
                id=sub_id,
                msg=EventMsg.with_payload(
                    "error",
                    ErrorEvent(
                        message="Failed to shutdown thread persistence",
                        codex_error_info=CodexErrorInfo.other(),
                    ),
                ),
            ),
        )


async def _record_rollout_protocol_event(sess: Any, msg: EventMsg) -> None:
    trace = _rollout_thread_trace(sess)
    record_protocol_event = getattr(trace, "record_protocol_event", None)
    if callable(record_protocol_event):
        await _maybe_await(record_protocol_event(msg))


async def _record_rollout_ended(sess: Any) -> None:
    trace = _rollout_thread_trace(sess)
    record_ended = getattr(trace, "record_ended", None)
    if callable(record_ended):
        await _maybe_await(record_ended("completed"))


def _rollout_thread_trace(sess: Any) -> Any:
    services = getattr(sess, "services", None)
    return getattr(services, "rollout_thread_trace", None) or getattr(sess, "rollout_thread_trace", None)


async def _emit_raw_event(sess: Any, event: Event, *, prefer_deliver: bool = False) -> None:
    method_names = ("deliver_event_raw", "send_event_raw") if prefer_deliver else ("send_event_raw", "deliver_event_raw")
    for name in method_names:
        method = getattr(sess, name, None)
        if callable(method):
            await _maybe_await(method(event))
            return
    raw_events = getattr(sess, "emitted_raw_events", None)
    if isinstance(raw_events, list):
        raw_events.append(event)
        return
    emitted_events = getattr(sess, "emitted_events", None)
    if isinstance(emitted_events, list):
        emitted_events.append(event.msg)


async def _emit_session_event(sess: Any, turn_context: Any, msg: EventMsg) -> None:
    send_event = getattr(sess, "send_event", None)
    if callable(send_event):
        await _maybe_await(send_event(turn_context, msg))
        return
    sub_id = getattr(turn_context, "sub_id", "")
    await _emit_raw_event(sess, Event(id=sub_id, msg=msg))


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value) or hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "AUTO_REVIEW_DENIED_ACTION_APPROVAL_DEVELOPER_PREFIX",
    "approve_guardian_denied_action",
    "CompactTask",
    "clean_background_terminals",
    "compact",
    "dispatch_session_op",
    "dynamic_tool_response",
    "exec_approval",
    "interrupt",
    "inter_agent_communication",
    "NoActiveTurnForUserInput",
    "patch_approval",
    "persist_thread_memory_mode_update",
    "realtime_conversation_audio",
    "realtime_conversation_close",
    "realtime_conversation_list_voices",
    "realtime_conversation_start",
    "realtime_conversation_text",
    "refresh_mcp_servers",
    "reload_user_config",
    "review",
    "RegularTask",
    "request_permissions_response",
    "request_user_input_response",
    "ResponseItemTurnInput",
    "resolve_elicitation",
    "run_user_shell_command",
    "shutdown",
    "shutdown_session_runtime",
    "set_thread_memory_mode",
    "thread_rollback",
    "thread_settings_applied_event",
    "thread_settings_update",
    "update_thread_settings",
    "user_input_or_turn",
    "user_input_or_turn_inner",
    "UserInputTurnInput",
    "UserShellCommandTask",
    "USER_SHELL_COMMAND_MODE_ACTIVE_TURN_AUXILIARY",
]
