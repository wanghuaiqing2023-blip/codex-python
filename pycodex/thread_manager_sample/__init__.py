"""Sample ThreadManager CLI ported from ``codex-thread-manager-sample``.

The Rust crate is a small binary that runs one prompt through ``ThreadManager``
and writes mapped app-server notifications as newline-delimited JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TextIO

from pycodex import core_api
from pycodex.protocol import Op, UserInput


class SampleError(RuntimeError):
    """User-facing failure for the sample binary."""


@dataclass(frozen=True)
class Args:
    model: str | None
    prompt: tuple[str, ...] = ()


@dataclass(frozen=True)
class SampleAdapters:
    """Runtime hooks used by ``run_main``.

    Defaults point at the existing ``core_api`` facade. Tests can inject small
    fakes without widening this crate's module boundary.
    """

    find_codex_home: Callable[[], Path | str] = core_api.find_codex_home
    current_dir: Callable[[], Path | str] = Path.cwd
    built_in_model_providers: Callable[[str | None], Mapping[str, Any]] = core_api.built_in_model_providers
    init_state_db: Callable[[Any], Any] = core_api.init_state_db
    thread_store_from_config: Callable[[Any, Any], Any] = core_api.thread_store_from_config
    resolve_installation_id: Callable[[Path], Any] = core_api.resolve_installation_id
    item_event_to_server_notification: Callable[[Any, str, str], Any] = core_api.item_event_to_server_notification
    set_default_originator: Callable[[str], Any] = core_api.set_default_originator
    auth_manager_factory: Callable[[Any], Any] | None = None
    environment_manager_factory: Callable[[Any, Any], Any] | None = None
    thread_manager_factory: Callable[..., Any] | None = None


def parse_args(argv: Iterable[str] | None = None) -> Args:
    parser = argparse.ArgumentParser(
        prog="codex-thread-manager-sample",
        description=(
            "Run one Codex turn through ThreadManager and print mapped "
            "notifications as newline-delimited JSON."
        ),
    )
    parser.add_argument("--model", metavar="MODEL")
    parser.add_argument("prompt", nargs=argparse.REMAINDER)
    namespace = parser.parse_args(list(argv) if argv is not None else None)
    return Args(model=namespace.model, prompt=tuple(namespace.prompt or ()))


def prompt_from_args_or_stdin(args: Args, stdin: TextIO | None = None) -> str:
    if args.prompt:
        return " ".join(args.prompt)
    stdin = stdin if stdin is not None else sys.stdin
    if _is_terminal(stdin):
        raise SampleError("no prompt provided; pass a prompt argument or pipe one into stdin")
    prompt = stdin.read().replace("\r\n", "\n").replace("\r", "\n")
    if not prompt.strip():
        raise SampleError("no prompt provided via stdin")
    return prompt


def new_config(
    model: str | None,
    arg0_paths: Any,
    adapters: SampleAdapters | None = None,
) -> SimpleNamespace:
    adapters = adapters or SampleAdapters()
    codex_home = Path(adapters.find_codex_home())
    cwd = Path(adapters.current_dir())
    model_provider_id = core_api.OPENAI_PROVIDER_ID
    model_providers = dict(adapters.built_in_model_providers(None))
    try:
        model_provider = model_providers[model_provider_id]
    except KeyError as exc:
        raise SampleError("OpenAI model provider should be available") from exc

    features = core_api.Features()
    set_features = getattr(features, "set", None)
    with_defaults = getattr(core_api.Features, "with_defaults", None)
    if callable(set_features) and callable(with_defaults):
        set_features(with_defaults())

    return SimpleNamespace(
        config_layer_stack=core_api.ConfigLayerStack(),
        startup_warnings=[],
        bypass_hook_trust=False,
        model=model,
        service_tier=None,
        review_model=None,
        model_provider_id=model_provider_id,
        model_provider=model_provider,
        model_providers=model_providers,
        permissions=core_api.Permissions(
            {
                "approval": "never",
                "profile": "read_only",
            }
        ),
        approvals_reviewer=_member(core_api.ApprovalsReviewer, "User"),
        include_permissions_instructions=False,
        include_apps_instructions=False,
        include_collaboration_mode_instructions=False,
        include_skill_instructions=False,
        include_environment_context=False,
        tui_notifications=core_api.TuiNotificationSettings(),
        model_availability_nux=core_api.ModelAvailabilityNuxConfig(),
        tui_alternate_screen=_member(core_api.AltScreenMode, "Auto"),
        tui_keymap=core_api.TuiKeymap(),
        tui_session_picker_view=_member(core_api.SessionPickerViewMode, "Dense"),
        tui_pet_anchor=_member(core_api.TuiPetAnchor, "Composer"),
        terminal_resize_reflow=core_api.TerminalResizeReflowConfig(),
        cwd=cwd,
        workspace_roots=[cwd],
        workspace_roots_explicit=False,
        cli_auth_credentials_store_mode=_member(core_api.AuthCredentialsStoreMode, "File"),
        mcp_servers={},
        mcp_oauth_credentials_store_mode=_member(core_api.OAuthCredentialsStoreMode, "File"),
        memories=core_api.MemoriesConfig(),
        sqlite_home=codex_home,
        log_dir=codex_home / "log",
        codex_home=codex_home,
        history=core_api.History(),
        ephemeral=True,
        file_opener=_member(core_api.UriBasedFileOpener, "VsCode"),
        codex_self_exe=getattr(arg0_paths, "codex_self_exe", None),
        codex_linux_sandbox_exe=getattr(arg0_paths, "codex_linux_sandbox_exe", None),
        main_execve_wrapper_exe=getattr(arg0_paths, "main_execve_wrapper_exe", None),
        chatgpt_base_url="https://chatgpt.com/backend-api/",
        realtime_audio=core_api.RealtimeAudioConfig(),
        realtime=core_api.RealtimeConfig(),
        experimental_thread_store=core_api.ThreadStoreConfig.local(),
        web_search_mode=_member(core_api.WebSearchMode, "Disabled"),
        background_terminal_max_timeout=300_000,
        ghost_snapshot=core_api.GhostSnapshotConfig(),
        multi_agent_v2=core_api.MultiAgentV2Config(),
        features=features,
        active_project=core_api.ProjectConfig(trust_level=None),
        notices=core_api.Notice(),
        check_for_update_on_startup=False,
        analytics_enabled=False,
        feedback_enabled=False,
        tool_suggest=core_api.ToolSuggestConfig(),
        otel=core_api.OtelConfig(),
    )


async def run_main(
    arg0_paths: Any,
    argv: Iterable[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    adapters: SampleAdapters | None = None,
) -> None:
    adapters = adapters or SampleAdapters()
    stdout = stdout if stdout is not None else sys.stdout
    try:
        await _maybe_await(adapters.set_default_originator("codex_thread_manager_sample"))
    except Exception:
        pass

    args = parse_args(argv)
    prompt = prompt_from_args_or_stdin(args, stdin)
    config = new_config(args.model, arg0_paths, adapters)
    state_db = await _maybe_await(adapters.init_state_db(config))
    auth_manager = await _maybe_await(
        adapters.auth_manager_factory(config) if adapters.auth_manager_factory else core_api.AuthManager()
    )
    local_runtime_paths = _exec_server_runtime_paths(
        getattr(config, "codex_self_exe", None),
        getattr(config, "codex_linux_sandbox_exe", None),
    )
    thread_store = adapters.thread_store_from_config(config, state_db)
    environment_manager = await _maybe_await(
        adapters.environment_manager_factory(config, local_runtime_paths)
        if adapters.environment_manager_factory
        else core_api.EnvironmentManager.from_codex_home(config.codex_home, local_runtime_paths)
    )
    installation_id = await _maybe_await(adapters.resolve_installation_id(config.codex_home))
    thread_manager = _thread_manager(
        config,
        adapters,
        auth_manager,
        environment_manager,
        thread_store,
        state_db,
        installation_id,
    )

    new_thread = await _maybe_await(thread_manager.start_thread(config))
    thread_id = str(getattr(new_thread, "thread_id"))
    thread = getattr(new_thread, "thread")

    turn_error: BaseException | None = None
    try:
        await run_turn(thread, thread_id, prompt, stdout=stdout, adapters=adapters)
    except BaseException as exc:
        turn_error = exc

    shutdown_error: BaseException | None = None
    try:
        await _maybe_await(thread.shutdown_and_wait())
    except BaseException as exc:
        shutdown_error = exc
    remove_thread = getattr(thread_manager, "remove_thread", None)
    if callable(remove_thread):
        await _maybe_await(remove_thread(getattr(new_thread, "thread_id")))

    if turn_error is not None:
        raise turn_error
    if shutdown_error is not None:
        raise SampleError(f"shut down Codex thread: {shutdown_error}") from shutdown_error


async def run_turn(
    thread: Any,
    thread_id: str,
    prompt: str,
    *,
    stdout: TextIO | None = None,
    adapters: SampleAdapters | None = None,
) -> None:
    adapters = adapters or SampleAdapters()
    stdout = stdout if stdout is not None else sys.stdout
    await _maybe_await(
        thread.submit(
            Op.user_input(
                items=[UserInput.text_input(prompt)],
                environments=None,
                final_output_json_schema=None,
                responsesapi_client_metadata=None,
                additional_context={},
            )
        )
    )

    current_turn_id: str | None = None
    while True:
        event = await _maybe_await(thread.next_event())
        msg = getattr(event, "msg", event)
        event_type = event_msg_type(msg)
        if event_type == "turn_started":
            current_turn_id = str(_payload_field(msg, "turn_id"))
        elif event_type in _MAPPED_EVENT_TYPES:
            if current_turn_id is None:
                raise SampleError("mapped notification arrived before turn started")
            notification = adapters.item_event_to_server_notification(msg, thread_id, current_turn_id)
            stdout.write(json.dumps(notification_to_mapping(notification), separators=(",", ":")) + "\n")
            stdout.flush()

        if event_type == "turn_complete":
            return
        if event_type == "error":
            raise SampleError(str(_payload_field(msg, "message")))
        if event_type == "turn_aborted":
            raise SampleError("turn aborted")
        if event_type == "exec_approval_request":
            raise SampleError("turn requested exec approval")
        if event_type == "apply_patch_approval_request":
            raise SampleError("turn requested patch approval")
        if event_type == "request_permissions":
            raise SampleError("turn requested permissions")
        if event_type == "request_user_input":
            raise SampleError("turn requested user input")
        if event_type == "dynamic_tool_call_request":
            raise SampleError("turn requested a dynamic tool call")


def event_msg_type(msg: Any) -> str:
    value = getattr(msg, "type", None)
    if isinstance(value, str):
        return _normalize_event_type(value)
    if isinstance(msg, Mapping):
        for key in ("type", "msg", "event"):
            if isinstance(msg.get(key), str):
                return _normalize_event_type(str(msg[key]))
    name = type(msg).__name__
    return _normalize_event_type(name)


def notification_to_mapping(notification: Any) -> Any:
    to_mapping = getattr(notification, "to_mapping", None)
    if callable(to_mapping):
        return to_mapping()
    if isinstance(notification, Mapping):
        return dict(notification)
    return notification


def main(argv: Iterable[str] | None = None) -> int:
    try:
        core_api.arg0_dispatch_or_else(lambda arg0_paths: asyncio.run(run_main(arg0_paths, argv)))
    except SampleError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _thread_manager(
    config: Any,
    adapters: SampleAdapters,
    auth_manager: Any,
    environment_manager: Any,
    thread_store: Any,
    state_db: Any,
    installation_id: Any,
) -> Any:
    if adapters.thread_manager_factory is not None:
        return adapters.thread_manager_factory(
            config=config,
            auth_manager=auth_manager,
            session_source=_session_source_exec(),
            environment_manager=environment_manager,
            extension_registry=core_api.empty_extension_registry(),
            analytics_events_client=None,
            thread_store=thread_store,
            state_db=state_db,
            installation_id=installation_id,
            attestation_provider=None,
        )
    return core_api.ThreadManager.new(
        auth_manager=auth_manager,
        session_source=_session_source_exec(),
        environment_manager=environment_manager,
        thread_store=thread_store,
        state_db=state_db,
    )


def _exec_server_runtime_paths(codex_self_exe: Any, codex_linux_sandbox_exe: Any) -> Any:
    from_optional_paths = getattr(core_api.ExecServerRuntimePaths, "from_optional_paths", None)
    if callable(from_optional_paths):
        return from_optional_paths(codex_self_exe, codex_linux_sandbox_exe)
    try:
        return core_api.ExecServerRuntimePaths(fs_helper=None)
    except TypeError:
        return SimpleNamespace(
            codex_self_exe=codex_self_exe,
            codex_linux_sandbox_exe=codex_linux_sandbox_exe,
        )


def _session_source_exec() -> Any:
    value = getattr(core_api.SessionSource, "Exec", None)
    if value is not None:
        return value
    exec_factory = getattr(core_api.SessionSource, "exec", None)
    if callable(exec_factory):
        return exec_factory()
    return "exec"


def _is_terminal(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


def _member(enum_type: Any, rust_name: str) -> Any:
    for candidate in (
        rust_name,
        rust_name.upper(),
        rust_name.replace("Vs", "VS").upper(),
    ):
        if hasattr(enum_type, candidate):
            return getattr(enum_type, candidate)
    value = rust_name[0].lower() + rust_name[1:]
    try:
        return enum_type(value)
    except Exception:
        return value


def _normalize_event_type(value: str) -> str:
    chars: list[str] = []
    previous_lower = False
    for char in value:
        if char in {"-", " "}:
            chars.append("_")
            previous_lower = False
            continue
        if char.isupper() and previous_lower:
            chars.append("_")
        chars.append(char.lower())
        previous_lower = char.islower() or char.isdigit()
    text = "".join(chars)
    aliases = {
        "turn_started_event": "turn_started",
        "turn_complete_event": "turn_complete",
        "turn_completed": "turn_complete",
        "error_event": "error",
        "turn_aborted_event": "turn_aborted",
        "exec_approval_request_event": "exec_approval_request",
        "apply_patch_approval_request_event": "apply_patch_approval_request",
        "request_permissions_event": "request_permissions",
        "request_user_input_event": "request_user_input",
        "dynamic_tool_call_request_event": "dynamic_tool_call_request",
    }
    return aliases.get(text, text)


def _payload_field(msg: Any, name: str) -> Any:
    if isinstance(msg, Mapping):
        if name in msg:
            return msg[name]
        payload = msg.get("payload")
        if isinstance(payload, Mapping) and name in payload:
            return payload[name]
    if hasattr(msg, name):
        return getattr(msg, name)
    payload = getattr(msg, "payload", None)
    if isinstance(payload, Mapping) and name in payload:
        return payload[name]
    if hasattr(payload, name):
        return getattr(payload, name)
    raise SampleError(f"event is missing {name}")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


_MAPPED_EVENT_TYPES = {
    "dynamic_tool_call_response",
    "mcp_tool_call_begin",
    "mcp_tool_call_end",
    "collab_agent_spawn_begin",
    "collab_agent_spawn_end",
    "collab_agent_interaction_begin",
    "collab_agent_interaction_end",
    "collab_waiting_begin",
    "collab_waiting_end",
    "collab_close_begin",
    "collab_close_end",
    "collab_resume_begin",
    "collab_resume_end",
    "agent_message_content_delta",
    "plan_delta",
    "reasoning_content_delta",
    "reasoning_raw_content_delta",
    "agent_reasoning_section_break",
    "item_started",
    "item_completed",
    "patch_apply_begin",
    "patch_apply_updated",
    "terminal_interaction",
    "exec_command_begin",
    "exec_command_output_delta",
    "exec_command_end",
}


__all__ = [
    "Args",
    "SampleAdapters",
    "SampleError",
    "event_msg_type",
    "main",
    "new_config",
    "notification_to_mapping",
    "parse_args",
    "prompt_from_args_or_stdin",
    "run_main",
    "run_turn",
]
