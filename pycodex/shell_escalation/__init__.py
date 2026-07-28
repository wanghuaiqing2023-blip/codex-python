"""Public re-exports for ``codex-shell-escalation``."""

from pycodex.protocol.approvals import (
    EscalationPermissions,
    ResolvedPermissionProfile,
)

from .unix import (
    ESCALATE_SOCKET_ENV_VAR,
    EscalateAction,
    EscalateServer,
    EscalationDecision,
    EscalationExecution,
    EscalationPolicy,
    EscalationSession,
    ExecParams,
    ExecResult,
    PreparedExec,
    ShellCommandExecutor,
    Stopwatch,
    main_execve_wrapper,
    run_shell_escalation_execve_wrapper,
)

__all__ = [
    "ESCALATE_SOCKET_ENV_VAR",
    "EscalateAction",
    "EscalateServer",
    "EscalationDecision",
    "EscalationExecution",
    "EscalationPermissions",
    "EscalationPolicy",
    "EscalationSession",
    "ExecParams",
    "ExecResult",
    "PreparedExec",
    "ResolvedPermissionProfile",
    "ShellCommandExecutor",
    "Stopwatch",
    "main_execve_wrapper",
    "run_shell_escalation_execve_wrapper",
]
