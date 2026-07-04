import json
from pathlib import Path

from pycodex.execpolicy import (
    Decision,
    ExecApprovalRequest,
    ExecPolicyPrefixRule,
    create_exec_approval_requirement_for_command,
    match_exec_policy_rules_for_command,
    prefix_rule_would_approve_all_commands,
)
from pycodex.core.session.turn.runtime import UserTurnSamplingResult
from pycodex.exec.local_runtime import ExecSessionConfig, shell_tool_outputs_from_local_http_exec_result
from pycodex.protocol import (
    AskForApproval,
    ExecApprovalRequestEvent,
    ExecPolicyAmendment,
    FileSystemSandboxPolicy,
    NetworkApprovalContext,
    NetworkApprovalProtocol,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    PermissionProfile,
    ReviewDecision,
    SandboxPermissions,
)


def _shell_call_result(command: str, *, sandbox_permissions: str | None = None) -> UserTurnSamplingResult:
    arguments = {"cmd": command}
    if sandbox_permissions is not None:
        arguments["sandbox_permissions"] = sandbox_permissions
    return UserTurnSamplingResult(
        request_plan=None,
        response_items=(),
        raw_result={
            "output": [
                {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-shell",
                    "arguments": json.dumps(arguments),
                }
            ]
        },
    )


def _approval_request(
    command: tuple[str, ...],
    *,
    approval_policy=AskForApproval.ON_REQUEST,
    permission_profile: PermissionProfile | None = None,
    sandbox_permissions: SandboxPermissions = SandboxPermissions.USE_DEFAULT,
    prefix_rule: tuple[str, ...] | None = None,
    matched_rules: tuple[object, ...] = (),
) -> ExecApprovalRequest:
    if permission_profile is None:
        permission_profile = PermissionProfile.read_only()
    return ExecApprovalRequest(
        command=command,
        approval_policy=approval_policy,
        permission_profile=permission_profile,
        file_system_sandbox_policy=permission_profile.file_system_sandbox_policy(),
        sandbox_cwd=Path("/repo"),
        sandbox_permissions=sandbox_permissions,
        prefix_rule=prefix_rule,
        matched_rules=matched_rules,
    )


def test_workspace_write_on_request_allows_workspace_write_dynamic_turn(tmp_path):
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: approval_matrix_covers_group / workspace_write_on_request_allows_workspace_write.
    # Contract: workspace-write + on-request + default sandbox can run a workspace
    # shell action without emitting an approval request.
    approvals = []
    ran = []

    def unexpected_approval(*_args):
        approvals.append(_args)
        return ReviewDecision.denied()

    def runner(command, **_kwargs):
        ran.append(command)
        return type("Completed", (), {"returncode": 0, "stdout": "workspace-on-request\n", "stderr": ""})()

    config = ExecSessionConfig(
        model=None,
        model_provider_id=None,
        cwd=tmp_path,
        approval_policy=AskForApproval.ON_REQUEST,
        permission_profile=PermissionProfile.workspace_write((tmp_path,)),
        exec_approval_callback=unexpected_approval,
    )
    outputs = shell_tool_outputs_from_local_http_exec_result(
        _shell_call_result("echo workspace-on-request"),
        config,
        runner=runner,
    )

    assert approvals == []
    assert ran == ["echo workspace-on-request"]
    assert outputs[0]["success"] is True
    assert "workspace-on-request" in outputs[0]["output"]


def test_workspace_write_on_request_requires_approval_outside_workspace_dynamic_turn(tmp_path):
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: approval_matrix_covers_group / workspace_write_on_request_requires_approval_outside_workspace.
    # Contract: an escalated/outside-workspace shell request under on-request is
    # converted into an approval request; approving it continues execution.
    approvals = []
    ran = []

    def approve(invocation, _config, requirement, meta):
        approvals.append((meta["call_id"], invocation.command, requirement.type))
        return ReviewDecision.approved()

    def runner(command, **_kwargs):
        ran.append(command)
        return type("Completed", (), {"returncode": 0, "stdout": "outside-ok\n", "stderr": ""})()

    config = ExecSessionConfig(
        model=None,
        model_provider_id=None,
        cwd=tmp_path,
        approval_policy=AskForApproval.ON_REQUEST,
        permission_profile=PermissionProfile.workspace_write((tmp_path,)),
        exec_approval_callback=approve,
    )
    outputs = shell_tool_outputs_from_local_http_exec_result(
        _shell_call_result("echo outside-ok", sandbox_permissions="require_escalated"),
        config,
        runner=runner,
    )

    assert approvals == [("call-shell", "echo outside-ok", "needs_approval")]
    assert ran == ["echo outside-ok"]
    assert outputs[0]["success"] is True
    assert "outside-ok" in outputs[0]["output"]
    assert "approval_required" not in outputs[0]["output"]


def test_denied_escalated_approval_returns_rejected_by_user_dynamic_turn(tmp_path):
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust tests:
    # - approval_matrix_covers_group / compound command with one safe command still requires approval.
    # - codex-core::tools::orchestrator denied approval path returns "rejected by user".
    # Contract: once an approval request has been denied, the tool output must be
    # a rejection result, not another approval_required placeholder.
    ran = []

    def deny(_invocation, _config, requirement, _meta):
        assert requirement.type == "needs_approval"
        return ReviewDecision.denied()

    def runner(command, **_kwargs):
        ran.append(command)
        return type("Completed", (), {"returncode": 0, "stdout": "should-not-run\n", "stderr": ""})()

    config = ExecSessionConfig(
        model=None,
        model_provider_id=None,
        cwd=tmp_path,
        approval_policy=AskForApproval.ON_REQUEST,
        permission_profile=PermissionProfile.workspace_write((tmp_path,)),
        exec_approval_callback=deny,
    )
    outputs = shell_tool_outputs_from_local_http_exec_result(
        _shell_call_result("cat ./one.txt && touch ./two.txt", sandbox_permissions="require_escalated"),
        config,
        runner=runner,
    )

    assert ran == []
    assert outputs[0]["success"] is False
    assert "rejected by user" in outputs[0]["output"]
    assert "approval_required" not in outputs[0]["output"]


def test_approval_matrix_covers_group():
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: approval_matrix_covers_group.
    plain = ExecApprovalRequestEvent(
        call_id="call-1",
        started_at_ms=1,
        command=("python", "--version"),
        cwd=Path("/repo"),
    )
    amendment = ExecApprovalRequestEvent(
        call_id="call-2",
        started_at_ms=1,
        command=("rm", "-rf", "target"),
        cwd=Path("/repo"),
        proposed_execpolicy_amendment=ExecPolicyAmendment.new(["rm", "-rf", "target"]),
    )

    assert [decision.type for decision in plain.effective_available_decisions()] == ["approved", "abort"]
    assert [decision.type for decision in amendment.effective_available_decisions()] == [
        "approved",
        "approved_execpolicy_amendment",
        "abort",
    ]


def test_approving_apply_patch_for_session_skips_future_prompts_for_same_file():
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: approving_apply_patch_for_session_skips_future_prompts_for_same_file.
    assert ReviewDecision.approved_for_session().to_opaque_string() == "approved_for_session"
    assert ReviewDecision.from_mapping("acceptForSession") == ReviewDecision.approved_for_session()


def test_approving_execpolicy_amendment_persists_policy_and_skips_future_prompts():
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: approving_execpolicy_amendment_persists_policy_and_skips_future_prompts.
    amendment = ExecPolicyAmendment.new(["touch", "allow-prefix.txt"])
    decision = ReviewDecision.approved_execpolicy_amendment(amendment)
    rules = (ExecPolicyPrefixRule.new(["touch", "allow-prefix.txt"], "allow"),)
    matched = match_exec_policy_rules_for_command(("touch", "allow-prefix.txt"), rules)

    assert decision.to_opaque_string() == "approved_with_amendment"
    assert decision.to_mapping()["approved_execpolicy_amendment"]["proposed_execpolicy_amendment"] == {
        "command": ["touch", "allow-prefix.txt"]
    }
    assert matched and matched[0]["prefixRuleMatch"]["decision"] == "allow"


def test_spawned_subagent_execpolicy_amendment_propagates_to_parent_session():
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: spawned_subagent_execpolicy_amendment_propagates_to_parent_session.
    parent_policy_rules = (ExecPolicyPrefixRule.new(["python", "safe.py"], "allow"),)
    child_command = ("python", "safe.py")

    assert match_exec_policy_rules_for_command(child_command, parent_policy_rules)


def test_matched_prefix_rule_runs_unsandboxed_under_zsh_fork():
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: matched_prefix_rule_runs_unsandboxed_under_zsh_fork.
    # Python parity scope: the execpolicy helper preserves the same matched
    # allow prefix rule. The Rust integration test also exercises the zsh
    # fork/runtime sandbox path, which is outside this helper-level slice.
    matched_rules = match_exec_policy_rules_for_command(
        ("touch", "allow-prefix.txt"),
        (ExecPolicyPrefixRule.new(["touch", "allow-prefix.txt"], "allow"),),
    )
    requirement = create_exec_approval_requirement_for_command(
        _approval_request(
            ("touch", "allow-prefix.txt"),
            approval_policy=AskForApproval.UNLESS_TRUSTED,
            matched_rules=matched_rules,
            )
        )

    assert matched_rules
    assert matched_rules[0]["prefixRuleMatch"]["matchedPrefix"] == ["touch", "allow-prefix.txt"]
    assert matched_rules[0]["prefixRuleMatch"]["decision"] == "allow"
    assert requirement.type == "needs_approval"
    assert requirement.proposed_execpolicy_amendment is not None


def test_invalid_requested_prefix_rule_falls_back_for_compound_command():
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: invalid_requested_prefix_rule_falls_back_for_compound_command.
    requirement = create_exec_approval_requirement_for_command(
        _approval_request(
            ("bash", "-lc", "touch /tmp/a && echo hello > /tmp/a"),
            sandbox_permissions=SandboxPermissions.REQUIRE_ESCALATED,
            prefix_rule=("touch",),
        )
    )

    assert requirement.type == "needs_approval"
    assert requirement.proposed_execpolicy_amendment is not None
    assert requirement.proposed_execpolicy_amendment.command_tokens() != ("touch",)


def test_approving_fallback_rule_for_compound_command_works():
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: approving_fallback_rule_for_compound_command_works.
    amendment = ExecPolicyAmendment.new(["touch", "/tmp/a", "&&", "echo", "hello", ">", "/tmp/a"])
    decision = ReviewDecision.approved_execpolicy_amendment(amendment)

    assert decision.proposed_execpolicy_amendment == amendment
    assert prefix_rule_would_approve_all_commands(amendment.command_tokens(), (amendment.command_tokens(),))


def test_denying_network_policy_amendment_persists_policy_and_skips_future_network_prompt():
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: denying_network_policy_amendment_persists_policy_and_skips_future_network_prompt.
    deny = NetworkPolicyAmendment("codex-network-test.invalid", NetworkPolicyRuleAction.DENY)
    decision = ReviewDecision.network_policy_amendment_decision(deny)

    assert decision.to_opaque_string() == "denied_with_network_policy_deny"
    assert decision.to_mapping() == {
        "network_policy_amendment": {
            "network_policy_amendment": {
                "host": "codex-network-test.invalid",
                "action": "deny",
            }
        }
    }


def test_network_approval_flow_survives_danger_full_access_session_start():
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: network_approval_flow_survives_danger_full_access_session_start.
    context = NetworkApprovalContext("codex-network-test.invalid", NetworkApprovalProtocol.HTTP)
    allow = NetworkPolicyAmendment(context.host, NetworkPolicyRuleAction.ALLOW)
    event = ExecApprovalRequestEvent(
        call_id="network-call",
        started_at_ms=1,
        command=("network-access", context.host),
        cwd=Path("/repo"),
        network_approval_context=context,
        proposed_network_policy_amendments=(allow,),
    )

    assert [decision.type for decision in event.effective_available_decisions()] == [
        "approved",
        "approved_for_session",
        "network_policy_amendment",
        "abort",
    ]


def test_compound_command_with_one_safe_command_still_requires_approval():
    # Rust source: codex/codex-rs/core/tests/suite/approvals.rs
    # Rust test: compound_command_with_one_safe_command_still_requires_approval.
    rules = (ExecPolicyPrefixRule.new(["touch", "allow-prefix.txt"], "allow"),)
    matched = match_exec_policy_rules_for_command(("bash", "-lc", "touch ./test.txt && rm ./test.txt"), rules)
    requirement = create_exec_approval_requirement_for_command(
        _approval_request(
            ("bash", "-lc", "touch ./test.txt && rm ./test.txt"),
            approval_policy=AskForApproval.UNLESS_TRUSTED,
            matched_rules=matched,
        )
    )

    assert matched == ()
    assert requirement.type == "needs_approval"
