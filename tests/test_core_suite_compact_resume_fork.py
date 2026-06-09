"""Rust integration parity for ``core/tests/suite/compact_resume_fork.rs``.

The upstream tests drive a mocked Codex thread through compact, resume, fork,
and rollback operations. These Python parity tests keep the behavior at the
rollout/reconstruction boundary: compacted replacement history must remain the
model-visible prefix across resume/fork-like continuations, second compactions
must become the new resume base, rollback behind compaction must drop the edited
turn while preserving the compacted prefix, and rolled-back context updates must
not duplicate in the follow-up turn.
"""

from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path

from pycodex.rollout import read_model_history_from_rollout, read_rollout_reconstruction_from_rollout
from pycodex.protocol import AskForApproval, CompactedItem, EventMsg, ResponseItem, SandboxPolicy, ThreadRolledBackEvent, TurnContextItem
from pycodex.protocol.models import ContentItem

AFTER_SECOND_RESUME = "AFTER_SECOND_RESUME"
AFTER_ROLLBACK = "AFTER_ROLLBACK"
SUMMARY_TEXT = "SUMMARY_TEXT"
ROLLED_BACK_DEV_INSTRUCTIONS = "ROLLED_BACK_DEV_INSTRUCTIONS"
PRETURN_CONTEXT_DIFF_CWD = "PRETURN_CONTEXT_DIFF_CWD"


def workspace_tempdir() -> Path:
    root = Path.cwd() / "tmp_tests_workspace"
    root.mkdir(exist_ok=True)
    path = root / f"compact-resume-fork-{uuid.uuid4()}"
    path.mkdir()
    return path


def user_msg(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def assistant_msg(text: str) -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


def developer_msg(text: str) -> ResponseItem:
    return ResponseItem.message("developer", (ContentItem.input_text(text),))


def item_texts(items: tuple[ResponseItem, ...]) -> list[str]:
    return [item.content[0].text or "" for item in items if item.type == "message" and item.content]


def user_texts(items: tuple[ResponseItem, ...]) -> list[str]:
    return [item.content[0].text or "" for item in items if item.type == "message" and item.role == "user" and item.content]


def response_item(item: ResponseItem) -> dict:
    return {"type": "response_item", "payload": item.to_mapping()}


def compacted(*items: ResponseItem) -> dict:
    return {
        "type": "compacted",
        "payload": CompactedItem(
            message="",
            replacement_history=tuple(item.to_mapping() for item in items),
        ).to_mapping(),
    }


def rollback(num_turns: int) -> dict:
    return {
        "type": "event_msg",
        "payload": EventMsg.with_payload("thread_rolled_back", ThreadRolledBackEvent(num_turns)).to_mapping(),
    }


def event(kind: str, **payload: object) -> dict:
    body = {"type": kind}
    body.update(payload)
    return {"type": "event_msg", "payload": body}


def turn_context(turn_id: str, *, model: str = "gpt-test", cwd: str = ".") -> dict:
    return {
        "type": "turn_context",
        "payload": TurnContextItem(
            cwd=Path(cwd),
            approval_policy=AskForApproval.NEVER,
            sandbox_policy=SandboxPolicy.read_only(),
            model=model,
            turn_id=turn_id,
        ).to_mapping(),
    }


def write_rollout(lines: list[dict]) -> Path:
    root = workspace_tempdir()
    thread_id = str(uuid.uuid4())
    path = root / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
    session_meta = {
        "timestamp": "2025-01-02T00:00:00Z",
        "type": "session_meta",
        "payload": {
            "id": thread_id,
            "timestamp": "2025-01-02T00:00:00Z",
            "cwd": str(root),
            "originator": "test",
            "cli_version": "test",
            "source": "cli",
            "model_provider": "test-provider",
            "base_instructions": None,
        },
    }
    full_lines = [session_meta]
    for index, line in enumerate(lines, start=1):
        line = dict(line)
        line.setdefault("timestamp", f"2025-01-02T00:00:{index:02d}Z")
        full_lines.append(line)
    path.write_text("\n".join(json.dumps(line, ensure_ascii=False) for line in full_lines) + "\n", encoding="utf-8")
    return path


class CompactResumeForkParityTests(unittest.TestCase):
    def test_compact_resume_and_fork_preserve_model_history_view(self) -> None:
        # Rust test: compact_resume_and_fork_preserve_model_history_view.
        # Contract: after compact, resume and fork continuations keep the
        # compacted replacement history as the model-visible prefix.
        compact_prefix = (user_msg("hello world"), user_msg(SUMMARY_TEXT))
        after_compact = write_rollout([
            response_item(user_msg("hello world")),
            response_item(assistant_msg("FIRST_REPLY")),
            compacted(*compact_prefix),
            response_item(user_msg("AFTER_COMPACT")),
        ])
        after_resume = write_rollout([
            compacted(*compact_prefix),
            response_item(user_msg("AFTER_COMPACT")),
            response_item(user_msg("AFTER_RESUME")),
        ])
        after_fork = write_rollout([
            compacted(*compact_prefix),
            response_item(user_msg("AFTER_COMPACT")),
            response_item(user_msg("AFTER_FORK")),
        ])

        compact_history = read_model_history_from_rollout(after_compact)
        resume_history = read_model_history_from_rollout(after_resume)
        fork_history = read_model_history_from_rollout(after_fork)

        self.assertEqual(user_texts(compact_history), ["hello world", SUMMARY_TEXT, "AFTER_COMPACT"])
        self.assertEqual(resume_history[: len(compact_history)], compact_history)
        self.assertEqual(fork_history[: len(compact_history)], compact_history)
        self.assertEqual(user_texts(resume_history)[-1], "AFTER_RESUME")
        self.assertEqual(user_texts(fork_history)[-1], "AFTER_FORK")

    def test_compact_resume_after_second_compaction_preserves_history(self) -> None:
        # Rust test: compact_resume_after_second_compaction_preserves_history.
        # Contract: a second compaction on the forked branch replaces the resume
        # base, and the next resumed turn appends only the new user message.
        second_prefix = (
            user_msg("hello world"),
            user_msg("AFTER_COMPACT"),
            user_msg("AFTER_RESUME"),
            user_msg("AFTER_FORK"),
            user_msg(SUMMARY_TEXT),
        )
        after_second_compact = write_rollout([
            compacted(*second_prefix),
            response_item(user_msg("AFTER_COMPACT_2")),
        ])
        after_second_resume = write_rollout([
            compacted(*second_prefix),
            response_item(user_msg("AFTER_COMPACT_2")),
            response_item(user_msg(AFTER_SECOND_RESUME)),
        ])

        compact_history = read_model_history_from_rollout(after_second_compact)
        resume_history = read_model_history_from_rollout(after_second_resume)

        self.assertEqual(resume_history[: len(compact_history)], compact_history)
        self.assertEqual(user_texts(compact_history), ["hello world", "AFTER_COMPACT", "AFTER_RESUME", "AFTER_FORK", SUMMARY_TEXT, "AFTER_COMPACT_2"])
        self.assertEqual(user_texts(resume_history)[-1], AFTER_SECOND_RESUME)

    def test_snapshot_rollback_past_compaction_replays_append_only_history(self) -> None:
        # Rust test: snapshot_rollback_past_compaction_replays_append_only_history.
        # Contract: rollback of the post-compaction turn removes that edited
        # turn but keeps the earlier compacted summary/history visible.
        path = write_rollout([
            event("task_started", turn_id="turn-1", model_context_window=128000),
            event("user_message", message="hello world"),
            response_item(user_msg("hello world")),
            response_item(assistant_msg("FIRST_REPLY")),
            event("task_complete", turn_id="turn-1", last_agent_message=None),
            compacted(user_msg("hello world"), user_msg(SUMMARY_TEXT)),
            event("task_started", turn_id="edited-turn", model_context_window=128000),
            event("user_message", message="EDITED_AFTER_COMPACT"),
            response_item(user_msg("EDITED_AFTER_COMPACT")),
            event("task_complete", turn_id="edited-turn", last_agent_message=None),
            rollback(1),
            event("task_started", turn_id="after-rollback-turn", model_context_window=128000),
            event("user_message", message=AFTER_ROLLBACK),
            response_item(user_msg(AFTER_ROLLBACK)),
            event("task_complete", turn_id="after-rollback-turn", last_agent_message=None),
        ])

        history = read_model_history_from_rollout(path)
        texts = user_texts(history)

        self.assertEqual(texts[-1], AFTER_ROLLBACK)
        self.assertIn("hello world", texts)
        self.assertIn(SUMMARY_TEXT, texts)
        self.assertNotIn("EDITED_AFTER_COMPACT", texts)

    def test_snapshot_rollback_followup_turn_trims_context_updates(self) -> None:
        # Rust test: snapshot_rollback_followup_turn_trims_context_updates.
        # Contract: pre-turn settings/context from a rolled-back turn are not
        # replayed twice; the follow-up context is the single latest context.
        path = write_rollout([
            event("task_started", turn_id="turn-1", model_context_window=128000),
            event("user_message", message="turn 1 user"),
            turn_context("turn-1", model="gpt-5.4", cwd="."),
            response_item(user_msg("turn 1 user")),
            response_item(assistant_msg("turn 1 assistant")),
            event("task_complete", turn_id="turn-1", last_agent_message=None),
            event("task_started", turn_id="rolled-back-turn", model_context_window=128000),
            event("user_message", message="turn 2 user"),
            turn_context("rolled-back-turn", model="gpt-5.4", cwd=PRETURN_CONTEXT_DIFF_CWD),
            response_item(developer_msg(ROLLED_BACK_DEV_INSTRUCTIONS)),
            response_item(user_msg(TURN_TWO_USER := "turn 2 user")),
            response_item(assistant_msg("turn 2 assistant")),
            event("task_complete", turn_id="rolled-back-turn", last_agent_message=None),
            rollback(1),
            event("task_started", turn_id="follow-up-turn", model_context_window=128000),
            event("user_message", message="follow-up user"),
            turn_context("follow-up-turn", model="gpt-5.4", cwd=PRETURN_CONTEXT_DIFF_CWD),
            response_item(developer_msg(ROLLED_BACK_DEV_INSTRUCTIONS)),
            response_item(user_msg("follow-up user")),
            event("task_complete", turn_id="follow-up-turn", last_agent_message=None),
        ])

        reconstruction = read_rollout_reconstruction_from_rollout(path)
        texts = item_texts(reconstruction.history)

        self.assertNotIn(TURN_TWO_USER, texts)
        self.assertEqual(texts.count(ROLLED_BACK_DEV_INSTRUCTIONS), 1)
        self.assertEqual(user_texts(reconstruction.history)[-1], "follow-up user")
        self.assertIsNotNone(reconstruction.reference_context_item)
        assert reconstruction.reference_context_item is not None
        self.assertEqual(str(reconstruction.reference_context_item.cwd), PRETURN_CONTEXT_DIFF_CWD)


if __name__ == "__main__":
    unittest.main()
