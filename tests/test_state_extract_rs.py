from datetime import datetime, timezone
from pathlib import Path

from pycodex.protocol import ReasoningEffort, ThreadId, ThreadSource, USER_MESSAGE_BEGIN
from pycodex.state.extract import (
    IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER,
    apply_rollout_item,
    rollout_item_affects_thread_metadata,
    strip_user_message_prefix,
    user_message_preview,
)
from pycodex.state.model import ThreadMetadata


THREAD_ID = ThreadId.from_string("00000000-0000-0000-0000-00000000002a")


def _metadata() -> ThreadMetadata:
    created_at = datetime.fromtimestamp(1_735_689_600, tz=timezone.utc)
    return ThreadMetadata(
        id=THREAD_ID,
        rollout_path=Path("/tmp/a.jsonl"),
        created_at=created_at,
        updated_at=created_at,
        source="cli",
        thread_source=None,
        agent_path=None,
        agent_nickname=None,
        agent_role=None,
        model_provider="openai",
        model=None,
        reasoning_effort=None,
        cwd=Path("/tmp"),
        cli_version="0.0.0",
        title="",
        preview=None,
        sandbox_policy="read-only",
        approval_mode="on-request",
        tokens_used=1,
        first_user_message=None,
        archived_at=None,
        git_sha=None,
        git_branch=None,
        git_origin_url=None,
    )


def _rollout(item_type: str, payload: object = None) -> dict[str, object]:
    return {"type": item_type, "payload": payload}


def _event(event_type: str, **payload: object) -> dict[str, object]:
    return _rollout("event_msg", {"type": event_type, **payload})


def test_response_item_user_messages_do_not_set_title_or_first_user_message() -> None:
    # Rust crate: codex-state
    # Rust module/test:
    # src/extract.rs::response_item_user_messages_do_not_set_title_or_first_user_message
    # Behavior contract: response items are ignored by thread metadata extraction.
    metadata = _metadata()
    item = _rollout(
        "response_item",
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hello"}]},
    )

    apply_rollout_item(metadata, item, "test-provider")

    assert metadata.first_user_message is None
    assert metadata.preview is None
    assert metadata.title == ""


def test_event_msg_user_messages_set_title_and_first_user_message() -> None:
    # Rust crate: codex-state
    # Rust module/test: src/extract.rs::event_msg_user_messages_set_title_and_first_user_message
    # Behavior contract: event user messages set first message, preview, and title.
    metadata = _metadata()
    item = _event(
        "user_message",
        message=f"{USER_MESSAGE_BEGIN} actual user request",
        images=[],
        local_images=[],
    )

    apply_rollout_item(metadata, item, "test-provider")

    assert metadata.first_user_message == "actual user request"
    assert metadata.preview == "actual user request"
    assert metadata.title == "actual user request"


def test_event_msg_image_only_user_message_sets_image_placeholder_preview() -> None:
    # Rust crate: codex-state
    # Rust module/test:
    # src/extract.rs::event_msg_image_only_user_message_sets_image_placeholder_preview
    # Behavior contract: image-only user messages use the stable [Image] placeholder.
    metadata = _metadata()
    item = _event(
        "user_message",
        message="",
        images=["https://example.test/image.png"],
        local_images=[],
    )

    apply_rollout_item(metadata, item, "test-provider")

    assert metadata.first_user_message == IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER
    assert metadata.preview == IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER
    assert metadata.title == ""


def test_event_msg_blank_user_message_without_images_keeps_first_user_message_empty() -> None:
    # Rust crate: codex-state
    # Rust module/test:
    # src/extract.rs::event_msg_blank_user_message_without_images_keeps_first_user_message_empty
    # Behavior contract: blank user messages without images do not affect preview/title.
    metadata = _metadata()
    item = _event("user_message", message="   ", images=[], local_images=[])

    apply_rollout_item(metadata, item, "test-provider")

    assert metadata.first_user_message is None
    assert metadata.preview is None
    assert metadata.title == ""


def test_thread_goal_sets_preview_only_and_later_user_sets_message_title() -> None:
    # Rust crate: codex-state
    # Rust module/test:
    # src/extract.rs::event_msg_thread_goal_sets_preview_only_and_later_user_sets_message_title
    # Behavior contract: non-empty goals set preview only; later user messages
    # preserve preview while filling first_user_message/title.
    metadata = _metadata()
    goal_item = _event(
        "thread_goal_updated",
        goal={"objective": "optimize the benchmark"},
    )

    apply_rollout_item(metadata, goal_item, "test-provider")

    assert metadata.preview == "optimize the benchmark"
    assert metadata.first_user_message is None
    assert metadata.title == ""

    user_item = _event(
        "user_message",
        message=f"{USER_MESSAGE_BEGIN} next normal prompt",
        images=[],
        local_images=[],
    )

    apply_rollout_item(metadata, user_item, "test-provider")

    assert metadata.preview == "optimize the benchmark"
    assert metadata.first_user_message == "next normal prompt"
    assert metadata.title == "next normal prompt"


def test_session_meta_turn_context_cwd_precedence_and_runtime_fields() -> None:
    # Rust crate: codex-state
    # Rust module/tests:
    # turn_context_does_not_override_session_cwd,
    # turn_context_sets_model_and_reasoning_effort
    # Behavior contract: session CWD wins; turn context updates model, effort,
    # sandbox policy, and approval mode.
    metadata = _metadata()
    metadata.cwd = Path()
    session_item = _rollout(
        "session_meta",
        {
            "meta": {
                "id": THREAD_ID,
                "source": "cli",
                "thread_source": ThreadSource.USER,
                "agent_nickname": "helper",
                "agent_role": "reviewer",
                "agent_path": "/helper",
                "model_provider": "openai",
                "cli_version": "0.0.1",
                "cwd": "/child/worktree",
            },
            "git": {
                "commit_hash": "abc123",
                "branch": "main",
                "repository_url": "https://example.test/repo.git",
            },
        },
    )
    turn_item = _rollout(
        "turn_context",
        {
            "cwd": "/parent/workspace",
            "model": "gpt-5",
            "effort": ReasoningEffort.HIGH,
            "sandbox_policy": "danger-full-access",
            "approval_policy": "never",
        },
    )

    apply_rollout_item(metadata, session_item, "test-provider")
    apply_rollout_item(metadata, turn_item, "test-provider")

    assert metadata.cwd == Path("/child/worktree")
    assert metadata.model == "gpt-5"
    assert metadata.reasoning_effort is ReasoningEffort.HIGH
    assert metadata.sandbox_policy == "danger-full-access"
    assert metadata.approval_mode == "never"
    assert metadata.thread_source is ThreadSource.USER
    assert metadata.agent_nickname == "helper"
    assert metadata.agent_role == "reviewer"
    assert metadata.agent_path == "/helper"
    assert metadata.cli_version == "0.0.1"
    assert metadata.git_sha == "abc123"
    assert metadata.git_branch == "main"
    assert metadata.git_origin_url == "https://example.test/repo.git"


def test_turn_context_sets_cwd_when_session_cwd_missing() -> None:
    # Rust crate: codex-state
    # Rust module/test: src/extract.rs::turn_context_sets_cwd_when_session_cwd_missing
    # Behavior contract: turn context fills CWD only when metadata CWD is empty.
    metadata = _metadata()
    metadata.cwd = Path()

    apply_rollout_item(
        metadata,
        _rollout(
            "turn_context",
            {
                "cwd": "/fallback/workspace",
                "model": "gpt-5",
                "effort": ReasoningEffort.HIGH,
                "sandbox_policy": "read-only",
                "approval_policy": "on-request",
            },
        ),
        "test-provider",
    )

    assert metadata.cwd == Path("/fallback/workspace")


def test_session_meta_does_not_set_model_or_reasoning_effort() -> None:
    # Rust crate: codex-state
    # Rust module/test: src/extract.rs::session_meta_does_not_set_model_or_reasoning_effort
    # Behavior contract: session metadata updates session fields but not model/effort.
    metadata = _metadata()

    apply_rollout_item(
        metadata,
        _rollout(
            "session_meta",
            {
                "meta": {
                    "id": THREAD_ID,
                    "source": "cli",
                    "model_provider": "openai",
                    "cli_version": "0.0.0",
                    "cwd": "/workspace",
                },
                "git": None,
            },
        ),
        "test-provider",
    )

    assert metadata.model is None
    assert metadata.reasoning_effort is None


def test_token_count_clamps_negative_usage_and_default_provider_fills_empty_provider() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/extract.rs::apply_event_msg TokenCount branch
    # Behavior contract: token usage is clamped at zero and empty provider is
    # filled from default_provider after any rollout item.
    metadata = _metadata()
    metadata.model_provider = ""

    apply_rollout_item(
        metadata,
        _event("token_count", info={"total_token_usage": {"total_tokens": -42}}),
        "default-provider",
    )

    assert metadata.tokens_used == 0
    assert metadata.model_provider == "default-provider"


def test_rollout_item_affects_thread_metadata_matches_rust_predicate() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/extract.rs::rollout_item_affects_thread_metadata
    # Behavior contract: only session meta, turn context, token count,
    # user-message, and thread-goal events can mutate thread metadata.
    assert rollout_item_affects_thread_metadata(_rollout("session_meta", {})) is True
    assert rollout_item_affects_thread_metadata(_rollout("turn_context", {})) is True
    assert rollout_item_affects_thread_metadata(_event("token_count")) is True
    assert rollout_item_affects_thread_metadata(_event("user_message")) is True
    assert rollout_item_affects_thread_metadata(_event("thread_goal_updated")) is True
    assert rollout_item_affects_thread_metadata(_event("error")) is False
    assert rollout_item_affects_thread_metadata(_rollout("response_item", {})) is False
    assert rollout_item_affects_thread_metadata(_rollout("compacted", {})) is False


def test_user_message_helpers_strip_prefix_and_detect_images() -> None:
    # Rust crate: codex-state
    # Rust module/items: strip_user_message_prefix, user_message_preview
    # Behavior contract: user-message prefix is stripped and image-only messages
    # produce the stable placeholder.
    assert strip_user_message_prefix("  hello  ") == "hello"
    assert strip_user_message_prefix(f"before {USER_MESSAGE_BEGIN} after ") == "after"
    assert user_message_preview({"message": "", "local_images": ["C:/tmp/image.png"]}) == "[Image]"
    assert user_message_preview({"message": "   ", "images": []}) is None
