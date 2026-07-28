"""Unix shell-escalation module re-exports."""

from pycodex.protocol.approvals import (
    EscalationPermissions,
    ResolvedPermissionProfile,
)

from .escalate_client import run_shell_escalation_execve_wrapper
from .escalate_protocol import (
    ESCALATE_SOCKET_ENV_VAR,
    EXEC_WRAPPER_ENV_VAR,
    EscalateAction,
    EscalateRequest,
    EscalateResponse,
    EscalationDecision,
    EscalationExecution,
    SuperExecMessage,
    SuperExecResult,
)
from .escalate_server import (
    EscalateServer,
    EscalationSession,
    ExecParams,
    ExecResult,
    PreparedExec,
    ShellCommandExecutor,
)
from .escalation_policy import EscalationPolicy
from .execve_wrapper import ExecveWrapperCli, main_execve_wrapper
from .socket import (
    AsyncDatagramSocket,
    AsyncSocket,
    LENGTH_PREFIX_SIZE,
    MAX_DATAGRAM_SIZE,
    MAX_FDS_PER_MESSAGE,
    encode_length,
)
from .stopwatch import CancellationToken, Stopwatch

__all__ = [
    "ESCALATE_SOCKET_ENV_VAR",
    "EXEC_WRAPPER_ENV_VAR",
    "AsyncDatagramSocket",
    "AsyncSocket",
    "CancellationToken",
    "EscalateAction",
    "EscalateRequest",
    "EscalateResponse",
    "EscalateServer",
    "EscalationDecision",
    "EscalationExecution",
    "EscalationPermissions",
    "EscalationPolicy",
    "EscalationSession",
    "ExecParams",
    "ExecResult",
    "ExecveWrapperCli",
    "LENGTH_PREFIX_SIZE",
    "MAX_DATAGRAM_SIZE",
    "MAX_FDS_PER_MESSAGE",
    "PreparedExec",
    "ResolvedPermissionProfile",
    "ShellCommandExecutor",
    "Stopwatch",
    "SuperExecMessage",
    "SuperExecResult",
    "encode_length",
    "main_execve_wrapper",
    "run_shell_escalation_execve_wrapper",
]
