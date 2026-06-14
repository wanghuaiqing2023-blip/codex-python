
"""Parity tests for Rust core/tests/suite/permissions_messages.rs.

The Rust suite observes the developer messages sent to the Responses API and
counts ``<permissions instructions>`` fragments across normal turns, settings
updates, resume, fork, and writable-root rendering.  These Python tests keep the
same user-visible contract at the context/update boundary without reproducing
Rust's mock HTTP server harness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.context.permissions_instructions import PermissionsInstructions
from pycodex.core.context_manager.updates import build_permissions_update_item
from pycodex.protocol import ApprovalsReviewer, AskForApproval, NetworkSandboxPolicy, PermissionProfile


@dataclass(frozen=True)
class _Context:
    permission_profile: PermissionProfile = field(default_factory=PermissionProfile.disabled)
    approval_policy: AskForApproval = AskForApproval.ON_REQUEST
    cwd: Path = Path("C:/workspace")
    include_permissions_instructions: bool = True

    @property
    def config(self) -> SimpleNamespace:
        return SimpleNamespace(
            include_permissions_instructions=self.include_permissions_instructions,
            approvals_reviewer=ApprovalsReviewer.USER,
        )

    @property
    def features(self) -> set[object]:
        return set()


def _render_permissions(context: _Context) -> str | None:
    if not context.include_permissions_instructions:
        return None
    return PermissionsInstructions.from_permission_profile(
        context.permission_profile,
        context.approval_policy,
        ApprovalsReviewer.USER,
        None,
        context.cwd,
    ).render()


class _PermissionsMessageLedger:
    def __init__(self, context: _Context, messages: list[str] | None = None) -> None:
        self.context = context
        self.messages = list(messages or [])
        initial = _render_permissions(context)
        if initial is not None and not self.messages:
            self.messages.append(initial)

    def request_permissions_texts(self) -> list[str]:
        return list(self.messages)

    def apply_context(self, next_context: _Context) -> None:
        update = build_permissions_update_item(self.context, next_context)
        self.context = next_context
        if update is not None:
            self.messages.append(update)

    def resume(self, next_context: _Context | None = None) -> "_PermissionsMessageLedger":
        resumed_context = next_context or self.context
        resumed = _PermissionsMessageLedger.__new__(_PermissionsMessageLedger)
        resumed.context = resumed_context
        resumed.messages = list(self.messages)
        current = _render_permissions(resumed_context)
        if current is not None:
            resumed.messages.append(current)
        return resumed


def _permission_texts_for_policy(policy: AskForApproval) -> list[str]:
    return _PermissionsMessageLedger(_Context(approval_policy=policy)).request_permissions_texts()


def test_permissions_message_sent_once_on_start() -> None:
    """Rust test: permissions_message_sent_once_on_start."""

    permissions = _permission_texts_for_policy(AskForApproval.ON_REQUEST)

    assert len(permissions) == 1
    assert "<permissions instructions>" in permissions[0]
    assert "How to request escalation" in permissions[0]


def test_permissions_message_added_on_override_change() -> None:
    """Rust test: permissions_message_added_on_override_change."""

    ledger = _PermissionsMessageLedger(_Context(approval_policy=AskForApproval.ON_REQUEST))
    ledger.apply_context(_Context(approval_policy=AskForApproval.NEVER))
    permissions = ledger.request_permissions_texts()

    assert len(permissions) == 2
    assert len(set(permissions)) == 2
    assert "How to request escalation" in permissions[0]
    assert "Approval policy is currently never" in permissions[1]


def test_permissions_message_not_added_when_no_change() -> None:
    """Rust test: permissions_message_not_added_when_no_change."""

    ledger = _PermissionsMessageLedger(_Context(approval_policy=AskForApproval.ON_REQUEST))
    first = ledger.request_permissions_texts()
    ledger.apply_context(_Context(approval_policy=AskForApproval.ON_REQUEST))
    second = ledger.request_permissions_texts()

    assert len(first) == 1
    assert len(second) == 1
    assert first == second


def test_permissions_message_omitted_when_disabled() -> None:
    """Rust test: permissions_message_omitted_when_disabled."""

    ledger = _PermissionsMessageLedger(
        _Context(approval_policy=AskForApproval.ON_REQUEST, include_permissions_instructions=False)
    )
    ledger.apply_context(_Context(approval_policy=AskForApproval.NEVER, include_permissions_instructions=False))

    assert ledger.request_permissions_texts() == []


def test_resume_replays_permissions_messages() -> None:
    """Rust test: resume_replays_permissions_messages."""

    initial = _PermissionsMessageLedger(_Context(approval_policy=AskForApproval.ON_REQUEST))
    initial.apply_context(_Context(approval_policy=AskForApproval.NEVER))

    resumed = initial.resume()
    permissions = resumed.request_permissions_texts()

    assert len(permissions) == 3
    assert len(set(permissions)) == 2
    assert permissions[-1] == permissions[1]


def test_resume_and_fork_append_permissions_messages() -> None:
    """Rust test: resume_and_fork_append_permissions_messages."""

    initial = _PermissionsMessageLedger(_Context(approval_policy=AskForApproval.ON_REQUEST))
    initial.apply_context(_Context(approval_policy=AskForApproval.NEVER))
    base_permissions = initial.request_permissions_texts()

    next_context = _Context(approval_policy=AskForApproval.UNLESS_TRUSTED)
    resumed = initial.resume(next_context)
    forked = initial.resume(next_context)

    resume_permissions = resumed.request_permissions_texts()
    fork_permissions = forked.request_permissions_texts()

    assert len(base_permissions) == 2
    assert len(resume_permissions) == len(base_permissions) + 1
    assert resume_permissions[: len(base_permissions)] == base_permissions
    assert resume_permissions[-1] not in base_permissions
    assert fork_permissions == resume_permissions


def test_permissions_message_includes_writable_roots() -> None:
    """Rust test: permissions_message_includes_writable_roots."""

    cwd = Path("C:/workspace")
    writable_root = cwd / "extra"
    profile = PermissionProfile.workspace_write(
        (writable_root,),
        network=NetworkSandboxPolicy.RESTRICTED,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )

    rendered = PermissionsInstructions.from_permission_profile(
        profile,
        AskForApproval.ON_REQUEST,
        ApprovalsReviewer.USER,
        None,
        cwd,
    ).render()

    assert "<permissions instructions>" in rendered
    assert "`sandbox_mode` is `workspace-write`" in rendered
    assert "Network access is restricted." in rendered
    assert str(writable_root) in rendered
