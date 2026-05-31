import unittest
from pathlib import Path

from pycodex.protocol import (
    AdditionalPermissionProfile,
    ApplyPatchApprovalRequestEvent,
    ElicitationAction,
    ElicitationRequest,
    ElicitationRequestEvent,
    EscalationPermissions,
    ExecApprovalRequestEvent,
    ExecPolicyAmendment,
    FileChange,
    GuardianAssessmentAction,
    GuardianAssessmentDecisionSource,
    GuardianAssessmentEvent,
    GuardianAssessmentOutcome,
    GuardianAssessmentStatus,
    GuardianCommandSource,
    GuardianRiskLevel,
    GuardianUserAuthorization,
    NetworkApprovalContext,
    NetworkApprovalProtocol,
    NetworkPermissions,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    PermissionGrantScope,
    PermissionProfile,
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsEvent,
    RequestPermissionsResponse,
    ResolvedPermissionProfile,
    ReviewDecision,
    command_execution_approval_decision_to_mapping,
    command_execution_request_approval_response,
    file_change_approval_decision_to_mapping,
    file_change_request_approval_response,
    permissions_request_approval_response,
)


class ProtocolApprovalsTests(unittest.TestCase):
    def test_exec_policy_amendment_keeps_command_prefix_tokens(self):
        amendment = ExecPolicyAmendment.new(["git", "status"])

        self.assertEqual(amendment.command, ("git", "status"))
        self.assertEqual(amendment.command_tokens(), ("git", "status"))

        with self.assertRaisesRegex(TypeError, "command must be a list of strings"):
            ExecPolicyAmendment.new("git status")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "command must be a list of strings"):
            ExecPolicyAmendment.new(["git", 123])  # type: ignore[list-item]

    def test_network_approval_protocol_accepts_upstream_aliases(self):
        self.assertIs(NetworkApprovalProtocol.parse("http"), NetworkApprovalProtocol.HTTP)
        self.assertIs(NetworkApprovalProtocol.parse("https_connect"), NetworkApprovalProtocol.HTTPS)
        self.assertIs(NetworkApprovalProtocol.parse("http-connect"), NetworkApprovalProtocol.HTTPS)
        with self.assertRaisesRegex(TypeError, "network approval protocol must be a string"):
            NetworkApprovalProtocol.parse(123)  # type: ignore[arg-type]

    def test_network_context_and_amendments_reject_non_rust_shapes(self):
        self.assertEqual(
            NetworkApprovalContext("api.example.com", "https").protocol,
            NetworkApprovalProtocol.HTTPS,
        )
        with self.assertRaisesRegex(TypeError, "host must be a string"):
            NetworkApprovalContext(123, NetworkApprovalProtocol.HTTPS)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "protocol must be a NetworkApprovalProtocol"):
            NetworkApprovalContext("api.example.com", object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "host must be a string"):
            NetworkPolicyAmendment(123, NetworkPolicyRuleAction.ALLOW)  # type: ignore[arg-type]
        self.assertIs(NetworkPolicyAmendment("api.example.com", "allow").action, NetworkPolicyRuleAction.ALLOW)

    def test_review_decision_opaque_strings_match_upstream(self):
        allow = NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.ALLOW)
        deny = NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.DENY)

        self.assertEqual(ReviewDecision.approved().to_opaque_string(), "approved")
        self.assertEqual(
            ReviewDecision.approved_execpolicy_amendment(ExecPolicyAmendment.new(["npm"])).to_opaque_string(),
            "approved_with_amendment",
        )
        self.assertEqual(ReviewDecision.approved_for_session().to_opaque_string(), "approved_for_session")
        self.assertEqual(
            ReviewDecision.network_policy_amendment_decision(allow).to_opaque_string(),
            "approved_with_network_policy_allow",
        )
        self.assertEqual(
            ReviewDecision.network_policy_amendment_decision(deny).to_opaque_string(),
            "denied_with_network_policy_deny",
        )
        self.assertEqual(ReviewDecision.default(), ReviewDecision.denied())
        self.assertEqual(ReviewDecision.timed_out().to_opaque_string(), "timed_out")
        self.assertEqual(ReviewDecision.abort().to_opaque_string(), "abort")

    def test_review_decision_round_trips_upstream_json_shape(self):
        exec_amendment = ExecPolicyAmendment.new(["npm", "test"])
        network_amendment = NetworkPolicyAmendment("api.example.com", NetworkPolicyRuleAction.ALLOW)

        simple = ReviewDecision.approved_for_session()
        exec_decision = ReviewDecision.approved_execpolicy_amendment(exec_amendment)
        network_decision = ReviewDecision.network_policy_amendment_decision(network_amendment)

        self.assertEqual(simple.to_mapping(), "approved_for_session")
        self.assertEqual(ReviewDecision.from_mapping("approved_for_session"), simple)
        self.assertEqual(ReviewDecision.from_mapping("acceptForSession"), simple)
        self.assertEqual(ReviewDecision.from_mapping("Cancel"), ReviewDecision.abort())
        self.assertEqual(
            exec_decision.to_mapping(),
            {
                "approved_execpolicy_amendment": {
                    "proposed_execpolicy_amendment": {"command": ["npm", "test"]}
                }
            },
        )
        self.assertEqual(ReviewDecision.from_mapping(exec_decision.to_mapping()), exec_decision)
        self.assertEqual(
            ReviewDecision.from_mapping({"acceptWithExecpolicyAmendment": {"execpolicyAmendment": {"command": ["npm", "test"]}}}),
            exec_decision,
        )
        self.assertEqual(
            network_decision.to_mapping(),
            {
                "network_policy_amendment": {
                    "network_policy_amendment": {
                        "host": "api.example.com",
                        "action": "allow",
                    }
                }
            },
        )
        self.assertEqual(ReviewDecision.from_mapping(network_decision.to_mapping()), network_decision)
        self.assertEqual(
            ReviewDecision.from_mapping(
                {"applyNetworkPolicyAmendment": {"networkPolicyAmendment": {"host": "api.example.com", "action": "allow"}}}
            ),
            network_decision,
        )

    def test_command_execution_approval_response_uses_app_server_decision_shape(self):
        exec_amendment = ExecPolicyAmendment.new(["npm", "test"])
        network_amendment = NetworkPolicyAmendment("api.example.com", NetworkPolicyRuleAction.ALLOW)

        self.assertEqual(command_execution_approval_decision_to_mapping(ReviewDecision.approved()), "accept")
        self.assertEqual(command_execution_approval_decision_to_mapping(ReviewDecision.approved_for_session()), "acceptForSession")
        self.assertEqual(command_execution_approval_decision_to_mapping(ReviewDecision.denied()), "decline")
        self.assertEqual(command_execution_approval_decision_to_mapping(ReviewDecision.timed_out()), "decline")
        self.assertEqual(command_execution_approval_decision_to_mapping(ReviewDecision.abort()), "cancel")
        self.assertEqual(
            command_execution_approval_decision_to_mapping(ReviewDecision.approved_execpolicy_amendment(exec_amendment)),
            {"acceptWithExecpolicyAmendment": {"execpolicyAmendment": {"command": ["npm", "test"]}}},
        )
        self.assertEqual(
            command_execution_approval_decision_to_mapping(ReviewDecision.network_policy_amendment_decision(network_amendment)),
            {"applyNetworkPolicyAmendment": {"networkPolicyAmendment": {"host": "api.example.com", "action": "allow"}}},
        )
        self.assertEqual(command_execution_request_approval_response(ReviewDecision.approved()), {"decision": "accept"})

    def test_file_change_approval_response_uses_app_server_decision_shape(self):
        self.assertEqual(file_change_approval_decision_to_mapping(ReviewDecision.approved()), "accept")
        self.assertEqual(file_change_approval_decision_to_mapping(ReviewDecision.approved_for_session()), "acceptForSession")
        self.assertEqual(file_change_approval_decision_to_mapping(ReviewDecision.denied()), "decline")
        self.assertEqual(file_change_approval_decision_to_mapping(ReviewDecision.timed_out()), "decline")
        self.assertEqual(file_change_approval_decision_to_mapping(ReviewDecision.abort()), "cancel")
        self.assertEqual(file_change_request_approval_response(ReviewDecision.approved()), {"decision": "accept"})
        with self.assertRaisesRegex(ValueError, "unsupported file change approval decision"):
            file_change_approval_decision_to_mapping(
                ReviewDecision.approved_execpolicy_amendment(ExecPolicyAmendment.new(["npm"]))
            )

    def test_exec_approval_effective_approval_id_falls_back_to_call_id(self):
        self.assertEqual(
            ExecApprovalRequestEvent("call-1", 123, ("git", "status"), Path(".")).effective_approval_id(),
            "call-1",
        )
        self.assertEqual(
            ExecApprovalRequestEvent(
                "call-1",
                123,
                ("git", "status"),
                Path("."),
                approval_id="child-approval",
            ).effective_approval_id(),
            "child-approval",
        )

    def test_exec_approval_uses_explicit_available_decisions(self):
        event = ExecApprovalRequestEvent(
            "call-1",
            123,
            ("git", "status"),
            Path("."),
            available_decisions=(ReviewDecision.denied(),),
        )

        self.assertEqual(event.effective_available_decisions(), (ReviewDecision.denied(),))

    def test_default_available_decisions_for_network_context(self):
        allow = NetworkPolicyAmendment("api.example.com", NetworkPolicyRuleAction.ALLOW)
        deny = NetworkPolicyAmendment("api.example.com", NetworkPolicyRuleAction.DENY)
        decisions = ExecApprovalRequestEvent.default_available_decisions(
            network_approval_context=NetworkApprovalContext("api.example.com", NetworkApprovalProtocol.HTTPS),
            proposed_network_policy_amendments=(deny, allow),
        )

        self.assertEqual(
            decisions,
            (
                ReviewDecision.approved(),
                ReviewDecision.approved_for_session(),
                ReviewDecision.network_policy_amendment_decision(allow),
                ReviewDecision.abort(),
            ),
        )

    def test_default_available_decisions_for_additional_permissions(self):
        decisions = ExecApprovalRequestEvent.default_available_decisions(
            additional_permissions=AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        self.assertEqual(decisions, (ReviewDecision.approved(), ReviewDecision.abort()))

    def test_default_available_decisions_for_execpolicy_prefix(self):
        amendment = ExecPolicyAmendment.new(["cargo", "test"])

        decisions = ExecApprovalRequestEvent.default_available_decisions(proposed_execpolicy_amendment=amendment)

        self.assertEqual(
            decisions,
            (
                ReviewDecision.approved(),
                ReviewDecision.approved_execpolicy_amendment(amendment),
                ReviewDecision.abort(),
            ),
        )

    def test_request_permission_profile_converts_to_additional_permissions(self):
        request = RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        additional = request.to_additional_permission_profile()

        self.assertFalse(request.is_empty())
        self.assertEqual(additional, AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)))
        self.assertEqual(RequestPermissionProfile.from_additional_permission_profile(additional), request)
        with self.assertRaisesRegex(TypeError, "value must be AdditionalPermissionProfile"):
            RequestPermissionProfile.from_additional_permission_profile({"network": {"enabled": True}})
        with self.assertRaisesRegex(TypeError, "network must be NetworkPermissions"):
            RequestPermissionProfile(network={"enabled": True})
        with self.assertRaisesRegex(TypeError, "file_system must be FileSystemPermissions"):
            RequestPermissionProfile(file_system={"read": ["/read"]})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            RequestPermissionProfile.from_mapping({"network": {"enabled": True}, "unexpected": True})

    def test_request_permissions_events_and_defaults(self):
        request = RequestPermissionProfile(network=NetworkPermissions(enabled=True))

        self.assertIs(PermissionGrantScope.default(), PermissionGrantScope.TURN)
        self.assertEqual(RequestPermissionsArgs(request, reason="need network").permissions, request)
        self.assertEqual(RequestPermissionsResponse(request).scope, PermissionGrantScope.TURN)
        self.assertEqual(RequestPermissionsResponse(request, scope="session").scope, PermissionGrantScope.SESSION)
        self.assertFalse(RequestPermissionsResponse(request).strict_auto_review)
        self.assertEqual(
            RequestPermissionsEvent("call", 10, request, cwd=Path("/tmp")).cwd,
            Path("/tmp"),
        )
        with self.assertRaisesRegex(TypeError, "permissions must be RequestPermissionProfile"):
            RequestPermissionsArgs({"network": {"enabled": True}})
        with self.assertRaisesRegex(TypeError, "reason must be a string"):
            RequestPermissionsArgs(request, reason=123)
        with self.assertRaisesRegex(TypeError, "permissions must be RequestPermissionProfile"):
            RequestPermissionsResponse({"network": {"enabled": True}})
        with self.assertRaisesRegex(TypeError, "scope must be a string"):
            RequestPermissionsResponse(request, scope=123)
        with self.assertRaisesRegex(TypeError, "scope must be a string"):
            RequestPermissionsResponse.from_mapping(
                {
                    "permissions": {"network": {"enabled": True}},
                    "scope": 123,
                }
            )
        with self.assertRaisesRegex(TypeError, "strict_auto_review must be a bool"):
            RequestPermissionsResponse(request, strict_auto_review="false")
        with self.assertRaisesRegex(TypeError, "started_at_ms must be an integer"):
            RequestPermissionsEvent("call", True, request)
        self.assertEqual(RequestPermissionsEvent("call", -1, request).started_at_ms, -1)
        self.assertEqual(RequestPermissionsEvent("call", -(2**63), request).started_at_ms, -(2**63))
        self.assertEqual(RequestPermissionsEvent("call", 2**63 - 1, request).started_at_ms, 2**63 - 1)
        with self.assertRaisesRegex(ValueError, "started_at_ms must fit in i64"):
            RequestPermissionsEvent("call", -(2**63) - 1, request)
        with self.assertRaisesRegex(ValueError, "started_at_ms must fit in i64"):
            RequestPermissionsEvent("call", 2**63, request)
        with self.assertRaisesRegex(TypeError, "permissions must be RequestPermissionProfile"):
            RequestPermissionsEvent("call", 10, {"network": {"enabled": True}})
        with self.assertRaisesRegex(TypeError, "cwd must be a string or Path"):
            RequestPermissionsEvent("call", 10, request, cwd=123)
        with self.assertRaisesRegex(TypeError, "turn_id must be a string"):
            RequestPermissionsEvent.from_mapping(
                {
                    "call_id": "call",
                    "turn_id": 123,
                    "started_at_ms": 10,
                    "permissions": {"network": {"enabled": True}},
                }
            )
        self.assertEqual(
            RequestPermissionsEvent.from_mapping(
                {
                    "call_id": "call",
                    "started_at_ms": -1,
                    "permissions": {"network": {"enabled": True}},
                }
            ).started_at_ms,
            -1,
        )
        with self.assertRaisesRegex(ValueError, "started_at_ms must fit in i64"):
            RequestPermissionsEvent.from_mapping(
                {
                    "call_id": "call",
                    "started_at_ms": 2**63,
                    "permissions": {"network": {"enabled": True}},
                }
            )

    def test_request_permissions_args_round_trips_upstream_json_shape(self):
        request = RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        args = RequestPermissionsArgs(request, reason="need network")
        args_without_reason = RequestPermissionsArgs(request)

        self.assertEqual(
            args.to_mapping(),
            {
                "permissions": {"network": {"enabled": True}},
                "reason": "need network",
            },
        )
        self.assertEqual(RequestPermissionsArgs.from_mapping(args.to_mapping()), args)
        self.assertEqual(
            args_without_reason.to_mapping(),
            {"permissions": {"network": {"enabled": True}}},
        )
        self.assertEqual(RequestPermissionsArgs.from_mapping(args_without_reason.to_mapping()), args_without_reason)

    def test_request_permissions_response_round_trips_upstream_json_shape(self):
        request = RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        response = RequestPermissionsResponse(request, scope=PermissionGrantScope.SESSION)
        strict_response = RequestPermissionsResponse(request, strict_auto_review=True)

        self.assertEqual(
            response.to_mapping(),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "session",
            },
        )
        self.assertEqual(RequestPermissionsResponse.from_mapping(response.to_mapping()), response)
        self.assertEqual(
            strict_response.to_mapping(),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "turn",
                "strict_auto_review": True,
            },
        )
        self.assertEqual(RequestPermissionsResponse.from_mapping(strict_response.to_mapping()), strict_response)
        self.assertEqual(
            RequestPermissionsResponse.from_mapping(
                {"permissions": {"network": {"enabled": True}}, "scope": "turn", "strictAutoReview": True}
            ),
            strict_response,
        )
        self.assertEqual(
            permissions_request_approval_response(strict_response),
            {"permissions": {"network": {"enabled": True}}, "scope": "turn", "strictAutoReview": True},
        )

    def test_guardian_assessment_action_shapes(self):
        permissions = RequestPermissionProfile(network=NetworkPermissions(enabled=True))

        self.assertEqual(
            GuardianAssessmentAction.command_action(GuardianCommandSource.SHELL, "rm -rf tmp", Path("/tmp")),
            GuardianAssessmentAction(type="command", source=GuardianCommandSource.SHELL, command="rm -rf tmp", cwd=Path("/tmp")),
        )
        self.assertEqual(
            GuardianAssessmentAction.execve(GuardianCommandSource.UNIFIED_EXEC, "/bin/rm", ("rm", "-f"), Path("/tmp")).argv,
            ("rm", "-f"),
        )
        self.assertEqual(
            GuardianAssessmentAction.apply_patch(Path("/repo"), (Path("a.py"),)).files,
            (Path("a.py"),),
        )
        self.assertEqual(
            GuardianAssessmentAction.network_access("https://api.example.com", "api.example.com", NetworkApprovalProtocol.HTTPS, 443).port,
            443,
        )
        self.assertEqual(GuardianAssessmentAction.mcp_tool_call("server", "tool").tool_name, "tool")
        self.assertEqual(GuardianAssessmentAction.request_permissions(permissions, "why").permissions, permissions)

    def test_guardian_assessment_action_round_trips_upstream_json_shape(self):
        payloads = [
            {
                "type": "command",
                "source": "shell",
                "command": "ls",
                "cwd": str(Path("/repo")),
            },
            {
                "type": "execve",
                "source": "unified_exec",
                "program": "/bin/echo",
                "argv": ["echo", "hi"],
                "cwd": str(Path("/repo")),
            },
            {
                "type": "apply_patch",
                "cwd": str(Path("/repo")),
                "files": [str(Path("/repo/a.py"))],
            },
            {
                "type": "network_access",
                "target": "https://api.example.com",
                "host": "api.example.com",
                "protocol": "https",
                "port": 443,
            },
            {
                "type": "mcp_tool_call",
                "server": "github",
                "tool_name": "search",
                "connector_id": None,
                "connector_name": None,
                "tool_title": None,
            },
            {
                "type": "request_permissions",
                "reason": None,
                "permissions": {"network": {"enabled": True}},
            },
        ]

        for payload in payloads:
            with self.subTest(action=payload["type"]):
                self.assertEqual(GuardianAssessmentAction.from_mapping(payload).to_mapping(), payload)

    def test_guardian_assessment_event_and_enums(self):
        action = GuardianAssessmentAction.command_action(GuardianCommandSource.SHELL, "ls", Path("."))
        event = GuardianAssessmentEvent(
            id="review-1",
            status=GuardianAssessmentStatus.APPROVED,
            action=action,
            risk_level=GuardianRiskLevel.LOW,
            user_authorization=GuardianUserAuthorization.HIGH,
            decision_source=GuardianAssessmentDecisionSource.AGENT,
        )

        self.assertEqual(event.action, action)
        self.assertIs(GuardianAssessmentOutcome.ALLOW, GuardianAssessmentOutcome.ALLOW)
        self.assertEqual(event.turn_id, "")
        self.assertEqual(event.started_at_ms, 0)

        with self.assertRaisesRegex(TypeError, "id must be a string"):
            GuardianAssessmentEvent(123, GuardianAssessmentStatus.APPROVED, action)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "turn_id must be a string"):
            GuardianAssessmentEvent("review-1", GuardianAssessmentStatus.APPROVED, action, turn_id=123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "started_at_ms must be an integer"):
            GuardianAssessmentEvent("review-1", GuardianAssessmentStatus.APPROVED, action, started_at_ms=True)
        with self.assertRaisesRegex(ValueError, "started_at_ms must fit in i64"):
            GuardianAssessmentEvent("review-1", GuardianAssessmentStatus.APPROVED, action, started_at_ms=2**63)
        with self.assertRaisesRegex(TypeError, "action must be a GuardianAssessmentAction"):
            GuardianAssessmentEvent("review-1", GuardianAssessmentStatus.APPROVED, object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "turn_id must be a string"):
            GuardianAssessmentEvent.from_mapping(
                {
                    "id": "review-1",
                    "turn_id": 123,
                    "started_at_ms": 0,
                    "status": "approved",
                    "action": {"type": "command", "source": "shell", "command": "ls", "cwd": "."},
                }
            )

    def test_guardian_assessment_event_round_trips_upstream_json_shape(self):
        payload = {
            "id": "review-1",
            "target_item_id": "call-1",
            "turn_id": "turn-1",
            "started_at_ms": 10,
            "completed_at_ms": 20,
            "status": "denied",
            "risk_level": "high",
            "user_authorization": "low",
            "rationale": "not authorized",
            "decision_source": "agent",
            "action": {
                "type": "request_permissions",
                "reason": "need network",
                "permissions": {"network": {"enabled": True}},
            },
        }

        self.assertEqual(GuardianAssessmentEvent.from_mapping(payload).to_mapping(), payload)

    def test_elicitation_request_message_and_event(self):
        form = ElicitationRequest.form("Fill this", {"type": "object"})
        url = ElicitationRequest.url("Open this", "https://example.com", "elicit-1")

        self.assertEqual(form.message(), "Fill this")
        self.assertEqual(url.message(), "Open this")
        self.assertEqual(ElicitationRequestEvent("server", 7, form).request, form)
        self.assertIs(ElicitationAction.ACCEPT, ElicitationAction.ACCEPT)

    def test_file_change_and_patch_approval_shapes(self):
        changes = {
            Path("new.py"): FileChange.add("print('hi')"),
            Path("old.py"): FileChange.delete("old"),
            Path("move.py"): FileChange.update("--- diff", move_path=Path("new_move.py")),
        }
        event = ApplyPatchApprovalRequestEvent("call", 123, changes, grant_root=Path("/repo"))

        self.assertEqual(event.changes[Path("new.py")].type, "add")
        self.assertEqual(event.changes[Path("move.py")].move_path, Path("new_move.py"))
        self.assertEqual(event.grant_root, Path("/repo"))

        with self.assertRaisesRegex(TypeError, "add file change requires content"):
            FileChange("add")
        with self.assertRaisesRegex(ValueError, "add file change cannot include update fields"):
            FileChange("add", content="new", unified_diff="--- diff")
        with self.assertRaisesRegex(TypeError, "update file change requires unified_diff"):
            FileChange("update")
        with self.assertRaisesRegex(ValueError, "unknown file change type"):
            FileChange("copy")
        with self.assertRaisesRegex(TypeError, "call_id must be a string"):
            ApplyPatchApprovalRequestEvent(123, 1, changes)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "started_at_ms must fit in i64"):
            ApplyPatchApprovalRequestEvent("call", 2**63, changes)
        with self.assertRaisesRegex(TypeError, "changes must be a mapping"):
            ApplyPatchApprovalRequestEvent("call", 1, [])  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "change values must be FileChange"):
            ApplyPatchApprovalRequestEvent("call", 1, {Path("x.py"): {"type": "add"}})  # type: ignore[dict-item]
        with self.assertRaisesRegex(TypeError, "grant_root must be a string or Path"):
            ApplyPatchApprovalRequestEvent("call", 1, changes, grant_root=123)  # type: ignore[arg-type]

    def test_escalation_permissions_variants(self):
        additional = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        resolved = ResolvedPermissionProfile(PermissionProfile.disabled())

        self.assertEqual(EscalationPermissions.additional(additional).additional_permission_profile, additional)
        self.assertEqual(EscalationPermissions.resolved(resolved).resolved_permission_profile, resolved)
        with self.assertRaisesRegex(TypeError, "permission_profile must be a PermissionProfile"):
            ResolvedPermissionProfile("disabled")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "additional_permission_profile must be an AdditionalPermissionProfile"):
            EscalationPermissions.additional({"network": {"enabled": True}})  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "resolved_permission_profile variant cannot include"):
            EscalationPermissions(
                "resolved_permission_profile",
                additional_permission_profile=additional,
                resolved_permission_profile=resolved,
            )


if __name__ == "__main__":
    unittest.main()
