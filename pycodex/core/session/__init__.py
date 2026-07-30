"""Session runtime modules aligned with ``codex-rs/core/src/session``."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from pycodex.core.session.handlers import (
    AUTO_REVIEW_DENIED_ACTION_APPROVAL_DEVELOPER_PREFIX,
    approve_guardian_denied_action,
    CompactTask,
    clean_background_terminals,
    compact,
    dispatch_session_op,
    dynamic_tool_response,
    exec_approval,
    interrupt,
    inter_agent_communication,
    NoActiveTurnForUserInput,
    patch_approval,
    persist_thread_memory_mode_update,
    realtime_conversation_audio,
    realtime_conversation_close,
    realtime_conversation_list_voices,
    realtime_conversation_start,
    realtime_conversation_text,
    refresh_mcp_servers,
    reload_user_config,
    review,
    RegularTask,
    request_permissions_response,
    request_user_input_response,
    ResponseItemTurnInput,
    resolve_elicitation,
    run_user_shell_command,
    set_thread_memory_mode,
    shutdown,
    shutdown_session_runtime,
    thread_rollback,
    thread_settings_applied_event,
    thread_settings_update,
    update_thread_settings,
    user_input_or_turn,
    user_input_or_turn_inner,
    UserInputTurnInput,
)
from pycodex.core.session.config_lock import (
    export_config_lock_if_configured,
    session_configuration_to_lock_config_toml,
    to_config_lockfile_toml,
    validate_config_lock_if_configured,
)
from pycodex.core.session.multi_agents import usage_hint_text
from pycodex.core.session.review import (
    build_review_turn_context,
    review_config_for_review,
    review_features_for_review,
    spawn_review_thread,
)
from pycodex.core.session.rollout_reconstruction import (
    PreviousTurnSettings,
    RolloutReconstruction,
    read_model_history_from_rollout,
    read_rollout_reconstruction_from_rollout,
    reconstruct_history_from_rollout,
    reconstruct_history_from_rollout_async,
    turn_ids_are_compatible,
)
from pycodex.protocol import Event, EventMsg, Op, Submission


class Codex:
    """Running core session owned by Rust ``session::Codex``.

    Transport-facing wrappers submit protocol operations and consume protocol
    events through this object. Sampling remains in the shared core turn
    runtime; this class owns only the session task and event channels.
    """

    def __init__(
        self,
        *,
        config: Any,
        model_client: Any,
        provider: Any,
        model_info: Any,
        auth: Any,
        auth_manager: Any,
        session: Any,
        codex_home: Path,
    ) -> None:
        self.config = config
        self.model_client = model_client
        self.provider = provider
        self.model_info = model_info
        self.auth = auth
        self.auth_manager = auth_manager
        self.session = session
        self.codex_home = Path(codex_home)
        self._events: asyncio.Queue[Event] = asyncio.Queue()
        self._turn_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closed = False
        self._current_submission_id = ""

    @classmethod
    async def spawn(cls, options: Any) -> tuple["Codex", str, dict[str, Any]]:
        """Spawn the runtime used by ``ThreadManager::spawn_thread_with_source``."""

        from pycodex.core.config.edit import CONFIG_TOML_FILE, read_toml_mapping
        from pycodex.exec.local_runtime import (
            build_default_local_http_exec_runtime,
            create_exec_core_session,
        )
        from pycodex.utils.home_dir import find_codex_home

        config = options.config
        codex_home = Path(find_codex_home())
        config_toml = read_toml_mapping(codex_home / CONFIG_TOML_FILE)
        model_client, provider, model_info, auth = build_default_local_http_exec_runtime(
            config,
            auth=options.auth_manager,
            config_toml=config_toml,
        )
        thread_id = str(model_client.state.thread_id)
        codex = cls(
            config=config,
            model_client=model_client,
            provider=provider,
            model_info=model_info,
            auth=auth,
            auth_manager=options.auth_manager,
            session=None,
            codex_home=codex_home,
        )
        session = create_exec_core_session(
            config,
            model_info,
            model_client=model_client,
            provider=provider,
            auth_manager=options.auth_manager,
            event_observer=codex._observe_session_event,
            thread_id=thread_id,
            state_db=None,
        )
        if options.session_source is not None:
            session.session_source = options.session_source
            model_client.state.session_source = options.session_source
        codex.session = session
        session_configured = {
            "type": "session_configured",
            "thread_id": thread_id,
            "model": str(getattr(model_info, "slug", getattr(config, "model", ""))),
            "model_provider_id": str(getattr(config, "model_provider_id", "") or "openai"),
            "cwd": str(getattr(config, "cwd", Path.cwd())),
        }
        return codex, thread_id, session_configured

    async def submit(self, op: Op) -> str:
        submission_id = str(uuid.uuid4())
        await self.submit_with_id(Submission(id=submission_id, op=op))
        return submission_id

    async def submit_with_id(self, submission: Submission) -> None:
        if self._closed:
            raise RuntimeError("Codex session is shut down")
        if not isinstance(submission, Submission):
            submission = Submission.from_mapping(submission)
        operation = submission.op
        if operation.type == "user_input":
            task = asyncio.create_task(
                self._run_user_turn(submission),
                name=f"pycodex-core-turn-{submission.id}",
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return
        should_exit = await dispatch_session_op(self.session, submission.id, operation)
        if should_exit:
            self._closed = True

    async def next_event(self) -> Event:
        return await self._events.get()

    async def shutdown_and_wait(self) -> None:
        if self._closed and not self._tasks:
            return
        self._closed = True
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _observe_session_event(self, msg: EventMsg | dict[str, Any]) -> None:
        resolved = msg if isinstance(msg, EventMsg) else EventMsg.from_mapping(msg)
        await self._events.put(Event(id=self._current_submission_id, msg=resolved))

    async def _run_user_turn(self, submission: Submission) -> None:
        from pycodex.exec.local_runtime import (
            run_exec_user_turn_core_sampling_websocket_preferred,
        )
        from pycodex.exec.run import ExecRunPlan, InitialOperation

        fields = submission.op.fields or {}
        plan = ExecRunPlan(
            initial_operation=InitialOperation.user_turn(
                tuple(fields.get("items", ())),
                fields.get("final_output_json_schema"),
                thread_settings=fields.get("thread_settings"),
            ),
            prompt_summary="",
        )
        async with self._turn_lock:
            self._current_submission_id = submission.id
            try:
                await run_exec_user_turn_core_sampling_websocket_preferred(
                    self.config,
                    plan,
                    self.model_client,
                    self.provider,
                    self.model_info,
                    auth=self.auth,
                    auth_manager=self.auth_manager,
                    codex_home=self.codex_home,
                    session_event_observer=self._observe_session_event,
                    core_session=self.session,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._events.put(
                    Event(
                        id=submission.id,
                        msg=EventMsg.with_payload("error", {"message": str(exc)}),
                    )
                )
            finally:
                self._current_submission_id = ""

__all__ = [
    "AUTO_REVIEW_DENIED_ACTION_APPROVAL_DEVELOPER_PREFIX",
    "approve_guardian_denied_action",
    "build_review_turn_context",
    "CompactTask",
    "clean_background_terminals",
    "Codex",
    "compact",
    "dispatch_session_op",
    "dynamic_tool_response",
    "exec_approval",
    "export_config_lock_if_configured",
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
    "review_config_for_review",
    "review_features_for_review",
    "PreviousTurnSettings",
    "read_model_history_from_rollout",
    "read_rollout_reconstruction_from_rollout",
    "reconstruct_history_from_rollout",
    "reconstruct_history_from_rollout_async",
    "RegularTask",
    "request_permissions_response",
    "request_user_input_response",
    "ResponseItemTurnInput",
    "resolve_elicitation",
    "run_user_shell_command",
    "RolloutReconstruction",
    "session_configuration_to_lock_config_toml",
    "set_thread_memory_mode",
    "shutdown",
    "shutdown_session_runtime",
    "spawn_review_thread",
    "thread_rollback",
    "thread_settings_applied_event",
    "thread_settings_update",
    "to_config_lockfile_toml",
    "turn_ids_are_compatible",
    "update_thread_settings",
    "user_input_or_turn",
    "user_input_or_turn_inner",
    "UserInputTurnInput",
    "usage_hint_text",
    "validate_config_lock_if_configured",
]
