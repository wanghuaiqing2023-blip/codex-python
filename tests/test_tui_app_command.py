"""Parity tests for ``codex-tui/src/app_command.rs``."""

from pathlib import Path

import pytest

from pycodex.tui.app_command import AppCommand, from_


def test_simple_constructors_create_expected_variants() -> None:
    # Rust: AppCommand::interrupt / clean_background_terminals / compact / shutdown
    assert AppCommand.interrupt() == AppCommand("Interrupt")
    assert AppCommand.clean_background_terminals() == AppCommand("CleanBackgroundTerminals")
    assert AppCommand.realtime_conversation_close() == AppCommand("RealtimeConversationClose")
    assert AppCommand.reload_user_config() == AppCommand("ReloadUserConfig")
    assert AppCommand.compact() == AppCommand("Compact")
    assert AppCommand.shutdown() == AppCommand("Shutdown")


def test_payload_constructors_match_rust_variant_fields() -> None:
    # Rust source: constructor helpers wrap their args into same-named enum fields.
    assert AppCommand.run_user_shell_command("ls") == AppCommand("RunUserShellCommand", {"command": "ls"})
    assert AppCommand.exec_approval("id", "turn", "accept") == AppCommand(
        "ExecApproval", {"id": "id", "turn_id": "turn", "decision": "accept"}
    )
    assert AppCommand.patch_approval("patch", "cancel") == AppCommand(
        "PatchApproval", {"id": "patch", "decision": "cancel"}
    )
    assert AppCommand.set_thread_name("name") == AppCommand("SetThreadName", {"name": "name"})
    assert AppCommand.thread_rollback(2) == AppCommand("ThreadRollback", {"num_turns": 2})


def test_user_turn_sets_approvals_reviewer_to_none() -> None:
    # Rust: AppCommand::user_turn always stores approvals_reviewer: None.
    command = AppCommand.user_turn(
        items=[{"type": "text", "text": "hi"}],
        cwd="/repo",
        approval_policy="on-request",
        active_permission_profile="active",
        model="gpt",
        effort="high",
        summary="auto",
        service_tier=None,
        final_output_json_schema={"type": "object"},
        collaboration_mode="pair",
        personality="friendly",
    )
    assert command.kind == "UserTurn"
    assert command.payload["cwd"] == Path("/repo")
    assert command.payload["approvals_reviewer"] is None
    assert command.payload["items"] == [{"type": "text", "text": "hi"}]


def test_override_turn_context_preserves_nested_options() -> None:
    # Rust: OverrideTurnContext stores Option<Option<...>> fields without flattening.
    command = AppCommand.override_turn_context(
        cwd="/repo",
        approval_policy="never",
        approvals_reviewer="user",
        permission_profile="profile",
        active_permission_profile="active",
        windows_sandbox_level="strict",
        model="gpt",
        effort=None,
        summary="detailed",
        service_tier="plus",
        collaboration_mode="solo",
        personality="direct",
    )
    assert command.kind == "OverrideTurnContext"
    assert command.payload["cwd"] == Path("/repo")
    assert command.payload["effort"] is None
    assert command.payload["service_tier"] == "plus"


def test_realtime_elicitation_user_input_and_permissions_commands() -> None:
    # Rust: constructors for non-turn payload variants.
    assert AppCommand.realtime_conversation_start("ws", {"voice": "alloy"}) == AppCommand(
        "RealtimeConversationStart", {"transport": "ws", "voice": {"voice": "alloy"}}
    )
    assert AppCommand.realtime_conversation_audio(b"frame") == AppCommand(
        "RealtimeConversationAudio", {"frame": b"frame"}
    )
    assert AppCommand.resolve_elicitation("srv", "req-1", "accept", {"x": 1}, None) == AppCommand(
        "ResolveElicitation",
        {"server_name": "srv", "request_id": "req-1", "decision": "accept", "content": {"x": 1}, "meta": None},
    )
    assert AppCommand.user_input_answer("input", "answer") == AppCommand(
        "UserInputAnswer", {"id": "input", "response": "answer"}
    )
    assert AppCommand.request_permissions_response("perm", "response") == AppCommand(
        "RequestPermissionsResponse", {"id": "perm", "response": "response"}
    )


def test_list_skills_review_guardian_and_is_review() -> None:
    # Rust: list_skills maps cwd list; is_review matches only Review variant.
    assert AppCommand.list_skills(["/a", Path("/b")], True) == AppCommand(
        "ListSkills", {"cwds": [Path("/a"), Path("/b")], "force_reload": True}
    )
    review = AppCommand.review("target")
    assert review == AppCommand("Review", {"target": "target"})
    assert review.is_review() is True
    assert AppCommand.approve_guardian_denied_action("event") == AppCommand(
        "ApproveGuardianDeniedAction", {"event": "event"}
    )
    assert AppCommand.interrupt().is_review() is False


def test_from_clones_app_command_payload() -> None:
    # Rust: impl From<&AppCommand> for AppCommand returns value.clone().
    original = AppCommand.user_turn([], "/repo", "never", None, "gpt", None, None, None, {"items": []}, None, None)
    cloned = from_(original)
    assert cloned == original
    assert cloned is not original
    assert cloned.payload is not original.payload
    cloned.payload["final_output_json_schema"]["items"].append("x")
    assert original.payload["final_output_json_schema"] == {"items": []}


def test_from_rejects_non_app_command() -> None:
    with pytest.raises(TypeError):
        from_("not-command")  # type: ignore[arg-type]


def test_user_turn_copies_items_list_like_owned_vec() -> None:
    items = [{"type": "text", "text": "hi"}]

    command = AppCommand.user_turn(
        items=items,
        cwd="/repo",
        approval_policy="on-request",
        active_permission_profile=None,
        model="gpt",
        effort=None,
        summary=None,
        service_tier=None,
        final_output_json_schema=None,
        collaboration_mode=None,
        personality=None,
    )
    items.append({"type": "text", "text": "later"})

    assert command.payload["items"] == [{"type": "text", "text": "hi"}]


def test_constructors_deep_copy_owned_mutable_payloads() -> None:
    # Rust constructors consume owned values; later caller-side mutation cannot
    # alter the already-built enum payload.
    item = {"type": "text", "text": ["hi"]}
    schema = {"properties": {"answer": {"type": "string"}}}
    command = AppCommand.user_turn(
        items=[item],
        cwd="/repo",
        approval_policy="on-request",
        active_permission_profile={"profile": ["active"]},
        model="gpt",
        effort={"level": ["high"]},
        summary={"mode": ["auto"]},
        service_tier={"tier": ["flex"]},
        final_output_json_schema=schema,
        collaboration_mode={"mode": ["pair"]},
        personality={"tone": ["friendly"]},
    )

    item["text"].append("later")
    schema["properties"]["answer"]["type"] = "integer"

    assert command.payload["items"] == [{"type": "text", "text": ["hi"]}]
    assert command.payload["final_output_json_schema"] == {
        "properties": {"answer": {"type": "string"}}
    }

    voice = {"voice": ["alloy"]}
    start = AppCommand.realtime_conversation_start({"transport": ["ws"]}, voice)
    voice["voice"].append("verse")
    assert start.payload["voice"] == {"voice": ["alloy"]}

    content = {"value": ["accepted"]}
    meta = {"meta": ["m"]}
    elicitation = AppCommand.resolve_elicitation("srv", "req-1", "accept", content, meta)
    content["value"].append("mutated")
    meta["meta"].append("mutated")
    assert elicitation.payload["content"] == {"value": ["accepted"]}
    assert elicitation.payload["meta"] == {"meta": ["m"]}


def test_override_turn_context_deep_copies_owned_mutable_options() -> None:
    effort = {"effort": ["high"]}
    service_tier = {"service_tier": ["auto"]}

    command = AppCommand.override_turn_context(
        effort=effort,
        service_tier=service_tier,
        active_permission_profile={"profile": ["active"]},
    )
    effort["effort"].append("low")
    service_tier["service_tier"].append("flex")

    assert command.payload["effort"] == {"effort": ["high"]}
    assert command.payload["service_tier"] == {"service_tier": ["auto"]}
    assert command.payload["active_permission_profile"] == {"profile": ["active"]}


def test_remaining_owned_payload_constructors_deep_copy_mutable_values() -> None:
    # Rust constructors consume owned payloads for these enum variants too.
    decision = {"decision": ["accept"]}
    response = {"response": ["ok"]}
    event = {"event": ["denied"]}
    target = {"target": ["review"]}

    exec_approval = AppCommand.exec_approval("exec", "turn", decision)
    patch_approval = AppCommand.patch_approval("patch", decision)
    user_answer = AppCommand.user_input_answer("input", response)
    permission_response = AppCommand.request_permissions_response("perm", response)
    guardian = AppCommand.approve_guardian_denied_action(event)
    review = AppCommand.review(target)

    decision["decision"].append("mutated")
    response["response"].append("mutated")
    event["event"].append("mutated")
    target["target"].append("mutated")

    assert exec_approval.payload["decision"] == {"decision": ["accept"]}
    assert patch_approval.payload["decision"] == {"decision": ["accept"]}
    assert user_answer.payload["response"] == {"response": ["ok"]}
    assert permission_response.payload["response"] == {"response": ["ok"]}
    assert guardian.payload["event"] == {"event": ["denied"]}
    assert review.payload["target"] == {"target": ["review"]}
