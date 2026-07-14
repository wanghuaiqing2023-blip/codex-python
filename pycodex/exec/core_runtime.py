"""Core in-memory runtime facade for ``codex exec`` user turns.

The implementation still lives in ``pycodex.exec.local_runtime`` while the
Python port keeps the local HTTP compatibility path intact.  This module gives
the CLI a core-facing import boundary for the direct in-memory execution path.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any, TextIO

from pycodex.exec.event_processor import JsonEventProcessor
from pycodex.exec.session import direct_resume_thread_id
from pycodex.exec.local_runtime import (
    align_local_http_exec_resume_model_client as align_core_exec_resume_model_client,
    build_default_local_http_exec_runtime as _build_default_local_http_exec_runtime,
    core_exec_config_summary,
    core_exec_enabled,
    core_exec_initial_messages_from_rollout,
    core_review_rollout_input_items,
    emit_local_http_exec_result,
    persist_core_exec_resume_rollout,
    persist_core_exec_rollout,
    run_exec_review_core_http_sampling,
    run_exec_resume_user_turn_core_http_sampling,
    run_exec_user_turn_core_http_sampling,
    run_exec_user_turn_core_sampling,
)


_LOCAL_HTTP_AUTH_ERROR = "OPENAI_API_KEY or CODEX_API_KEY is required for PYCODEX_EXEC_LOCAL_HTTP=1"
_CORE_AUTH_ERROR = "OPENAI_API_KEY or CODEX_API_KEY is required for core exec runtime"


@dataclass(frozen=True)
class CoreExecResumeTarget:
    """Resolved core resume target and aligned rollout path."""

    thread_id: str | None
    session_name: str | None
    rollout_path: Path


def build_default_core_exec_runtime(
    config: Any,
    *,
    auth: Any = None,
    env: Any = None,
    config_toml: Any = None,
    codex_home: str | Path | None = None,
    client_version: str | None = None,
    models_manager: Any = None,
) -> tuple[Any, Any, Any, Any]:
    """Build core transport and resolve model metadata through models-manager."""

    try:
        model_client, provider, _fallback_model_info, resolved_auth = _build_default_local_http_exec_runtime(
            config,
            auth=auth,
            env=env,
            config_toml=config_toml,
        )
    except ValueError as exc:
        if str(exc) == _LOCAL_HTTP_AUTH_ERROR:
            raise ValueError(_CORE_AUTH_ERROR) from exc
        raise

    manager = models_manager or _build_core_models_manager(
        config,
        provider,
        auth=auth,
        config_toml=config_toml,
        codex_home=codex_home,
        client_version=client_version,
    )
    model_info = _resolve_core_model_info(manager, config)
    return model_client, provider, model_info, resolved_auth


def _build_core_models_manager(
    config: Any,
    provider: Any,
    *,
    auth: Any,
    config_toml: Mapping[str, Any] | None,
    codex_home: str | Path | None,
    client_version: str | None,
) -> Any:
    from pycodex.models_manager import OpenAiModelsManager, StaticModelsManager, bundled_models_response

    model_catalog = getattr(config, "model_catalog", None)
    if model_catalog is None and isinstance(config_toml, Mapping):
        configured_catalog = config_toml.get("model_catalog")
        model_catalog = configured_catalog if isinstance(configured_catalog, Mapping) else None
    if model_catalog is not None:
        return StaticModelsManager(model_catalog=model_catalog)
    if codex_home is None:
        return StaticModelsManager(model_catalog=bundled_models_response())

    from pycodex.model_provider.auth import auth_service_from_snapshot
    from pycodex.model_provider.models_endpoint import OpenAiModelsEndpoint
    from pycodex.model_provider_info import ModelProviderInfo

    try:
        auth_manager = _run_awaitable_blocking(
            auth_service_from_snapshot(
                Path(codex_home),
                auth,
                getattr(config, "chatgpt_base_url", None),
            )
        )
    except (OSError, RuntimeError, ValueError):
        auth_manager = None
    base_url = getattr(provider, "base_url", None)
    provider_info = ModelProviderInfo.create_openai_provider(
        str(base_url) if isinstance(base_url, str) and base_url else None
    )
    return OpenAiModelsManager(
        Path(codex_home),
        OpenAiModelsEndpoint(provider_info, auth_manager),
        auth_manager,
        client_version=client_version,
    )


def _resolve_core_model_info(models_manager: Any, config: Any) -> Any:
    from pycodex.models_manager import ModelsManagerConfig, RefreshStrategy

    strategy = RefreshStrategy.ONLINE_IF_UNCACHED
    list_models = getattr(models_manager, "list_models")
    try:
        _run_awaitable_blocking(list_models(strategy))
    except (OSError, RuntimeError, ValueError):
        strategy = RefreshStrategy.OFFLINE

    requested_model = getattr(config, "model", None)
    model = _run_awaitable_blocking(models_manager.get_default_model(requested_model, strategy))
    converter = getattr(config, "to_models_manager_config", None)
    manager_config = converter() if callable(converter) else ModelsManagerConfig()
    return _run_awaitable_blocking(models_manager.get_model_info(model, manager_config))


def _run_awaitable_blocking(awaitable: Any) -> Any:
    """Resolve Rust-shaped async manager methods from synchronous CLI startup."""

    if not hasattr(awaitable, "__await__"):
        return awaitable
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result: dict[str, Any] = {}

    def worker() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:  # pragma: no cover - re-raised below
            result["error"] = exc

    thread = Thread(target=worker, name="pycodex-models-manager", daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def resolve_core_exec_resume_target(
    codex_home: str | Path,
    session_config: Any,
    model_client: Any,
    resume_args: Any,
) -> CoreExecResumeTarget | None:
    """Resolve resume CLI args into the core runtime's local rollout target."""

    if resume_args is None:
        raise ValueError("resume command is missing resume arguments")
    session_id = getattr(resume_args, "session_id", None)
    thread_id = direct_resume_thread_id(session_id)
    session_name = session_id if session_id is not None and thread_id is None else None
    resume_last = bool(getattr(resume_args, "last", False))
    include_all = bool(getattr(resume_args, "all", False))
    rollout_path = align_core_exec_resume_model_client(
        codex_home,
        session_config,
        model_client,
        thread_id=thread_id,
        session_name=session_name,
        resume_last=resume_last,
        include_all=include_all,
    )
    if rollout_path is None:
        return None
    return CoreExecResumeTarget(
        thread_id=thread_id,
        session_name=session_name,
        rollout_path=Path(rollout_path),
    )


def core_exec_rollout_input_items(command: str, plan: Any, result: Any) -> tuple[Any, ...]:
    """Return the input items to persist for a completed core exec command."""

    if command == "review":
        return tuple(core_review_rollout_input_items(result))
    if command == "resume":
        return ()
    initial_operation = getattr(plan, "initial_operation", None)
    if getattr(initial_operation, "kind", None) != "user_turn":
        return ()
    return tuple(getattr(initial_operation, "items", ()) or ())


def persist_core_exec_result(
    command: str,
    codex_home: str | Path,
    session_config: Any,
    result: Any,
    model_client: Any,
    plan: Any,
    *,
    cli_version: str,
    model_info: Any = None,
) -> bool:
    """Persist a completed core exec result when the command owns a new rollout turn."""

    if command == "resume":
        return False
    persist_core_exec_rollout(
        codex_home,
        session_config,
        result,
        model_client,
        input_items=core_exec_rollout_input_items(command, plan, result),
        cli_version=cli_version,
        model_info=model_info,
    )
    return True


async def run_core_exec_command(
    command: str | None,
    codex_home: str | Path,
    session_config: Any,
    plan: Any,
    model_client: Any,
    provider: Any,
    model_info: Any,
    *,
    resume_args: Any = None,
    resume_target: CoreExecResumeTarget | None = None,
    resume_target_resolved: bool = False,
    auth: Any = None,
    endpoint: str | None = None,
    timeout: float | None = None,
    opener: Any = None,
    built_tools: Any = None,
    max_tool_followups: int | None = None,
    cli_version: str,
    auth_manager: Any = None,
) -> Any:
    """Run one prepared non-interactive core exec command and persist owned turns."""

    if auth_manager is None:
        from pycodex.login.auth.manager import AuthManager

        auth_manager = await AuthManager.new(codex_home, True)

    if command == "review":
        result = await run_exec_review_core_http_sampling(
            session_config,
            plan,
            model_client,
            provider,
            model_info,
            auth=auth,
            endpoint=endpoint,
            timeout=timeout,
            opener=opener,
            built_tools=built_tools,
            max_tool_followups=max_tool_followups,
            auth_manager=auth_manager,
        )
        persist_core_exec_result(
            command,
            codex_home,
            session_config,
            result,
            model_client,
            plan,
            cli_version=cli_version,
            model_info=model_info,
        )
        return result

    if command == "resume":
        if resume_args is None:
            raise ValueError("resume command is missing resume arguments")
        target = resume_target
        if target is None and not resume_target_resolved:
            target = resolve_core_exec_resume_target(
                codex_home,
                session_config,
                model_client,
                resume_args,
            )
        if target is None:
            result = await run_exec_user_turn_core_http_sampling(
                session_config,
                plan,
                model_client,
                provider,
                model_info,
                auth=auth,
                endpoint=endpoint,
                timeout=timeout,
                opener=opener,
                built_tools=built_tools,
                max_tool_followups=max_tool_followups,
                auth_manager=auth_manager,
            )
            persist_core_exec_result(
                "exec",
                codex_home,
                session_config,
                result,
                model_client,
                plan,
                cli_version=cli_version,
                model_info=model_info,
            )
            return result
        return await run_exec_resume_user_turn_core_http_sampling(
            Path(codex_home),
            session_config,
            plan,
            model_client,
            provider,
            model_info,
            thread_id=target.thread_id,
            session_name=target.session_name,
            resume_last=bool(getattr(resume_args, "last", False)),
            include_all=bool(getattr(resume_args, "all", False)),
            auth=auth,
            endpoint=endpoint,
            timeout=timeout,
            opener=opener,
            built_tools=built_tools,
            resolved_rollout_path=target.rollout_path,
            max_tool_followups=max_tool_followups,
            auth_manager=auth_manager,
        )

    result = await run_exec_user_turn_core_http_sampling(
        session_config,
        plan,
        model_client,
        provider,
        model_info,
        auth=auth,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        built_tools=built_tools,
        max_tool_followups=max_tool_followups,
        auth_manager=auth_manager,
    )
    persist_core_exec_result(
        command or "exec",
        codex_home,
        session_config,
        result,
        model_client,
        plan,
        cli_version=cli_version,
        model_info=model_info,
    )
    return result


def emit_core_exec_config_summary(
    processor: Any,
    session_config: Any,
    plan: Any,
    model_client: Any,
    model_info: Any,
    *,
    rollout_path: str | Path | None = None,
    stdout: TextIO,
    stderr: TextIO,
    version: str,
) -> tuple[Any, Any]:
    """Build and emit the core exec config summary for one non-interactive run."""

    summary_config, summary_session = core_exec_config_summary(
        session_config,
        model=getattr(model_info, "slug"),
        provider_id=getattr(session_config, "model_provider_id", None) or "openai",
        session_id=str(model_client.state.session_id),
        thread_id=str(model_client.state.thread_id),
        initial_messages=(
            core_exec_initial_messages_from_rollout(rollout_path)
            if rollout_path is not None
            else None
        ),
        rollout_path=rollout_path,
    )
    if isinstance(processor, JsonEventProcessor):
        processor.print_config_summary(
            summary_config,
            plan.prompt_summary,
            summary_session,
            output=stdout,
        )
    else:
        processor.print_config_summary(
            summary_config,
            plan.prompt_summary,
            summary_session,
            stderr=stderr,
            version=version,
        )
    return summary_config, summary_session


def emit_core_exec_result(
    command: str,
    processor: Any,
    result: Any,
    session_config: Any,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> None:
    """Emit the final result and completion status for a core exec command."""

    emit_local_http_exec_result(
        processor,
        result,
        config=session_config,
        stdout=stdout,
        stderr=stderr,
    )
    print(f"pycodex: completed core non-interactive {command} execution.", file=stderr)


__all__ = [
    "align_core_exec_resume_model_client",
    "build_default_core_exec_runtime",
    "CoreExecResumeTarget",
    "core_exec_config_summary",
    "core_exec_enabled",
    "core_exec_initial_messages_from_rollout",
    "core_exec_rollout_input_items",
    "core_review_rollout_input_items",
    "emit_core_exec_config_summary",
    "emit_core_exec_result",
    "persist_core_exec_result",
    "persist_core_exec_resume_rollout",
    "persist_core_exec_rollout",
    "run_core_exec_command",
    "run_exec_review_core_http_sampling",
    "run_exec_resume_user_turn_core_http_sampling",
    "run_exec_user_turn_core_http_sampling",
    "run_exec_user_turn_core_sampling",
    "resolve_core_exec_resume_target",
]
