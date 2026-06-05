"""Python port entry point for Codex sandboxing.

Upstream Rust implementation for permissions and sandbox behavior lives in
``codex-rs/sandboxing``.  The currently implemented Python surface lives in
``pycodex.core.tools.sandboxing`` and ``pycodex.protocol``; this module
re-exports the implemented pieces under the canonical top-level import path
``pycodex.sandboxing``.
"""

from __future__ import annotations

from pycodex.core.tools import sandboxing as tool_sandboxing
from pycodex.protocol import (
    AskForApproval,
    ExecPolicyAmendment,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    NetworkPermissions,
    ReviewDecision,
    SandboxPermissions,
)

from pycodex.core.tools.sandboxing import (
    ApprovalStore,
    ExecApprovalRequirement,
    PermissionRequestPayload,
    SandboxOverride,
    default_exec_approval_requirement,
    managed_network_for_sandbox_permissions,
    sandbox_override_for_first_attempt,
    with_cached_approval,
)

__all__ = [
    "ApprovalStore",
    "ExecApprovalRequirement",
    "PermissionRequestPayload",
    "SandboxOverride",
    "ReviewDecision",
    "SandboxPermissions",
    "NetworkPermissions",
    "FileSystemSandboxKind",
    "FileSystemSandboxPolicy",
    "GranularApprovalConfig",
    "AskForApproval",
    "ExecPolicyAmendment",
    "default_exec_approval_requirement",
    "managed_network_for_sandbox_permissions",
    "sandbox_override_for_first_attempt",
    "with_cached_approval",
    "tool_sandboxing",
]
