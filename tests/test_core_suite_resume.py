import json
from types import SimpleNamespace

from pycodex.core.context import ModelSwitchInstructions
from pycodex.core.context_manager.updates import build_model_instructions_update_item
from pycodex.exec.local_runtime import local_http_exec_initial_messages_from_rollout
from pycodex.protocol.user_input import ByteRange, TextElement


def _append_event(path, payload):
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(
            json.dumps(
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": payload,
                },
                separators=(",", ":"),
            )
            + "\n"
        )


class _ModelInfo:
    slug = "gpt-5.3-codex"

    def get_model_instructions(self, _personality=None):
        return "new model base behavior"


def _next_context(slug="gpt-5.3-codex"):
    model = _ModelInfo()
    model.slug = slug
    return SimpleNamespace(model_info=model, personality=None)


def test_resume_includes_initial_messages_from_rollout_events(tmp_path):
    # Rust: codex/codex-rs/core/tests/suite/resume.rs
    # Test: resume_includes_initial_messages_from_rollout_events.
    rollout = tmp_path / "rollout.jsonl"
    text_element = {
        "byte_range": {"start": 0, "end": 6},
        "placeholder": "<note>",
    }
    _append_event(rollout, {"type": "turn_started", "turn_id": "turn-1"})
    _append_event(
        rollout,
        {
            "type": "user_message",
            "message": "Record some messages",
            "text_elements": [text_element],
        },
    )
    _append_event(rollout, {"type": "agent_message", "message": "Completed first turn"})
    _append_event(rollout, {"type": "token_count", "info": None, "rate_limits": None})
    _append_event(
        rollout,
        {
            "type": "turn_complete",
            "turn_id": "turn-1",
            "last_agent_message": "Completed first turn",
        },
    )

    messages = local_http_exec_initial_messages_from_rollout(rollout)

    assert [message.type for message in messages] == [
        "task_started",
        "user_message",
        "agent_message",
        "token_count",
        "task_complete",
    ]
    assert messages[1].payload.message == "Record some messages"
    assert messages[1].payload.text_elements == (
        TextElement.new(ByteRange(0, 6), "<note>"),
    )
    assert messages[2].payload.message == "Completed first turn"
    assert messages[4].payload.turn_id == messages[0].payload.turn_id
    assert messages[4].payload.last_agent_message == "Completed first turn"


def test_resume_includes_initial_messages_from_reasoning_events(tmp_path):
    # Rust: resume_includes_initial_messages_from_reasoning_events.
    rollout = tmp_path / "rollout.jsonl"
    _append_event(rollout, {"type": "turn_started", "turn_id": "turn-1"})
    _append_event(rollout, {"type": "user_message", "message": "Record reasoning messages"})
    _append_event(rollout, {"type": "agent_reasoning", "text": "Summarized step"})
    _append_event(rollout, {"type": "agent_reasoning_raw_content", "text": "raw detail"})
    _append_event(rollout, {"type": "agent_message", "message": "Completed reasoning turn"})
    _append_event(rollout, {"type": "token_count", "info": None, "rate_limits": None})
    _append_event(
        rollout,
        {
            "type": "turn_complete",
            "turn_id": "turn-1",
            "last_agent_message": "Completed reasoning turn",
        },
    )

    messages = local_http_exec_initial_messages_from_rollout(rollout)

    assert [message.type for message in messages] == [
        "task_started",
        "user_message",
        "agent_reasoning",
        "agent_reasoning_raw_content",
        "agent_message",
        "token_count",
        "task_complete",
    ]
    assert messages[1].payload.message == "Record reasoning messages"
    assert messages[2].payload.text == "Summarized step"
    assert messages[3].payload.text == "raw detail"
    assert messages[4].payload.message == "Completed reasoning turn"
    assert messages[6].payload.turn_id == messages[0].payload.turn_id


def test_resume_switches_models_preserves_base_instructions():
    # Rust: resume_switches_models_preserves_base_instructions.
    initial_instructions = "original baked base instructions"
    message = build_model_instructions_update_item(
        SimpleNamespace(model="gpt-5.2"),
        _next_context("gpt-5.3-codex"),
    )

    assert message == ModelSwitchInstructions.new("new model base behavior").render()
    assert "<model_switch>" in message
    assert initial_instructions == "original baked base instructions"


def test_resume_model_switch_is_not_duplicated_after_pre_turn_override():
    # Rust: resume_model_switch_is_not_duplicated_after_pre_turn_override.
    first = build_model_instructions_update_item(
        SimpleNamespace(model="gpt-5.2"),
        _next_context("gpt-5.4"),
    )
    second = build_model_instructions_update_item(
        SimpleNamespace(model="gpt-5.4"),
        _next_context("gpt-5.4"),
    )

    developer_sections = [section for section in (first, second) if section is not None]
    assert sum("<model_switch>" in section for section in developer_sections) == 1
