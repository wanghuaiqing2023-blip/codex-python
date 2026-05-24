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
)


class ProtocolApprovalsTests(unittest.TestCase):
    def test_exec_policy_amendment_keeps_command_prefix_tokens(self):
        amendment = ExecPolicyAmendment.new(["git", "status"])

        self.assertEqual(amendment.command, ("git", "status"))
        self.assertEqual(amendment.command_tokens(), ("git", "status"))

    def test_network_approval_protocol_accepts_upstream_aliases(self):
        self.assertIs(NetworkApprovalProtocol.parse("http"), NetworkApprovalProtocol.HTTP)
        self.assertIs(NetworkApprovalProtocol.parse("https_connect"), NetworkApprovalProtocol.HTTPS)
        self.assertIs(NetworkApprovalProtocol.parse("http-connect"), NetworkApprovalProtocol.HTTPS)

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

    def test_escalation_permissions_variants(self):
        additional = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        resolved = ResolvedPermissionProfile(PermissionProfile.disabled())

        self.assertEqual(EscalationPermissions.additional(additional).additional_permission_profile, additional)
        self.assertEqual(EscalationPermissions.resolved(resolved).resolved_permission_profile, resolved)


if __name__ == "__main__":
    unittest.main()
