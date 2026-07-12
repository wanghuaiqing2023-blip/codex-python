from pathlib import Path

from pycodex.exec.local_runtime import (
    local_http_apply_patch_approval_keys,
    local_http_apply_patch_approval_decision_allows_apply,
    local_http_apply_patch_request_approval,
)
from pycodex.exec.session import ExecSessionConfig
from pycodex.protocol import AskForApproval, ReviewDecision
from pycodex.protocol.approvals import FileChange


def test_local_apply_patch_routes_approval_through_interactive_callback() -> None:
    # Fixed Rust commit 1c7832f, tools::runtimes::apply_patch:
    # a non-preapproved patch asks the session for a ReviewDecision before
    # applying the verified changes.
    calls: list[tuple] = []

    def callback(call_id, changes, cwd, reason, grant_root):
        calls.append((call_id, changes, cwd, reason, grant_root))
        return ReviewDecision.approved()

    config = ExecSessionConfig(
        model="gpt-test",
        model_provider_id="openai",
        cwd=Path("C:/repo"),
        approval_policy=AskForApproval.ON_REQUEST,
        patch_approval_callback=callback,
    )
    changes = {Path("hello.txt"): FileChange.add("hello\n")}

    decision = local_http_apply_patch_request_approval(
        config,
        call_id="patch-1",
        changes=changes,
        cwd=Path("C:/repo"),
    )

    assert decision == ReviewDecision.approved()
    assert local_http_apply_patch_approval_decision_allows_apply(decision) is True
    assert calls == [("patch-1", changes, Path("C:/repo"), None, None)]


def test_local_apply_patch_without_callback_remains_unapproved() -> None:
    config = ExecSessionConfig(
        model="gpt-test",
        model_provider_id="openai",
        cwd=Path("C:/repo"),
        approval_policy=AskForApproval.ON_REQUEST,
    )

    decision = local_http_apply_patch_request_approval(
        config,
        call_id="patch-1",
        changes={Path("hello.txt"): FileChange.add("hello\n")},
        cwd=Path("C:/repo"),
    )

    assert decision is None
    assert local_http_apply_patch_approval_decision_allows_apply(decision) is False


def test_local_apply_patch_approval_keys_are_file_scoped_in_local_environment() -> None:
    # Fixed Rust commit 1c7832f:
    # tools::runtimes::apply_patch::approval_keys includes environment id and
    # one absolute key per changed path so subsets can reuse session approval.
    keys = local_http_apply_patch_approval_keys(
        {
            Path("hello.txt"): FileChange.add("hello\n"),
            Path("nested/world.txt"): FileChange.add("world\n"),
        },
        Path("C:/repo"),
    )

    assert [key.environment_id for key in keys] == ["local", "local"]
    assert [key.path for key in keys] == [
        Path("C:/repo/hello.txt").resolve(),
        Path("C:/repo/nested/world.txt").resolve(),
    ]
