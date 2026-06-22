import json

from pycodex.hooks import PermissionRequestDecision
from pycodex.hooks import PermissionRequestDecisionKind
from pycodex.hooks import looks_like_json
from pycodex.hooks import parse_permission_request
from pycodex.hooks import parse_post_tool_use
from pycodex.hooks import parse_pre_tool_use
from pycodex.hooks import parse_session_start
from pycodex.hooks import parse_stop
from pycodex.hooks import parse_subagent_stop
from pycodex.hooks import parse_user_prompt_submit


def dumped(value):
    return json.dumps(value, separators=(",", ":"))


def test_permission_request_rejects_reserved_fields_from_rust_tests():
    # Rust crate/module/test:
    # codex-hooks/src/engine/output_parser.rs
    # permission_request_rejects_reserved_{updated_input,updated_permissions,interrupt}_field.
    cases = [
        ({"updatedInput": {}}, "PermissionRequest hook returned unsupported updatedInput"),
        (
            {"updatedPermissions": {}},
            "PermissionRequest hook returned unsupported updatedPermissions",
        ),
        ({"interrupt": True}, "PermissionRequest hook returned unsupported interrupt:true"),
    ]
    for extra, expected in cases:
        parsed = parse_permission_request(
            dumped(
                {
                    "continue": True,
                    "hookSpecificOutput": {
                        "hookEventName": "PermissionRequest",
                        "decision": {"behavior": "allow", **extra},
                    },
                }
            )
        )

        assert parsed is not None
        assert parsed.invalid_reason == expected
        assert parsed.decision is None


def test_permission_request_decision_defaults_and_universal_fail_closed():
    # Rust source contract: permission_request_decision trims deny messages and
    # unsupported PermissionRequest universal fields suppress parsed decisions.
    denied = parse_permission_request(
        dumped(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {"behavior": "deny", "message": "  "},
                }
            }
        )
    )
    assert denied is not None
    assert denied.decision == PermissionRequestDecision.Deny(
        "PermissionRequest hook denied approval"
    )

    invalid = parse_permission_request(
        dumped(
            {
                "continue": False,
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {"behavior": "allow"},
                },
            }
        )
    )
    assert invalid is not None
    assert invalid.invalid_reason == "PermissionRequest hook returned unsupported continue:false"
    assert invalid.decision is None


def test_pre_tool_use_hook_specific_decisions_and_legacy_invalid_reasons():
    # Rust source contract: parse_pre_tool_use prefers hook-specific decisions
    # when permissionDecision/permissionDecisionReason/updatedInput are present.
    allowed = parse_pre_tool_use(
        dumped(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "updatedInput": {"cmd": "ls"},
                    "additionalContext": "extra",
                }
            }
        )
    )
    assert allowed is not None
    assert allowed.invalid_reason is None
    assert allowed.updated_input == {"cmd": "ls"}
    assert allowed.additional_context == "extra"

    denied = parse_pre_tool_use(
        dumped(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "  no  ",
                }
            }
        )
    )
    assert denied is not None
    assert denied.block_reason == "no"

    invalid = parse_pre_tool_use(dumped({"decision": "block", "reason": "  "}))
    assert invalid is not None
    assert (
        invalid.invalid_reason
        == "PreToolUse hook returned decision:block without a non-empty reason"
    )

    invalid_allow = parse_pre_tool_use(
        dumped(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                }
            }
        )
    )
    assert invalid_allow is not None
    assert (
        invalid_allow.invalid_reason
        == "PreToolUse hook returned unsupported permissionDecision:allow"
    )


def test_post_tool_use_block_reason_and_reason_without_decision_contracts():
    # Rust source contract: parse_post_tool_use reports invalid_block_reason for
    # missing block reasons and for reason-without-decision while continuing.
    blocked = parse_post_tool_use(dumped({"decision": "block", "reason": "  stop  "}))
    assert blocked is not None
    assert blocked.should_block is True
    assert blocked.reason == "  stop  "

    missing_reason = parse_post_tool_use(dumped({"decision": "block"}))
    assert missing_reason is not None
    assert missing_reason.should_block is False
    assert (
        missing_reason.invalid_block_reason
        == "PostToolUse hook returned decision:block without a non-empty reason"
    )

    reason_without_decision = parse_post_tool_use(dumped({"reason": "because"}))
    assert reason_without_decision is not None
    assert (
        reason_without_decision.invalid_block_reason
        == "PostToolUse hook returned reason without decision"
    )

    unsupported_specific = parse_post_tool_use(
        dumped(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "updatedMCPToolOutput": {},
                }
            }
        )
    )
    assert unsupported_specific is not None
    assert (
        unsupported_specific.invalid_reason
        == "PostToolUse hook returned unsupported updatedMCPToolOutput"
    )


def test_start_stop_user_prompt_and_json_shape_contracts():
    # Rust source contract: parse_json trims input, requires an object, rejects
    # deny_unknown_fields wire shapes, and looks_like_json only trims the left.
    assert looks_like_json("  [1]") is True
    assert looks_like_json("\nplain") is False
    assert parse_session_start("[]") is None
    assert parse_session_start(dumped({"unexpected": True})) is None

    started = parse_session_start(
        dumped(
            {
                "systemMessage": "warn",
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "ctx",
                },
            }
        )
    )
    assert started is not None
    assert started.universal.system_message == "warn"
    assert started.additional_context == "ctx"

    stopped = parse_stop(dumped({"decision": "block", "reason": "  stop now  "}))
    assert stopped is not None
    assert stopped.should_block is True
    assert stopped.reason == "  stop now  "

    subagent_stop = parse_subagent_stop(dumped({"decision": "block", "reason": ""}))
    assert subagent_stop is not None
    assert subagent_stop.should_block is False
    assert (
        subagent_stop.invalid_block_reason
        == "SubagentStop hook returned decision:block without a non-empty reason"
    )

    user_prompt = parse_user_prompt_submit(
        dumped(
            {
                "decision": "block",
                "reason": "halt",
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": "ctx",
                },
            }
        )
    )
    assert user_prompt is not None
    assert user_prompt.should_block is True
    assert user_prompt.additional_context == "ctx"


def test_serde_like_wire_validation_rejects_bad_types_and_enums():
    # Rust source contract: serde deserialization into *CommandOutputWire
    # returns None for invalid field types, unknown fields, or enum variants.
    assert parse_pre_tool_use(dumped({"continue": "true"})) is None
    assert (
        parse_pre_tool_use(
            dumped(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "maybe",
                    }
                }
            )
        )
        is None
    )
    assert (
        parse_permission_request(
            dumped(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PermissionRequest",
                        "decision": {"behavior": "ask"},
                    }
                }
            )
        )
        is None
    )
    allow = parse_permission_request(
        dumped(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {"behavior": "allow", "interrupt": False},
                }
            }
        )
    )
    assert allow is not None
    assert allow.decision is not None
    assert allow.decision.kind == PermissionRequestDecisionKind.ALLOW
