"""Configuration planning helpers for ``codex exec``.

Ported from the pre-``ConfigBuilder`` slice of
``codex/codex-rs/exec/src/lib.rs``.  The full config loader is still being
ported elsewhere; this module keeps the CLI-to-harness override projection
explicit and testable so the eventual runner can feed the same values into the
Python app-server path.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import json
import sys
from typing import Any
from typing import BinaryIO, TextIO

from pycodex.app_server_client import (
    DEFAULT_IN_PROCESS_CHANNEL_CAPACITY,
    EnvironmentManager,
    ExecServerRuntimePaths,
    InProcessClientStartArgs,
    StateDbHandle,
)
from pycodex.arg0 import Arg0DispatchPaths
from pycodex.config import ConfigOverride, apply_single_override
from pycodex.core.agents_md import (
    DEFAULT_PROJECT_DOC_MAX_BYTES,
    AgentsMdConfig,
    AgentsMdManager,
)
from pycodex.features import Feature, FeatureConfigSource, FeatureOverrides, Features, FeaturesToml
from pycodex.git_utils import get_git_repo_root
from pycodex.core.otel_init import OtelProvider
from pycodex.core.otel_init import build_provider as build_otel_provider
from pycodex.utils.home_dir import find_codex_home
from pycodex.protocol import AskForApproval, GranularApprovalConfig, PermissionProfile, SandboxMode

from .cli import ExecCli
from .event_processor import (
    final_message_from_notification_items,
    handle_last_message,
    should_print_final_message_to_stdout,
    should_print_final_message_to_tty,
)
from .run import ExecRunPlan, prepare_exec_run_plan
from .session import (
    ClientRequest,
    ExecLoopAction,
    ExecLoopStepResult,
    ExecSessionConfig,
    ExecSessionStartupResult,
    InitialOperationRequest,
    InitialOperationResult,
    RequestIdSequencer,
    ThreadBootstrapRequest,
    ThreadBootstrapResult,
    exec_session_startup_result,
    exec_session_startup_processor_actions,
    exec_loop_actions_from_step,
    exec_loop_step,
    initial_operation_result_from_response,
    initial_operation_request_from_plan,
    next_initial_operation_request,
    thread_bootstrap_request,
    thread_bootstrap_result_from_response,
)

JsonValue = Any

UPSTREAM_EXEC_RUN_MAIN = "codex/codex-rs/exec/src/lib.rs"
DEFAULT_ANALYTICS_ENABLED = True
EXEC_DEFAULT_LOG_FILTER = "error,opentelemetry_sdk=off,opentelemetry_otlp=off"
EXEC_UNTRUSTED_DIRECTORY_MESSAGE = "Not inside a trusted directory and --skip-git-repo-check was not specified."
LMSTUDIO_OSS_PROVIDER_ID = "lmstudio"
OLLAMA_OSS_PROVIDER_ID = "ollama"
LMSTUDIO_DEFAULT_OSS_MODEL = "openai/gpt-oss-20b"
OLLAMA_DEFAULT_OSS_MODEL = "gpt-oss:20b"
NO_DEFAULT_OSS_PROVIDER_MESSAGE = (
    "No default OSS provider configured. Use --local-provider=provider or set oss_provider "
    f"to one of: {LMSTUDIO_OSS_PROVIDER_ID}, {OLLAMA_OSS_PROVIDER_ID} in config.toml"
)


class ExecConfigPlanError(ValueError):
    """Raised when ``codex exec`` config planning cannot continue."""


@dataclass(frozen=True)
class ExecHarnessOverrides:
    """Subset of upstream ``ConfigOverrides`` supplied by ``codex exec``."""

    model: str | None = None
    approval_policy: AskForApproval | GranularApprovalConfig | None = AskForApproval.NEVER
    sandbox_mode: SandboxMode | None = None
    cwd: Path | None = None
    model_provider: str | None = None
    model_reasoning_effort: JsonValue | None = None
    model_reasoning_summary: JsonValue | None = None
    service_tier: str | None = None
    show_raw_agent_reasoning: bool | None = None
    ephemeral: bool | None = None
    bypass_hook_trust: bool | None = None
    additional_writable_roots: tuple[Path, ...] = ()
    upstream_source: str = UPSTREAM_EXEC_RUN_MAIN

    def __post_init__(self) -> None:
        if self.cwd is not None and not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        object.__setattr__(
            self,
            "additional_writable_roots",
            tuple(Path(root) for root in self.additional_writable_roots),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "model": self.model,
            "approvalPolicy": _enum_value(self.approval_policy),
            "sandboxMode": _enum_value(self.sandbox_mode),
            "cwd": str(self.cwd) if self.cwd is not None else None,
            "modelProvider": self.model_provider,
            "modelReasoningEffort": self.model_reasoning_effort,
            "modelReasoningSummary": self.model_reasoning_summary,
            "serviceTier": self.service_tier,
            "showRawAgentReasoning": self.show_raw_agent_reasoning,
            "ephemeral": self.ephemeral,
            "bypassHookTrust": self.bypass_hook_trust,
            "additionalWritableRoots": [str(root) for root in self.additional_writable_roots],
        }
        return {key: value for key, value in data.items() if value is not None and value != []}


@dataclass(frozen=True)
class ExecConfigBootstrapPlan:
    """Values resolved before upstream builds the full runtime ``Config``."""

    config_cwd: Path
    strict_config: bool = False
    ignore_user_config: bool = False
    ignore_rules: bool = False
    cli_overrides: tuple[ConfigOverride, ...] = ()
    harness_overrides: ExecHarnessOverrides = ExecHarnessOverrides()
    user_instructions: str | None = None
    instruction_sources: tuple[Path, ...] = ()
    startup_warnings: tuple[str, ...] = ()
    mcp_servers: Mapping[str, JsonValue] | None = None
    allow_login_shell: bool = True
    features: Features | None = None
    exec_permission_approvals_enabled: bool = False
    request_permissions_tool_enabled: bool = False
    tui_status_line: tuple[str, ...] | None = None
    tui_status_line_use_colors: bool = True
    tui_terminal_title: tuple[str, ...] | None = None
    upstream_source: str = UPSTREAM_EXEC_RUN_MAIN

    def __post_init__(self) -> None:
        if not isinstance(self.config_cwd, Path):
            object.__setattr__(self, "config_cwd", Path(self.config_cwd))
        object.__setattr__(self, "cli_overrides", tuple(self.cli_overrides))
        object.__setattr__(self, "instruction_sources", tuple(Path(path) for path in self.instruction_sources))
        object.__setattr__(self, "startup_warnings", tuple(str(warning) for warning in self.startup_warnings))
        if self.tui_status_line is not None:
            object.__setattr__(self, "tui_status_line", tuple(str(item) for item in self.tui_status_line))
        if self.tui_terminal_title is not None:
            object.__setattr__(self, "tui_terminal_title", tuple(str(item) for item in self.tui_terminal_title))
        servers = self.mcp_servers if isinstance(self.mcp_servers, Mapping) else {}
        object.__setattr__(self, "mcp_servers", copy.deepcopy(dict(servers)))
        if self.features is None:
            object.__setattr__(self, "features", Features.with_defaults())

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "configCwd": str(self.config_cwd),
            "strictConfig": self.strict_config,
            "ignoreUserConfig": self.ignore_user_config,
            "ignoreRules": self.ignore_rules,
            "cliOverrides": [
                {"path": override.path, "value": override.value} for override in self.cli_overrides
            ],
            "harnessOverrides": self.harness_overrides.to_mapping(),
            "userInstructions": self.user_instructions,
            "instructionSources": [str(path) for path in self.instruction_sources],
            "startupWarnings": list(self.startup_warnings),
            "mcpServers": copy.deepcopy(dict(self.mcp_servers or {})),
            "allowLoginShell": self.allow_login_shell,
            "execPermissionApprovalsEnabled": self.exec_permission_approvals_enabled,
            "requestPermissionsToolEnabled": self.request_permissions_tool_enabled,
            "tuiStatusLine": list(self.tui_status_line) if self.tui_status_line is not None else None,
            "tuiStatusLineUseColors": self.tui_status_line_use_colors,
            "tuiTerminalTitle": list(self.tui_terminal_title) if self.tui_terminal_title is not None else None,
        }


@dataclass(frozen=True)
class ExecRuntimeStartupPlan:
    """Composed startup inputs for the non-interactive exec runtime."""

    bootstrap_plan: ExecConfigBootstrapPlan
    session_config: ExecSessionConfig
    run_plan: ExecRunPlan
    trusted_directory_check: "ExecTrustedDirectoryCheckPlan"

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "bootstrapPlan": self.bootstrap_plan.to_mapping(),
            "sessionConfig": self.session_config.to_mapping()
            if hasattr(self.session_config, "to_mapping")
            else _exec_session_config_to_mapping(self.session_config),
            "runPlan": {
                "initialOperation": self.run_plan.initial_operation.kind,
                "promptSummary": self.run_plan.prompt_summary,
            },
            "trustedDirectoryCheck": self.trusted_directory_check.to_mapping(),
        }


@dataclass(frozen=True)
class ExecRunMainPlan:
    """Pure plan for the Rust ``run_main`` startup orchestration."""

    startup: ExecRuntimeStartupPlan
    processor_kind: str
    stderr_with_ansi: bool
    local_runtime_paths: ExecServerRuntimePaths
    state_db: StateDbHandle | None
    environment_manager_source: str
    in_process_start_args: InProcessClientStartArgs
    telemetry_service_name: str = "codex_exec"
    analytics_enabled: bool = DEFAULT_ANALYTICS_ENABLED
    log_filter: str = EXEC_DEFAULT_LOG_FILTER
    upstream_source: str = UPSTREAM_EXEC_RUN_MAIN

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "startup": self.startup.to_mapping(),
            "processorKind": self.processor_kind,
            "stderrWithAnsi": self.stderr_with_ansi,
            "environmentManagerSource": self.environment_manager_source,
            "telemetryServiceName": self.telemetry_service_name,
            "analyticsEnabled": self.analytics_enabled,
            "logFilter": self.log_filter,
            "inProcessStartArgs": {
                "clientName": self.in_process_start_args.client_name,
                "clientVersion": self.in_process_start_args.client_version,
                "strictConfig": self.in_process_start_args.strict_config,
                "enableCodexApiKeyEnv": self.in_process_start_args.enable_codex_api_key_env,
                "experimentalApi": self.in_process_start_args.experimental_api,
                "channelCapacity": self.in_process_start_args.channel_capacity,
                "configWarnings": list(self.in_process_start_args.config_warnings),
                "sessionSource": self.in_process_start_args.session_source,
            },
        }


@dataclass(frozen=True)
class ExecTrustedDirectoryCheckPlan:
    """Rust-shaped pre-client trusted-directory gate for ``codex exec``."""

    allowed: bool
    cwd: Path
    git_repo_root: Path | None = None
    skipped_by_flag: bool = False
    skipped_by_dangerous_bypass: bool = False
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if self.git_repo_root is not None and not isinstance(self.git_repo_root, Path):
            object.__setattr__(self, "git_repo_root", Path(self.git_repo_root))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "allowed": self.allowed,
            "cwd": str(self.cwd),
            "gitRepoRoot": str(self.git_repo_root) if self.git_repo_root is not None else None,
            "skippedByFlag": self.skipped_by_flag,
            "skippedByDangerousBypass": self.skipped_by_dangerous_bypass,
            "message": self.message,
        }


@dataclass(frozen=True)
class ExecRuntimeActionSummary:
    """Runner-facing summary of executable loop actions."""

    actions: tuple[ExecLoopAction, ...]
    client_requests: tuple[ClientRequest, ...]
    server_requests: tuple[JsonValue, ...]
    notifications: tuple[JsonValue, ...]
    agent_messages: tuple[str, ...]
    final_messages: tuple[str, ...]
    config_summaries: tuple[JsonValue, ...]
    warnings: tuple[str, ...]
    should_break: bool

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "actions": [action.to_mapping() for action in self.actions],
            "clientRequests": [request.to_mapping() for request in self.client_requests],
            "serverRequests": list(self.server_requests),
            "notifications": list(self.notifications),
            "agentMessages": list(self.agent_messages),
            "finalMessages": list(self.final_messages),
            "configSummaries": list(self.config_summaries),
            "warnings": list(self.warnings),
            "shouldBreak": self.should_break,
        }


def _agent_messages_from_notifications(notifications: tuple[JsonValue, ...]) -> tuple[str, ...]:
    messages: list[str] = []
    for notification in notifications:
        if not isinstance(notification, dict):
            continue
        params = notification.get("params")
        if not isinstance(params, dict):
            continue
        turn = params.get("turn")
        if not isinstance(turn, dict):
            continue
        items = turn.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "agentMessage":
                continue
            text = item.get("text")
            if isinstance(text, str):
                messages.append(text)
    return tuple(messages)


def _final_messages_from_notifications(notifications: tuple[JsonValue, ...]) -> tuple[str, ...]:
    messages: list[str] = []
    for notification in notifications:
        if not isinstance(notification, dict):
            continue
        params = notification.get("params")
        if not isinstance(params, dict):
            continue
        turn = params.get("turn")
        if not isinstance(turn, dict):
            continue
        items = turn.get("items")
        if not isinstance(items, list):
            continue
        final_message = final_message_from_notification_items(items)
        if final_message is not None:
            messages.append(final_message)
    return tuple(messages)


def _notification_turn_status(notification: JsonValue) -> str | None:
    if not isinstance(notification, dict):
        return None
    params = notification.get("params")
    if not isinstance(params, dict):
        return None
    turn = params.get("turn")
    if not isinstance(turn, dict):
        return None
    status = turn.get("status")
    return status if isinstance(status, str) else None


def _transcript_final_messages_from_action_summaries(
    summaries: tuple[ExecRuntimeActionSummary, ...]
) -> tuple[str, ...]:
    messages: list[str] = []
    for summary in summaries:
        for notification in summary.notifications:
            status = _notification_turn_status(notification)
            if status in {"failed", "interrupted", "Failed", "Interrupted"}:
                messages.clear()
                continue
            if status is not None and status not in {"completed", "Completed"}:
                continue
            params = notification.get("params") if isinstance(notification, dict) else None
            turn = params.get("turn") if isinstance(params, dict) else None
            items = turn.get("items") if isinstance(turn, dict) else None
            if not isinstance(items, list):
                continue
            final_message = final_message_from_notification_items(items)
            if final_message is not None:
                messages.append(final_message)
    return tuple(messages)


def _event_exchange_notification(exchange: ExecRuntimeEventExchange) -> JsonValue | None:
    notification_decision = exchange.step.decision.notification
    if notification_decision is None:
        return None
    return notification_decision.notification


def _turn_statuses_from_event_exchanges(
    exchanges: tuple[ExecRuntimeEventExchange, ...]
) -> tuple[str, ...]:
    statuses: list[str] = []
    for exchange in exchanges:
        status = _notification_turn_status(_event_exchange_notification(exchange))
        if status is not None:
            statuses.append(status)
    return tuple(statuses)


def _transcript_final_messages_from_event_exchanges(
    exchanges: tuple[ExecRuntimeEventExchange, ...]
) -> tuple[str, ...]:
    messages: list[str] = []
    for exchange in exchanges:
        notification = _event_exchange_notification(exchange)
        if notification is None:
            continue
        status = _notification_turn_status(notification)
        if status in {"failed", "interrupted", "Failed", "Interrupted"}:
            messages.clear()
            continue
        if status is not None and status not in {"completed", "Completed"}:
            continue
        params = notification.get("params") if isinstance(notification, dict) else None
        turn = params.get("turn") if isinstance(params, dict) else None
        items = turn.get("items") if isinstance(turn, dict) else None
        if not isinstance(items, list):
            continue
        final_message = final_message_from_notification_items(items)
        if final_message is not None:
            messages.append(final_message)
    return tuple(messages)


def exec_runtime_action_summary(actions: tuple[ExecLoopAction, ...]) -> ExecRuntimeActionSummary:
    notifications = tuple(
        action.notification for action in actions if action.kind == "process_notification" and action.notification is not None
    )
    return ExecRuntimeActionSummary(
        actions=actions,
        client_requests=tuple(
            action.client_request for action in actions if action.kind == "send_request" and action.client_request is not None
        ),
        server_requests=tuple(
            action.server_request.to_mapping() if hasattr(action.server_request, "to_mapping") else action.server_request
            for action in actions
            if action.kind == "handle_server_request" and action.server_request is not None
        ),
        notifications=notifications,
        agent_messages=_agent_messages_from_notifications(notifications),
        final_messages=_final_messages_from_notifications(notifications),
        config_summaries=tuple(
            action.to_mapping() for action in actions if action.kind == "print_config_summary"
        ),
        warnings=tuple(
            str(action.warning) for action in actions if action.kind == "process_warning" and action.warning is not None
        ),
        should_break=any(action.kind == "break" for action in actions),
    )


@dataclass(frozen=True)
class ExecRuntimeEventInput:
    """Runner input for processing one server event."""

    event: JsonValue
    processor_status: JsonValue = "running"
    thread_read_response: JsonValue | None = None


@dataclass(frozen=True)
class ExecRuntimeEventExchange:
    """Single event-loop exchange state for a runner."""

    step: ExecLoopStepResult
    actions: tuple[ExecLoopAction, ...]

    @property
    def action_summary(self) -> ExecRuntimeActionSummary:
        return exec_runtime_action_summary(self.actions)


@dataclass(frozen=True)
class ExecRuntimeInitialRequestPlan:
    """Parsed bootstrap state plus the initial operation request to send next."""

    bootstrap: ThreadBootstrapResult
    initial_operation_request: InitialOperationRequest

    @property
    def request(self) -> ClientRequest:
        return self.initial_operation_request.request


@dataclass(frozen=True)
class ExecRuntimeStartupExchange:
    """Completed startup exchange state for a runner."""

    initial_request_plan: ExecRuntimeInitialRequestPlan
    startup_result: ExecSessionStartupResult
    processor_actions: tuple[ExecLoopAction, ...]

    @property
    def action_summary(self) -> ExecRuntimeActionSummary:
        return exec_runtime_action_summary(self.processor_actions)


@dataclass(frozen=True)
class ExecRuntimeRunnerTranscript:
    """Runner-facing transcript of startup plus processed event exchanges."""

    startup_exchange: ExecRuntimeStartupExchange
    event_exchanges: tuple[ExecRuntimeEventExchange, ...] = ()
    bootstrap_request: ClientRequest | None = None

    def with_event_exchange(self, event_exchange: ExecRuntimeEventExchange) -> "ExecRuntimeRunnerTranscript":
        return ExecRuntimeRunnerTranscript(
            startup_exchange=self.startup_exchange,
            event_exchanges=(*self.event_exchanges, event_exchange),
            bootstrap_request=self.bootstrap_request,
        )

    @property
    def action_summaries(self) -> tuple[ExecRuntimeActionSummary, ...]:
        return (
            self.startup_exchange.action_summary,
            *(exchange.action_summary for exchange in self.event_exchanges),
        )

    @property
    def bootstrap_client_requests(self) -> tuple[ClientRequest, ...]:
        if self.bootstrap_request is None:
            return ()
        return (self.bootstrap_request,)

    @property
    def initial_client_requests(self) -> tuple[ClientRequest, ...]:
        return (self.startup_exchange.initial_request_plan.request,)

    @property
    def startup_client_requests(self) -> tuple[ClientRequest, ...]:
        return (*self.bootstrap_client_requests, *self.initial_client_requests)

    @property
    def client_requests(self) -> tuple[ClientRequest, ...]:
        return tuple(
            request
            for summary in self.action_summaries
            for request in summary.client_requests
        )

    @property
    def all_client_requests(self) -> tuple[ClientRequest, ...]:
        return (*self.startup_client_requests, *self.client_requests)

    @property
    def server_requests(self) -> tuple[JsonValue, ...]:
        return tuple(
            request
            for summary in self.action_summaries
            for request in summary.server_requests
        )

    @property
    def notifications(self) -> tuple[JsonValue, ...]:
        return tuple(
            notification
            for summary in self.action_summaries
            for notification in summary.notifications
        )

    @property
    def agent_messages(self) -> tuple[str, ...]:
        return tuple(
            message
            for summary in self.action_summaries
            for message in summary.agent_messages
        )

    @property
    def final_messages(self) -> tuple[str, ...]:
        return _transcript_final_messages_from_event_exchanges(self.event_exchanges)

    @property
    def final_agent_message(self) -> str | None:
        if not self.agent_messages:
            return None
        return self.agent_messages[-1]

    @property
    def final_message(self) -> str | None:
        if not self.final_messages:
            return None
        return self.final_messages[-1]

    @property
    def config_summaries(self) -> tuple[JsonValue, ...]:
        return tuple(
            config_summary
            for summary in self.action_summaries
            for config_summary in summary.config_summaries
        )

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(
            warning
            for summary in self.action_summaries
            for warning in summary.warnings
        )

    @property
    def turn_statuses(self) -> tuple[str, ...]:
        return _turn_statuses_from_event_exchanges(self.event_exchanges)

    @property
    def terminal_turn_status(self) -> str | None:
        if not self.turn_statuses:
            return None
        return self.turn_statuses[-1]

    @property
    def should_break(self) -> bool:
        return any(summary.should_break for summary in self.action_summaries)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "bootstrapClientRequests": [request.to_mapping() for request in self.bootstrap_client_requests],
            "initialClientRequests": [request.to_mapping() for request in self.initial_client_requests],
            "startupClientRequests": [request.to_mapping() for request in self.startup_client_requests],
            "clientRequests": [request.to_mapping() for request in self.client_requests],
            "allClientRequests": [request.to_mapping() for request in self.all_client_requests],
            "serverRequests": list(self.server_requests),
            "notifications": list(self.notifications),
            "agentMessages": list(self.agent_messages),
            "finalMessages": list(self.final_messages),
            "finalAgentMessage": self.final_agent_message,
            "finalMessage": self.final_message,
            "configSummaries": list(self.config_summaries),
            "warnings": list(self.warnings),
            "turnStatuses": list(self.turn_statuses),
            "terminalTurnStatus": self.terminal_turn_status,
            "shouldBreak": self.should_break,
            "eventExchangeCount": len(self.event_exchanges),
            "actionSummaries": [summary.to_mapping() for summary in self.action_summaries],
        }


@dataclass(frozen=True)
class ExecRuntimeFinalMessageOutputPlan:
    """Output decisions for a runner final message."""

    final_message: str | None
    stdout_text: str | None
    tty_text: str | None
    last_message_contents: str | None
    last_message_path: str | None = None

    @property
    def should_write_last_message(self) -> bool:
        return self.last_message_path is not None and self.last_message_contents is not None

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "finalMessage": self.final_message,
            "stdoutText": self.stdout_text,
            "ttyText": self.tty_text,
            "lastMessageContents": self.last_message_contents,
            "lastMessagePath": self.last_message_path,
            "shouldWriteLastMessage": self.should_write_last_message,
        }


def apply_exec_runtime_final_message_output_plan(
    plan: ExecRuntimeFinalMessageOutputPlan,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    stdout_target = stdout if stdout is not None else sys.stdout
    stderr_target = stderr if stderr is not None else sys.stderr
    if plan.stdout_text is not None:
        print(plan.stdout_text, file=stdout_target)
    if plan.tty_text is not None:
        print(plan.tty_text, file=stderr_target)
    if plan.should_write_last_message and plan.last_message_path is not None:
        handle_last_message(plan.last_message_contents, Path(plan.last_message_path), stderr=stderr_target)


@dataclass(frozen=True)
class ExecRuntimeRunnerResult:
    """Final runner-facing result derived from a transcript."""

    transcript: ExecRuntimeRunnerTranscript

    @property
    def final_message(self) -> str | None:
        return self.transcript.final_message

    @property
    def completed(self) -> bool:
        return self.transcript.should_break

    @property
    def terminal_turn_status(self) -> str | None:
        return self.transcript.terminal_turn_status

    @property
    def succeeded(self) -> bool:
        return self.terminal_turn_status in {"completed", "Completed"}

    @property
    def outcome(self) -> str:
        status = self.terminal_turn_status
        if status in {"completed", "Completed"}:
            return "success"
        if status in {"failed", "Failed"}:
            return "failed"
        if status in {"interrupted", "Interrupted"}:
            return "interrupted"
        return "incomplete"

    @property
    def request_count(self) -> int:
        return len(self.transcript.all_client_requests)

    @property
    def exit_code(self) -> int:
        return 0 if self.succeeded else 1

    def final_message_output_plan(
        self,
        *,
        stdout_is_terminal: bool,
        stderr_is_terminal: bool,
        final_message_rendered: bool = False,
        output_last_message: bool = False,
        last_message_path: str | Path | None = None,
    ) -> ExecRuntimeFinalMessageOutputPlan:
        message = self.final_message if self.completed else None
        stdout_text = (
            message
            if should_print_final_message_to_stdout(message, stdout_is_terminal, stderr_is_terminal)
            else None
        )
        tty_text = (
            message
            if should_print_final_message_to_tty(
                message,
                final_message_rendered,
                stdout_is_terminal,
                stderr_is_terminal,
            )
            else None
        )
        normalized_last_message_path = str(last_message_path) if last_message_path is not None else None
        should_capture_last_message = output_last_message or normalized_last_message_path is not None
        return ExecRuntimeFinalMessageOutputPlan(
            final_message=message,
            stdout_text=stdout_text,
            tty_text=tty_text,
            last_message_contents=message if should_capture_last_message and message is not None else None,
            last_message_path=normalized_last_message_path,
        )

    def final_message_output_plan_from_cli(
        self,
        cli: ExecCli,
        *,
        stdout_is_terminal: bool,
        stderr_is_terminal: bool,
        final_message_rendered: bool = False,
    ) -> ExecRuntimeFinalMessageOutputPlan:
        return self.final_message_output_plan(
            stdout_is_terminal=stdout_is_terminal,
            stderr_is_terminal=stderr_is_terminal,
            final_message_rendered=final_message_rendered,
            last_message_path=cli.last_message_file,
        )

    def apply_final_message_output_from_cli(
        self,
        cli: ExecCli,
        *,
        stdout_is_terminal: bool,
        stderr_is_terminal: bool,
        final_message_rendered: bool = False,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> ExecRuntimeFinalMessageOutputPlan:
        plan = self.final_message_output_plan_from_cli(
            cli,
            stdout_is_terminal=stdout_is_terminal,
            stderr_is_terminal=stderr_is_terminal,
            final_message_rendered=final_message_rendered,
        )
        apply_exec_runtime_final_message_output_plan(plan, stdout=stdout, stderr=stderr)
        return plan

    def apply_cli_completion(
        self,
        cli: ExecCli,
        *,
        stdout_is_terminal: bool,
        stderr_is_terminal: bool,
        final_message_rendered: bool = False,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> ExecRuntimeCliCompletion:
        output_plan = self.apply_final_message_output_from_cli(
            cli,
            stdout_is_terminal=stdout_is_terminal,
            stderr_is_terminal=stderr_is_terminal,
            final_message_rendered=final_message_rendered,
            stdout=stdout,
            stderr=stderr,
        )
        return ExecRuntimeCliCompletion(result=self, output_plan=output_plan)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "completed": self.completed,
            "succeeded": self.succeeded,
            "outcome": self.outcome,
            "terminalTurnStatus": self.terminal_turn_status,
            "exitCode": self.exit_code,
            "finalMessage": self.final_message,
            "requestCount": self.request_count,
            "transcript": self.transcript.to_mapping(),
        }


@dataclass(frozen=True)
class ExecRuntimeCliCompletion:
    """CLI-facing completion result after final-message output is applied."""

    result: ExecRuntimeRunnerResult
    output_plan: ExecRuntimeFinalMessageOutputPlan

    @property
    def completed(self) -> bool:
        return self.result.completed

    @property
    def ready_to_exit(self) -> bool:
        return self.terminal_turn_status is not None

    @property
    def succeeded(self) -> bool:
        return self.result.succeeded

    @property
    def final_message(self) -> str | None:
        return self.result.final_message

    @property
    def terminal_turn_status(self) -> str | None:
        return self.result.terminal_turn_status

    @property
    def exit_code(self) -> int:
        return self.result.exit_code

    @property
    def outcome(self) -> str:
        return self.result.outcome

    @property
    def json_payload(self) -> dict[str, JsonValue]:
        return {
            "outcome": self.outcome,
            "exitCode": self.exit_code,
            "succeeded": self.succeeded,
            "completed": self.completed,
            "readyToExit": self.ready_to_exit,
            "terminalTurnStatus": self.terminal_turn_status,
            "finalMessage": self.final_message,
            "outputPlan": self.output_plan.to_mapping(),
        }

    def json_payload_text(self) -> str:
        return json.dumps(self.json_payload, ensure_ascii=False, separators=(",", ":"))

    def apply_json_payload_output(self, *, stdout: TextIO | None = None) -> str:
        text = self.json_payload_text()
        stdout_target = stdout if stdout is not None else sys.stdout
        print(text, file=stdout_target)
        return text

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "completed": self.completed,
            "readyToExit": self.ready_to_exit,
            "succeeded": self.succeeded,
            "finalMessage": self.final_message,
            "terminalTurnStatus": self.terminal_turn_status,
            "exitCode": self.exit_code,
            "outcome": self.outcome,
            "jsonPayload": self.json_payload,
            "result": self.result.to_mapping(),
            "outputPlan": self.output_plan.to_mapping(),
        }


def exec_runtime_runner_result(transcript: ExecRuntimeRunnerTranscript) -> ExecRuntimeRunnerResult:
    return ExecRuntimeRunnerResult(transcript=transcript)


def exec_runtime_runner_transcript(
    startup_exchange: ExecRuntimeStartupExchange,
    event_exchanges: tuple[ExecRuntimeEventExchange, ...] = (),
    *,
    bootstrap_request: ClientRequest | None = None,
) -> ExecRuntimeRunnerTranscript:
    return ExecRuntimeRunnerTranscript(
        startup_exchange=startup_exchange,
        event_exchanges=event_exchanges,
        bootstrap_request=bootstrap_request,
    )


@dataclass(frozen=True)
class ExecRuntimeRequestSequence:
    """Prepared request sequence state for exec startup."""

    startup: ExecRuntimeStartupPlan
    request_ids: RequestIdSequencer
    bootstrap_request: ThreadBootstrapRequest

    def ensure_trusted_directory(self) -> None:
        ensure_exec_trusted_directory(self.startup.trusted_directory_check)

    def trusted_bootstrap_request(self) -> ThreadBootstrapRequest:
        """Return the bootstrap request after enforcing Rust's pre-client cwd gate."""

        self.ensure_trusted_directory()
        return self.bootstrap_request

    def next_initial_operation_request(self, bootstrap: ThreadBootstrapResult) -> InitialOperationRequest:
        return next_initial_operation_request_from_startup_plan(
            self.startup,
            self.request_ids,
            bootstrap,
        )

    def startup_client_requests_from_bootstrap_result(
        self, bootstrap: ThreadBootstrapResult
    ) -> tuple[ClientRequest, ClientRequest]:
        initial_request = self.next_initial_operation_request(bootstrap)
        return (self.bootstrap_request.request, initial_request.request)

    def bootstrap_result_from_response(self, response: JsonValue) -> ThreadBootstrapResult:
        return thread_bootstrap_result_from_response(
            self.bootstrap_request.action,
            response,
            self.startup.session_config,
        )

    def initial_request_plan_from_bootstrap_response(
        self, response: JsonValue
    ) -> ExecRuntimeInitialRequestPlan:
        bootstrap = self.bootstrap_result_from_response(response)
        return ExecRuntimeInitialRequestPlan(
            bootstrap=bootstrap,
            initial_operation_request=self.next_initial_operation_request(bootstrap),
        )

    def initial_client_request_from_bootstrap_response(self, response: JsonValue) -> ClientRequest:
        """Return the next initial request, consuming one request id."""
        return self.initial_request_plan_from_bootstrap_response(response).request

    def startup_result_from_request_responses(
        self,
        *,
        bootstrap_response: JsonValue,
        initial_operation_request: InitialOperationRequest,
        initial_operation_response: JsonValue,
    ) -> ExecSessionStartupResult:
        bootstrap = self.bootstrap_result_from_response(bootstrap_response)
        return self.startup_result_from_responses(
            bootstrap,
            initial_operation_method=initial_operation_request.request.method,
            initial_operation_response=initial_operation_response,
        )

    def startup_processor_actions_from_request_responses(
        self,
        *,
        bootstrap_response: JsonValue,
        initial_operation_request: InitialOperationRequest,
        initial_operation_response: JsonValue,
        json_mode: bool = False,
        system_bwrap_warning: str | None = None,
    ) -> tuple[ExecLoopAction, ...]:
        startup_result = self.startup_result_from_request_responses(
            bootstrap_response=bootstrap_response,
            initial_operation_request=initial_operation_request,
            initial_operation_response=initial_operation_response,
        )
        return self.startup_processor_actions(
            startup_result,
            json_mode=json_mode,
            system_bwrap_warning=system_bwrap_warning,
        )

    def startup_exchange_from_responses(
        self,
        *,
        bootstrap_response: JsonValue,
        initial_operation_response: JsonValue,
        json_mode: bool = False,
        system_bwrap_warning: str | None = None,
    ) -> ExecRuntimeStartupExchange:
        initial_request_plan = self.initial_request_plan_from_bootstrap_response(bootstrap_response)
        startup_result = self.startup_result_from_responses(
            initial_request_plan.bootstrap,
            initial_operation_method=initial_request_plan.request.method,
            initial_operation_response=initial_operation_response,
        )
        processor_actions = self.startup_processor_actions(
            startup_result,
            json_mode=json_mode,
            system_bwrap_warning=system_bwrap_warning,
        )
        return ExecRuntimeStartupExchange(
            initial_request_plan=initial_request_plan,
            startup_result=startup_result,
            processor_actions=processor_actions,
        )

    def runner_transcript_from_responses(
        self,
        *,
        bootstrap_response: JsonValue,
        initial_operation_response: JsonValue,
        event_inputs: tuple[ExecRuntimeEventInput, ...] = (),
        json_mode: bool = False,
        system_bwrap_warning: str | None = None,
    ) -> ExecRuntimeRunnerTranscript:
        startup_exchange = self.startup_exchange_from_responses(
            bootstrap_response=bootstrap_response,
            initial_operation_response=initial_operation_response,
            json_mode=json_mode,
            system_bwrap_warning=system_bwrap_warning,
        )
        transcript = exec_runtime_runner_transcript(
            startup_exchange,
            bootstrap_request=self.bootstrap_request.request,
        )
        return self.append_event_inputs_to_runner_transcript(transcript, event_inputs)

    def runner_result_from_responses(
        self,
        *,
        bootstrap_response: JsonValue,
        initial_operation_response: JsonValue,
        event_inputs: tuple[ExecRuntimeEventInput, ...] = (),
        json_mode: bool = False,
        system_bwrap_warning: str | None = None,
    ) -> ExecRuntimeRunnerResult:
        transcript = self.runner_transcript_from_responses(
            bootstrap_response=bootstrap_response,
            initial_operation_response=initial_operation_response,
            event_inputs=event_inputs,
            json_mode=json_mode,
            system_bwrap_warning=system_bwrap_warning,
        )
        return exec_runtime_runner_result(transcript)

    def cli_completion_from_responses(
        self,
        cli: ExecCli,
        *,
        bootstrap_response: JsonValue,
        initial_operation_response: JsonValue,
        event_inputs: tuple[ExecRuntimeEventInput, ...] = (),
        stdout_is_terminal: bool,
        stderr_is_terminal: bool,
        final_message_rendered: bool = False,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        json_mode: bool = False,
        system_bwrap_warning: str | None = None,
    ) -> ExecRuntimeCliCompletion:
        result = self.runner_result_from_responses(
            bootstrap_response=bootstrap_response,
            initial_operation_response=initial_operation_response,
            event_inputs=event_inputs,
            json_mode=json_mode,
            system_bwrap_warning=system_bwrap_warning,
        )
        return result.apply_cli_completion(
            cli,
            stdout_is_terminal=stdout_is_terminal,
            stderr_is_terminal=stderr_is_terminal,
            final_message_rendered=final_message_rendered,
            stdout=stdout,
            stderr=stderr,
        )

    def cli_json_completion_from_responses(
        self,
        cli: ExecCli,
        *,
        bootstrap_response: JsonValue,
        initial_operation_response: JsonValue,
        event_inputs: tuple[ExecRuntimeEventInput, ...] = (),
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        system_bwrap_warning: str | None = None,
    ) -> ExecRuntimeCliCompletion:
        result = self.runner_result_from_responses(
            bootstrap_response=bootstrap_response,
            initial_operation_response=initial_operation_response,
            event_inputs=event_inputs,
            json_mode=True,
            system_bwrap_warning=system_bwrap_warning,
        )
        output_plan = result.final_message_output_plan_from_cli(
            cli,
            stdout_is_terminal=True,
            stderr_is_terminal=True,
            final_message_rendered=True,
        )
        apply_exec_runtime_final_message_output_plan(output_plan, stdout=stdout, stderr=stderr)
        completion = ExecRuntimeCliCompletion(result=result, output_plan=output_plan)
        completion.apply_json_payload_output(stdout=stdout)
        return completion

    def completion_from_responses(
        self,
        cli: ExecCli,
        *,
        bootstrap_response: JsonValue,
        initial_operation_response: JsonValue,
        event_inputs: tuple[ExecRuntimeEventInput, ...] = (),
        stdout_is_terminal: bool,
        stderr_is_terminal: bool,
        final_message_rendered: bool = False,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        system_bwrap_warning: str | None = None,
    ) -> ExecRuntimeCliCompletion:
        if cli.json:
            return self.cli_json_completion_from_responses(
                cli,
                bootstrap_response=bootstrap_response,
                initial_operation_response=initial_operation_response,
                event_inputs=event_inputs,
                stdout=stdout,
                stderr=stderr,
                system_bwrap_warning=system_bwrap_warning,
            )
        return self.cli_completion_from_responses(
            cli,
            bootstrap_response=bootstrap_response,
            initial_operation_response=initial_operation_response,
            event_inputs=event_inputs,
            stdout_is_terminal=stdout_is_terminal,
            stderr_is_terminal=stderr_is_terminal,
            final_message_rendered=final_message_rendered,
            stdout=stdout,
            stderr=stderr,
            system_bwrap_warning=system_bwrap_warning,
        )

    def append_event_input_to_runner_transcript(
        self,
        transcript: ExecRuntimeRunnerTranscript,
        event_input: ExecRuntimeEventInput,
    ) -> ExecRuntimeRunnerTranscript:
        event_exchange = self.exec_loop_exchange(
            transcript.startup_exchange.startup_result,
            event_input.event,
            processor_status=event_input.processor_status,
            thread_read_response=event_input.thread_read_response,
        )
        return transcript.with_event_exchange(event_exchange)

    def append_event_inputs_to_runner_transcript(
        self,
        transcript: ExecRuntimeRunnerTranscript,
        event_inputs: tuple[ExecRuntimeEventInput, ...],
    ) -> ExecRuntimeRunnerTranscript:
        updated = transcript
        for event_input in event_inputs:
            if updated.should_break:
                break
            updated = self.append_event_input_to_runner_transcript(updated, event_input)
        return updated

    def startup_result_from_responses(
        self,
        bootstrap: ThreadBootstrapResult,
        *,
        initial_operation_method: str,
        initial_operation_response: JsonValue,
    ) -> ExecSessionStartupResult:
        return exec_session_startup_result_from_responses(
            self.startup,
            bootstrap,
            initial_operation_method=initial_operation_method,
            initial_operation_response=initial_operation_response,
        )

    def startup_processor_actions(
        self,
        startup_result: ExecSessionStartupResult,
        *,
        json_mode: bool = False,
        system_bwrap_warning: str | None = None,
    ) -> tuple[ExecLoopAction, ...]:
        return exec_session_startup_processor_actions(
            self.startup.session_config,
            self.startup.run_plan,
            startup_result,
            json_mode=json_mode,
            system_bwrap_warning=system_bwrap_warning,
        )

    def exec_loop_step(
        self,
        startup_result: ExecSessionStartupResult,
        event: JsonValue,
        *,
        processor_status: JsonValue = "running",
        thread_read_response: JsonValue | None = None,
    ) -> ExecLoopStepResult:
        return exec_loop_step(
            event,
            startup_result.loop_state,
            request_ids=self.request_ids,
            processor_status=processor_status,
            thread_read_response=thread_read_response,
        )

    def exec_loop_actions(
        self,
        startup_result: ExecSessionStartupResult,
        event: JsonValue,
        *,
        processor_status: JsonValue = "running",
        thread_read_response: JsonValue | None = None,
    ) -> tuple[ExecLoopAction, ...]:
        return exec_loop_actions_from_step(
            self.exec_loop_step(
                startup_result,
                event,
                processor_status=processor_status,
                thread_read_response=thread_read_response,
            )
        )

    def exec_loop_exchange(
        self,
        startup_result: ExecSessionStartupResult,
        event: JsonValue,
        *,
        processor_status: JsonValue = "running",
        thread_read_response: JsonValue | None = None,
    ) -> ExecRuntimeEventExchange:
        step = self.exec_loop_step(
            startup_result,
            event,
            processor_status=processor_status,
            thread_read_response=thread_read_response,
        )
        return ExecRuntimeEventExchange(
            step=step,
            actions=exec_loop_actions_from_step(step),
        )

    def exec_loop_actions_with_thread_read_response(
        self,
        startup_result: ExecSessionStartupResult,
        event: JsonValue,
        thread_read_response: JsonValue,
        *,
        processor_status: JsonValue = "running",
    ) -> tuple[ExecLoopAction, ...]:
        return self.exec_loop_actions(
            startup_result,
            event,
            processor_status=processor_status,
            thread_read_response=thread_read_response,
        )

    def exec_loop_shutdown_actions(
        self,
        startup_result: ExecSessionStartupResult,
        event: JsonValue,
        *,
        thread_read_response: JsonValue | None = None,
    ) -> tuple[ExecLoopAction, ...]:
        return self.exec_loop_actions(
            startup_result,
            event,
            processor_status="initiate_shutdown",
            thread_read_response=thread_read_response,
        )

    def exec_loop_shutdown_exchange(
        self,
        startup_result: ExecSessionStartupResult,
        event: JsonValue,
        *,
        thread_read_response: JsonValue | None = None,
    ) -> ExecRuntimeEventExchange:
        return self.exec_loop_exchange(
            startup_result,
            event,
            processor_status="initiate_shutdown",
            thread_read_response=thread_read_response,
        )


def exec_sandbox_mode_from_cli(cli: ExecCli) -> SandboxMode | None:
    """Resolve the upstream sandbox-mode precedence for ``codex exec``."""

    return cli.effective_sandbox_mode()


def resolve_oss_provider(explicit_provider: str | None, config_toml: Mapping[str, JsonValue] | None) -> str | None:
    """Return the explicit OSS provider or the global ``oss_provider`` value."""

    if explicit_provider is not None:
        return explicit_provider
    if config_toml is None:
        return None
    provider = config_toml.get("oss_provider")
    return provider if isinstance(provider, str) and provider else None


def get_default_model_for_oss_provider(provider_id: str) -> str | None:
    """Mirror upstream OSS default model lookup."""

    if provider_id == LMSTUDIO_OSS_PROVIDER_ID:
        return LMSTUDIO_DEFAULT_OSS_MODEL
    if provider_id == OLLAMA_OSS_PROVIDER_ID:
        return OLLAMA_DEFAULT_OSS_MODEL
    return None


def exec_model_provider_override(cli: ExecCli, config_toml: Mapping[str, JsonValue] | None = None) -> str | None:
    if cli.local_provider is not None:
        return cli.local_provider
    if cli.oss:
        provider = resolve_oss_provider(cli.local_provider, config_toml)
        if provider is None:
            raise ExecConfigPlanError(NO_DEFAULT_OSS_PROVIDER_MESSAGE)
        return provider
    if config_toml is None:
        return None
    provider = config_toml.get("model_provider")
    return provider if isinstance(provider, str) and provider else None


def exec_model_override(
    cli: ExecCli,
    model_provider: str | None = None,
    config_toml: Mapping[str, JsonValue] | None = None,
) -> str | None:
    if cli.model is not None:
        return cli.model
    if cli.oss and model_provider is not None:
        return get_default_model_for_oss_provider(model_provider)
    if config_toml is not None:
        model = config_toml.get("model")
        if isinstance(model, str) and model:
            return model
    return None


def exec_harness_overrides_from_cli(
    cli: ExecCli,
    config_toml: Mapping[str, JsonValue] | None = None,
) -> ExecHarnessOverrides:
    """Build the harness override slice that upstream passes to ``ConfigBuilder``."""

    model_provider = exec_model_provider_override(cli, config_toml)
    return ExecHarnessOverrides(
        model=exec_model_override(cli, model_provider, config_toml),
        approval_policy=cli.approval_policy or AskForApproval.NEVER,
        sandbox_mode=exec_sandbox_mode_from_cli(cli),
        cwd=Path(cli.cwd) if cli.cwd is not None else None,
        model_provider=model_provider,
        model_reasoning_effort=_optional_str((config_toml or {}).get("model_reasoning_effort")),
        model_reasoning_summary=_optional_str((config_toml or {}).get("model_reasoning_summary")),
        service_tier=_optional_str((config_toml or {}).get("service_tier")),
        show_raw_agent_reasoning=True if cli.oss else None,
        ephemeral=True if cli.ephemeral else None,
        bypass_hook_trust=True if cli.dangerously_bypass_hook_trust else None,
        additional_writable_roots=tuple(Path(path) for path in cli.add_dir),
    )


def resolve_exec_config_cwd(cli: ExecCli, current_dir: str | Path | None = None) -> Path:
    """Resolve the cwd used to load config, matching upstream's existing path check."""

    if cli.cwd is None:
        return Path.cwd() if current_dir is None else Path(current_dir)
    candidate = Path(cli.cwd)
    if not candidate.is_absolute() and current_dir is not None:
        candidate = Path(current_dir) / candidate
    try:
        return candidate.resolve(strict=True)
    except OSError as exc:
        raise ExecConfigPlanError(f"Failed to resolve -C/--cd path {cli.cwd}: {exc}") from exc


def build_exec_config_bootstrap_plan(
    cli: ExecCli,
    *,
    config_toml: Mapping[str, JsonValue] | None = None,
    current_dir: str | Path | None = None,
) -> ExecConfigBootstrapPlan:
    """Plan the config inputs that precede full app-server startup."""

    config_cwd = resolve_exec_config_cwd(cli, current_dir)
    cli_overrides = tuple(cli.cli_config_overrides().parse_overrides())
    effective_config = _exec_config_with_overrides(config_toml, cli_overrides)
    features = _features_from_exec_config(effective_config)
    warnings: list[str] = []
    user_instructions, instruction_sources = _resolve_exec_user_instructions(
        config_cwd,
        effective_config,
        warnings,
    )
    return ExecConfigBootstrapPlan(
        config_cwd=config_cwd,
        strict_config=cli.strict_config,
        ignore_user_config=cli.ignore_user_config,
        ignore_rules=cli.ignore_rules,
        cli_overrides=cli_overrides,
        harness_overrides=exec_harness_overrides_from_cli(cli, effective_config),
        user_instructions=user_instructions,
        instruction_sources=instruction_sources,
        startup_warnings=tuple(warnings),
        mcp_servers=effective_config.get("mcp_servers") if isinstance(effective_config.get("mcp_servers"), Mapping) else {},
        allow_login_shell=_allow_login_shell_from_config(effective_config),
        features=features,
        exec_permission_approvals_enabled=features.enabled(Feature.EXEC_PERMISSION_APPROVALS),
        request_permissions_tool_enabled=features.enabled(Feature.REQUEST_PERMISSIONS_TOOL),
        tui_status_line=_tui_config_str_tuple(effective_config, "status_line"),
        tui_status_line_use_colors=_tui_config_bool(effective_config, "status_line_use_colors", True),
        tui_terminal_title=_tui_config_str_tuple(effective_config, "terminal_title"),
    )


def exec_session_config_from_bootstrap_plan(plan: ExecConfigBootstrapPlan) -> ExecSessionConfig:
    """Project the exec bootstrap plan into the session config shape used by thread requests."""

    harness = plan.harness_overrides
    cwd = plan.config_cwd
    return ExecSessionConfig(
        model=harness.model,
        model_provider_id=harness.model_provider,
        cwd=cwd,
        workspace_roots=(cwd, *harness.additional_writable_roots),
        user_instructions=plan.user_instructions,
        instruction_sources=plan.instruction_sources,
        startup_warnings=plan.startup_warnings,
        mcp_servers=plan.mcp_servers,
        approval_policy=harness.approval_policy or AskForApproval.NEVER,
        permission_profile=_permission_profile_from_sandbox_mode(
            harness.sandbox_mode,
            (cwd, *harness.additional_writable_roots),
        ),
        ephemeral=bool(harness.ephemeral),
        reasoning_effort=harness.model_reasoning_effort,
        model_reasoning_summary=harness.model_reasoning_summary,
        service_tier=harness.service_tier,
        show_raw_agent_reasoning=bool(harness.show_raw_agent_reasoning),
        tui_status_line=plan.tui_status_line,
        tui_status_line_use_colors=plan.tui_status_line_use_colors,
        tui_terminal_title=plan.tui_terminal_title,
        allow_login_shell=plan.allow_login_shell,
        features=plan.features,
        exec_permission_approvals_enabled=plan.exec_permission_approvals_enabled,
        request_permissions_tool_enabled=plan.request_permissions_tool_enabled,
    )


def _exec_config_with_overrides(
    config_toml: Mapping[str, JsonValue] | None,
    cli_overrides: tuple[ConfigOverride, ...],
) -> dict[str, JsonValue]:
    config: dict[str, JsonValue] = copy.deepcopy(dict(config_toml or {}))
    for override in cli_overrides:
        apply_single_override(config, override.path, override.value)
    return config


def _tui_config_mapping(config_toml: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    tui = config_toml.get("tui")
    if isinstance(tui, Mapping):
        return tui
    return {}


def _tui_config_str_tuple(config_toml: Mapping[str, JsonValue], key: str) -> tuple[str, ...] | None:
    value = _tui_config_mapping(config_toml).get(key)
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return None
    return tuple(str(item) for item in value)


def _tui_config_bool(config_toml: Mapping[str, JsonValue], key: str, default: bool) -> bool:
    value = _tui_config_mapping(config_toml).get(key)
    return value if isinstance(value, bool) else default


def _allow_login_shell_from_config(config_toml: Mapping[str, JsonValue]) -> bool:
    value = config_toml.get("allow_login_shell")
    return value if isinstance(value, bool) else True


def _features_from_exec_config(config_toml: Mapping[str, JsonValue]) -> Features:
    features_value = config_toml.get("features")
    features_toml = FeaturesToml.from_mapping(features_value) if isinstance(features_value, Mapping) else None
    legacy_unified_exec = config_toml.get("experimental_use_unified_exec_tool")
    return Features.from_sources(
        FeatureConfigSource(
            features=features_toml,
            experimental_use_unified_exec_tool=legacy_unified_exec if isinstance(legacy_unified_exec, bool) else None,
        ),
        FeatureConfigSource(),
        FeatureOverrides(),
    )


def exec_trusted_directory_check(
    cli: ExecCli,
    cwd: str | Path,
    *,
    git_repo_root: str | Path | None = None,
) -> ExecTrustedDirectoryCheckPlan:
    """Plan Rust's pre-client git trusted-directory check."""

    cwd_path = Path(cwd)
    if cli.skip_git_repo_check:
        return ExecTrustedDirectoryCheckPlan(
            allowed=True,
            cwd=cwd_path,
            skipped_by_flag=True,
        )
    if cli.dangerously_bypass_approvals_and_sandbox:
        return ExecTrustedDirectoryCheckPlan(
            allowed=True,
            cwd=cwd_path,
            skipped_by_dangerous_bypass=True,
        )

    repo_root = Path(git_repo_root) if git_repo_root is not None else get_git_repo_root(cwd_path)
    if repo_root is None:
        return ExecTrustedDirectoryCheckPlan(
            allowed=False,
            cwd=cwd_path,
            message=EXEC_UNTRUSTED_DIRECTORY_MESSAGE,
        )
    return ExecTrustedDirectoryCheckPlan(
        allowed=True,
        cwd=cwd_path,
        git_repo_root=repo_root,
    )


def ensure_exec_trusted_directory(check: ExecTrustedDirectoryCheckPlan) -> None:
    """Raise the Rust-facing startup error when the trusted-directory gate fails."""

    if check.allowed:
        return
    raise ExecConfigPlanError(check.message or EXEC_UNTRUSTED_DIRECTORY_MESSAGE)


def build_exec_runtime_startup_plan(
    cli: ExecCli,
    *,
    config_toml: Mapping[str, JsonValue] | None = None,
    current_dir: str | Path | None = None,
    stdin: bytes | str | BinaryIO | TextIO | None = None,
    stdin_is_terminal: bool | None = None,
    stderr: TextIO | None = None,
) -> ExecRuntimeStartupPlan:
    """Compose the pre-agent startup state for ``codex exec``."""

    bootstrap_plan = build_exec_config_bootstrap_plan(
        cli,
        config_toml=config_toml,
        current_dir=current_dir,
    )
    return ExecRuntimeStartupPlan(
        bootstrap_plan=bootstrap_plan,
        session_config=exec_session_config_from_bootstrap_plan(bootstrap_plan),
        run_plan=prepare_exec_run_plan(
            cli,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
            stderr=stderr,
        ),
        trusted_directory_check=exec_trusted_directory_check(
            cli,
            bootstrap_plan.config_cwd,
        ),
    )


def build_exec_run_main_plan(
    cli: ExecCli,
    *,
    arg0_paths: Arg0DispatchPaths | None = None,
    config_toml: Mapping[str, JsonValue] | None = None,
    current_dir: str | Path | None = None,
    stdin: bytes | str | BinaryIO | TextIO | None = None,
    stdin_is_terminal: bool | None = None,
    stderr: TextIO | None = None,
    client_version: str = "0",
) -> ExecRunMainPlan:
    """Compose the testable startup choices owned by Rust ``run_main``."""

    paths = arg0_paths if arg0_paths is not None else Arg0DispatchPaths()
    startup = build_exec_runtime_startup_plan(
        cli,
        config_toml=config_toml,
        current_dir=current_dir,
        stdin=stdin,
        stdin_is_terminal=stdin_is_terminal,
        stderr=stderr,
    )
    environment_source = "env" if startup.bootstrap_plan.ignore_user_config else "codex_home"
    local_runtime_paths = ExecServerRuntimePaths.from_optional_paths(
        paths.codex_self_exe,
        paths.codex_linux_sandbox_exe,
    )
    environment_manager = EnvironmentManager(
        {
            "source": environment_source,
            "local_runtime_paths": local_runtime_paths.to_mapping(),
        }
    )
    state_db = StateDbHandle({})
    start_args = InProcessClientStartArgs(
        arg0_paths=paths,
        config=startup.session_config,
        cli_overrides=[(override.path, override.value) for override in startup.bootstrap_plan.cli_overrides],
        loader_overrides={
            "ignore_user_config": startup.bootstrap_plan.ignore_user_config,
            "ignore_rules": startup.bootstrap_plan.ignore_rules,
        },
        strict_config=startup.bootstrap_plan.strict_config,
        cloud_requirements=None,
        feedback=None,
        log_db=None,
        state_db=state_db,
        environment_manager=environment_manager,
        config_warnings=[
            {"summary": warning, "details": None, "path": None, "range": None}
            for warning in startup.session_config.startup_warnings
        ],
        session_source="exec",
        enable_codex_api_key_env=True,
        client_name="codex_exec",
        client_version=client_version,
        experimental_api=True,
        opt_out_notification_methods=[],
        channel_capacity=DEFAULT_IN_PROCESS_CHANNEL_CAPACITY,
    )
    return ExecRunMainPlan(
        startup=startup,
        processor_kind="json" if cli.json else "human",
        stderr_with_ansi=cli.color.value != "never",
        local_runtime_paths=local_runtime_paths,
        state_db=state_db,
        environment_manager_source=environment_source,
        in_process_start_args=start_args,
    )


def build_exec_otel_provider(
    config: JsonValue,
    service_version: str,
    service_name_override: str | None = None,
) -> OtelProvider | None:
    """Build the exec OTEL provider with Rust's exec analytics default."""

    return build_otel_provider(
        config,
        service_version,
        service_name_override,
        DEFAULT_ANALYTICS_ENABLED,
    )


def build_exec_runtime_request_sequence(
    cli: ExecCli,
    *,
    config_toml: Mapping[str, JsonValue] | None = None,
    current_dir: str | Path | None = None,
    stdin: bytes | str | BinaryIO | TextIO | None = None,
    stdin_is_terminal: bool | None = None,
    stderr: TextIO | None = None,
    initial_request_id: int = 1,
    resume_args: JsonValue | None = None,
    resolved_thread_id: str | None = None,
) -> ExecRuntimeRequestSequence:
    """Build the pre-network request sequence for ``codex exec`` startup."""

    startup = build_exec_runtime_startup_plan(
        cli,
        config_toml=config_toml,
        current_dir=current_dir,
        stdin=stdin,
        stdin_is_terminal=stdin_is_terminal,
        stderr=stderr,
    )
    request_ids = RequestIdSequencer(initial_request_id)
    bootstrap_request = thread_bootstrap_request_from_startup_plan(
        startup,
        request_ids.next(),
        resume_args=resume_args,
        resolved_thread_id=resolved_thread_id,
    )
    return ExecRuntimeRequestSequence(
        startup=startup,
        request_ids=request_ids,
        bootstrap_request=bootstrap_request,
    )


def thread_bootstrap_request_from_startup_plan(
    startup: ExecRuntimeStartupPlan,
    request_id: str | int,
    *,
    resume_args: JsonValue | None = None,
    resolved_thread_id: str | None = None,
) -> ThreadBootstrapRequest:
    """Build the thread bootstrap request for a prepared exec startup plan."""

    return thread_bootstrap_request(
        request_id,
        startup.session_config,
        resume_args=resume_args,
        resolved_thread_id=resolved_thread_id,
    )


def initial_operation_request_from_startup_plan(
    startup: ExecRuntimeStartupPlan,
    request_id: str | int,
    thread_id: str,
) -> InitialOperationRequest:
    """Build the initial operation request for a prepared exec startup plan."""

    return initial_operation_request_from_plan(
        request_id,
        startup.session_config,
        thread_id,
        startup.run_plan,
    )


def next_initial_operation_request_from_startup_plan(
    startup: ExecRuntimeStartupPlan,
    request_ids: RequestIdSequencer,
    bootstrap: ThreadBootstrapResult,
) -> InitialOperationRequest:
    """Build the next initial operation request after thread bootstrap completes."""

    return next_initial_operation_request(
        request_ids,
        startup.session_config,
        bootstrap,
        startup.run_plan,
    )


def exec_session_startup_result_from_startup_plan(
    startup: ExecRuntimeStartupPlan,
    bootstrap: ThreadBootstrapResult,
    initial_operation: InitialOperationResult,
) -> ExecSessionStartupResult:
    """Build the final exec session startup result after the initial operation completes."""

    return exec_session_startup_result(
        startup.session_config,
        bootstrap,
        initial_operation,
    )


def exec_session_startup_result_from_responses(
    startup: ExecRuntimeStartupPlan,
    bootstrap: ThreadBootstrapResult,
    *,
    initial_operation_method: str,
    initial_operation_response: JsonValue,
) -> ExecSessionStartupResult:
    """Parse an initial operation response and build the exec session startup result."""

    return exec_session_startup_result_from_startup_plan(
        startup,
        bootstrap,
        initial_operation_result_from_response(initial_operation_method, initial_operation_response),
    )


def _exec_session_config_to_mapping(config: ExecSessionConfig) -> dict[str, JsonValue]:
    return {
        "model": config.model,
        "modelProviderId": config.model_provider_id,
        "cwd": str(config.cwd),
        "workspaceRoots": [str(root) for root in config.workspace_roots],
        "userInstructions": config.user_instructions,
        "instructionSources": [str(path) for path in config.instruction_sources],
        "startupWarnings": list(config.startup_warnings),
        "approvalPolicy": _enum_value(config.approval_policy),
        "permissionProfile": config.permission_profile.to_mapping(),
        "ephemeral": config.ephemeral,
        "reasoningEffort": config.reasoning_effort,
        "serviceTier": config.service_tier,
        "hideAgentReasoning": config.hide_agent_reasoning,
        "showRawAgentReasoning": config.show_raw_agent_reasoning,
        "tuiStatusLine": list(config.tui_status_line) if config.tui_status_line is not None else None,
        "tuiStatusLineUseColors": config.tui_status_line_use_colors,
        "tuiTerminalTitle": list(config.tui_terminal_title) if config.tui_terminal_title is not None else None,
        "allowLoginShell": config.allow_login_shell,
        "execPermissionApprovalsEnabled": config.exec_permission_approvals_enabled,
        "requestPermissionsToolEnabled": config.request_permissions_tool_enabled,
    }


def _permission_profile_from_sandbox_mode(
    sandbox_mode: SandboxMode | None,
    workspace_roots: tuple[Path, ...],
) -> PermissionProfile:
    if sandbox_mode is SandboxMode.DANGER_FULL_ACCESS:
        return PermissionProfile.disabled()
    if sandbox_mode is SandboxMode.WORKSPACE_WRITE:
        return PermissionProfile.workspace_write(workspace_roots)
    return PermissionProfile.read_only()


def _enum_value(value: Enum | GranularApprovalConfig | None) -> JsonValue | None:
    if isinstance(value, GranularApprovalConfig):
        return {"granular": value.to_mapping()}
    return value.value if isinstance(value, Enum) else None


def _resolve_exec_user_instructions(
    cwd: Path,
    config_toml: Mapping[str, JsonValue] | None,
    warnings: list[str],
) -> tuple[str | None, tuple[Path, ...]]:
    config = config_toml or {}
    codex_home = _maybe_codex_home()
    manager = AgentsMdManager(
        AgentsMdConfig(
            cwd=cwd,
            codex_home=codex_home,
            user_instructions=_optional_str(config.get("user_instructions")),
            project_doc_max_bytes=_project_doc_max_bytes(config.get("project_doc_max_bytes")),
            project_doc_fallback_filenames=_string_tuple(config.get("project_doc_fallback_filenames")),
            project_root_markers=_optional_string_tuple(config.get("project_root_markers")),
            child_agents_md=_bool_value(config.get("child_agents_md"), False),
        )
    )
    return manager.user_instructions(warnings), tuple(manager.instruction_sources())


def _maybe_codex_home() -> Path | None:
    try:
        return find_codex_home()
    except (FileNotFoundError, NotADirectoryError, OSError):
        return None


def _optional_str(value: JsonValue) -> str | None:
    return value if isinstance(value, str) and value else None


def _project_doc_max_bytes(value: JsonValue) -> int:
    if isinstance(value, bool):
        return DEFAULT_PROJECT_DOC_MAX_BYTES
    if isinstance(value, int) and value >= 0:
        return value
    return DEFAULT_PROJECT_DOC_MAX_BYTES


def _string_tuple(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _optional_string_tuple(value: JsonValue) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _string_tuple(value)


def _bool_value(value: JsonValue, default: bool) -> bool:
    return value if isinstance(value, bool) else default


__all__ = [
    "DEFAULT_ANALYTICS_ENABLED",
    "EXEC_DEFAULT_LOG_FILTER",
    "EXEC_UNTRUSTED_DIRECTORY_MESSAGE",
    "ExecConfigBootstrapPlan",
    "ExecConfigPlanError",
    "ExecHarnessOverrides",
    "ExecRuntimeActionSummary",
    "ExecRuntimeCliCompletion",
    "ExecRuntimeEventExchange",
    "ExecRuntimeEventInput",
    "ExecRuntimeFinalMessageOutputPlan",
    "apply_exec_runtime_final_message_output_plan",
    "ExecRuntimeInitialRequestPlan",
    "ExecRuntimeRequestSequence",
    "ExecRuntimeRunnerResult",
    "ExecRuntimeRunnerTranscript",
    "ExecRuntimeStartupExchange",
    "ExecRuntimeStartupPlan",
    "ExecRunMainPlan",
    "ExecTrustedDirectoryCheckPlan",
    "LMSTUDIO_DEFAULT_OSS_MODEL",
    "LMSTUDIO_OSS_PROVIDER_ID",
    "NO_DEFAULT_OSS_PROVIDER_MESSAGE",
    "OLLAMA_DEFAULT_OSS_MODEL",
    "OLLAMA_OSS_PROVIDER_ID",
    "UPSTREAM_EXEC_RUN_MAIN",
    "build_exec_config_bootstrap_plan",
    "build_exec_otel_provider",
    "build_exec_run_main_plan",
    "build_exec_runtime_request_sequence",
    "build_exec_runtime_startup_plan",
    "exec_runtime_action_summary",
    "exec_runtime_runner_result",
    "exec_runtime_runner_transcript",
    "exec_session_config_from_bootstrap_plan",
    "ensure_exec_trusted_directory",
    "exec_trusted_directory_check",
    "exec_session_startup_result_from_responses",
    "exec_session_startup_result_from_startup_plan",
    "initial_operation_request_from_startup_plan",
    "next_initial_operation_request_from_startup_plan",
    "thread_bootstrap_request_from_startup_plan",
    "exec_harness_overrides_from_cli",
    "exec_model_override",
    "exec_model_provider_override",
    "exec_sandbox_mode_from_cli",
    "get_default_model_for_oss_provider",
    "resolve_exec_config_cwd",
    "resolve_oss_provider",
]
