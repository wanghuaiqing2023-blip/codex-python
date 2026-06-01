import json
import os
import unittest
import uuid
from pathlib import Path

from pycodex.core import (
    SESSIONS_SUBDIR,
    Cursor,
    SessionIndexEntry,
    SessionMeta,
    append_event_msg_to_rollout,
    append_response_item_to_rollout,
    append_session_index_entry,
    append_thread_name,
    append_turn_context_to_rollout,
    append_turn_to_latest_thread_rollout,
    append_turn_to_thread_rollout,
    append_turn_to_rollout,
    count_session_rollout_files,
    find_session_rollout_containing_response_marker,
    find_archived_thread_path_by_id_str,
    find_thread_meta_by_name_str,
    find_thread_name_by_id,
    find_thread_names_by_ids,
    find_thread_path_by_id_str,
    get_threads,
    get_threads_in_root,
    last_user_image_count_in_rollout,
    materialize_session_rollout,
    parse_cursor,
    parse_timestamp_uuid_from_filename,
    read_event_msgs_from_rollout,
    read_head_for_summary,
    read_model_history_from_rollout,
    read_response_items_from_rollout,
    read_session_meta_line,
    read_thread_item_from_rollout,
    rollout_date_parts,
    session_index_path,
    ThreadSortKey,
)
from pycodex.protocol import EventMsg, TurnAbortReason, TurnAbortedEvent


def workspace_tempdir():
    root = Path.cwd() / "tmp_tests_workspace"
    root.mkdir(exist_ok=True)
    path = root / f"case-{uuid.uuid4()}"
    path.mkdir()
    return path


def session_meta_payload(thread_id: str) -> dict:
    return {
        "id": thread_id,
        "timestamp": "2024-01-01T00-00-00Z",
        "cwd": ".",
        "originator": "test_originator",
        "cli_version": "test_version",
        "source": "cli",
        "thread_source": None,
        "agent_path": None,
        "agent_nickname": None,
        "agent_role": None,
        "model_provider": "test-provider",
        "base_instructions": None,
        "dynamic_tools": None,
        "memory_mode": None,
    }


def write_rollout(path: Path, thread_id: str, extra_lines: list[dict] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "timestamp": "2024-01-01T00-00-00Z",
            "type": "session_meta",
            "payload": session_meta_payload(thread_id),
        }
    ]
    lines.extend(extra_lines or [])
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def write_thread_rollout(
    codex_home: Path,
    timestamp: str,
    thread_id: str,
    message: str | None = "Hello from user",
    source: str = "cli",
    model_provider: str | None = "test-provider",
    cwd: str = ".",
    git: dict | None = None,
) -> Path:
    year, month, day = timestamp[:4], timestamp[5:7], timestamp[8:10]
    path = codex_home / SESSIONS_SUBDIR / year / month / day / f"rollout-{timestamp}-{thread_id}.jsonl"
    payload = session_meta_payload(thread_id)
    payload.update({"timestamp": timestamp, "source": source, "model_provider": model_provider, "cwd": cwd})
    if git is not None:
        payload["git"] = git
    lines = [{"timestamp": timestamp, "type": "session_meta", "payload": payload}]
    if message is not None:
        lines.append(
            {
                "timestamp": timestamp,
                "type": "event_msg",
                "payload": {"type": "user_message", "message": message, "kind": "plain"},
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


class CoreRolloutTests(unittest.TestCase):
    def test_count_session_rollout_files_matches_exec_ephemeral_suite_counting_rule(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        saved = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(saved, thread_id)
        nested = root / SESSIONS_SUBDIR / "custom" / "manual.jsonl"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text("{}\n", encoding="utf-8")
        ignored = root / "archived_sessions" / "archived.jsonl"
        ignored.parent.mkdir(parents=True, exist_ok=True)
        ignored.write_text("{}\n", encoding="utf-8")

        self.assertEqual(count_session_rollout_files(root), 2)
        self.assertEqual(count_session_rollout_files(root / "empty"), 0)

    def test_materialize_session_rollout_respects_ephemeral_flag(self):
        root = workspace_tempdir()
        default_id = str(uuid.uuid4())
        ephemeral_id = str(uuid.uuid4())
        default_meta = SessionMeta(
            id=default_id,
            timestamp="2025-01-02T03:04:05Z",
            cwd=".",
            originator="codex_exec",
            cli_version="test-version",
            source="cli",
            model_provider="openai",
        )
        ephemeral_meta = SessionMeta(
            id=ephemeral_id,
            timestamp="2025-01-02T03:04:06Z",
            cwd=".",
            originator="codex_exec",
            cli_version="test-version",
            source="cli",
            model_provider="openai",
        )

        default_path = materialize_session_rollout(root, default_meta)
        ephemeral_path = materialize_session_rollout(root, ephemeral_meta, ephemeral=True)

        self.assertIsNotNone(default_path)
        assert default_path is not None
        self.assertTrue(default_path.name.startswith("rollout-2025-01-02T03-04-05Z-"))
        self.assertEqual(count_session_rollout_files(root), 1)
        self.assertIsNone(ephemeral_path)
        self.assertEqual(read_session_meta_line(default_path).meta.id, default_id)

    def test_find_session_rollout_containing_response_marker_matches_resume_suite_scan(self):
        root = workspace_tempdir()
        first_id = str(uuid.uuid4())
        second_id = str(uuid.uuid4())
        marker = f"resume-marker-{uuid.uuid4()}"
        first = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{first_id}.jsonl"
        second = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-01-{second_id}.jsonl"
        write_rollout(
            first,
            first_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "response_item",
                    "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "other"}]},
                }
            ],
        )
        write_rollout(
            second,
            second_id,
            [
                {"timestamp": "x", "type": "event_msg", "payload": {"message": marker}},
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": f"contains {marker}"}],
                    },
                },
            ],
        )

        self.assertEqual(find_session_rollout_containing_response_marker(root, marker), second)
        self.assertIsNone(find_session_rollout_containing_response_marker(root, "missing-marker"))

    def test_append_response_item_to_rollout_supports_resume_append_marker_evidence(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        marker = f"resume-append-{uuid.uuid4()}"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(path, thread_id)

        append_response_item_to_rollout(
            path,
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": f"new marker {marker}"}],
            },
            timestamp="2025-01-02T00:00:01Z",
        )

        self.assertEqual(find_session_rollout_containing_response_marker(root, marker), path)
        self.assertEqual(count_session_rollout_files(root), 1)
        self.assertIn(marker, path.read_text(encoding="utf-8"))

    def test_append_event_msg_to_rollout_persists_turn_aborted_event(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(path, thread_id)

        append_event_msg_to_rollout(
            path,
            EventMsg.with_payload(
                "turn_aborted",
                TurnAbortedEvent(
                    turn_id="turn-1",
                    reason=TurnAbortReason.INTERRUPTED,
                ),
            ),
            timestamp="2025-01-02T00:00:01Z",
        )

        line = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(line["type"], "event_msg")
        self.assertEqual(line["payload"]["type"], "turn_aborted")
        self.assertEqual(line["payload"]["turn_id"], "turn-1")
        self.assertEqual(line["payload"]["reason"], "interrupted")
        events = read_event_msgs_from_rollout(path)
        self.assertEqual(events[-1].type, "turn_aborted")
        self.assertEqual(events[-1].payload.turn_id, "turn-1")
        self.assertEqual(events[-1].payload.reason, TurnAbortReason.INTERRUPTED)

    def test_read_event_msgs_from_rollout_skips_invalid_lines_and_respects_max_items(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(path, thread_id)
        with path.open("a", encoding="utf-8", newline="\n") as file:
            file.write("not json\n")
            file.write(json.dumps({"timestamp": "x", "type": "event_msg", "payload": "bad"}) + "\n")
            file.write(json.dumps({"timestamp": "x", "type": "response_item", "payload": {"type": "unknown"}}) + "\n")
            file.write(json.dumps({"timestamp": "x", "type": "event_msg", "payload": {"type": "user_message", "message": "one", "kind": "plain"}}) + "\n")
            file.write(json.dumps({"timestamp": "x", "type": "event_msg", "payload": {"type": "user_message", "message": "two", "kind": "plain"}}) + "\n")

        self.assertEqual(read_event_msgs_from_rollout(path, max_items=0), ())
        events = read_event_msgs_from_rollout(path, max_items=1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, "user_message")
        self.assertEqual(events[0].payload.message, "one")

    def test_last_user_image_count_in_rollout_matches_resume_suite_scan(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "first"},
                            {"type": "input_image", "image_url": "file://one.png"},
                        ],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ignored"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_image", "image_url": "file://two.png"},
                            {"type": "input_image", "image_url": "file://three.png"},
                        ],
                    },
                },
            ],
        )

        self.assertEqual(last_user_image_count_in_rollout(path), 2)
        self.assertEqual(last_user_image_count_in_rollout(root / "missing.jsonl"), 0)

    def test_read_response_items_from_rollout_recovers_resume_history_in_order(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {"timestamp": "x", "type": "response_item", "payload": {"role": "assistant"}},
                "not-a-rollout-dict",
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "first"}],
                    },
                },
                {"timestamp": "ignored", "type": "event_msg", "payload": {"message": "not history"}},
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "second"}],
                    },
                },
            ],
        )

        items = read_response_items_from_rollout(path)

        self.assertEqual([item.role for item in items], ["user", "assistant"])
        self.assertEqual(items[0].content[0].text, "first")
        self.assertEqual(items[1].content[0].text, "second")
        self.assertEqual(len(read_response_items_from_rollout(path, max_items=1)), 1)
        self.assertEqual(read_response_items_from_rollout(root / "missing.jsonl"), ())

    def test_read_model_history_from_rollout_applies_compacted_replacement_history(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "pre compact"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "compacted",
                    "payload": {
                        "message": "summary",
                        "replacement_history": [
                            {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": "summary user"}],
                            },
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "summary assistant"}],
                            },
                        ],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "after compact"}],
                    },
                },
            ],
        )

        items = read_model_history_from_rollout(path)

        self.assertEqual([item.content[0].text for item in items], ["summary user", "summary assistant", "after compact"])

    def test_read_model_history_from_rollout_applies_thread_rollback_events(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "keep user"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "keep assistant"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "drop user"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "drop assistant"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "event_msg",
                    "payload": {"type": "thread_rolled_back", "num_turns": 1},
                },
            ],
        )

        items = read_model_history_from_rollout(path)

        self.assertEqual([item.content[0].text for item in items], ["keep user", "keep assistant"])

    def test_append_turn_to_rollout_supports_resume_append_file_and_image_evidence(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        marker = f"resume-turn-{uuid.uuid4()}"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(path, thread_id)

        append_turn_to_rollout(
            path,
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "resume prompt"},
                    {"type": "input_image", "image_url": "file://resume-one.png"},
                    {"type": "input_image", "image_url": "file://resume-two.png"},
                ],
            },
            (
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": f"resumed answer {marker}"}],
                },
            ),
            timestamp="2025-01-02T00:00:03Z",
        )

        self.assertEqual(find_session_rollout_containing_response_marker(root, marker), path)
        self.assertEqual(last_user_image_count_in_rollout(path), 2)
        self.assertEqual(count_session_rollout_files(root), 1)

    def test_append_turn_context_to_rollout_updates_thread_item_cwd(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        old_cwd = str(root / "old")
        new_cwd = str(root / "new")
        path = write_thread_rollout(root, "2025-01-02T00-00-00", thread_id, cwd=old_cwd)
        with path.open("a", encoding="utf-8", newline="\n") as file:
            for index in range(12):
                file.write(
                    json.dumps(
                        {
                            "timestamp": f"2025-01-02T00:00:{index + 1:02d}Z",
                            "type": "response_item",
                            "payload": {"type": "message", "role": "assistant", "content": []},
                        }
                    )
                    + "\n"
                )

        append_turn_context_to_rollout(path, new_cwd, timestamp="2025-01-02T00:00:04Z")

        self.assertEqual(read_thread_item_from_rollout(path).cwd, Path(new_cwd))

    def test_append_turn_to_thread_rollout_uses_existing_file_by_id(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        marker = f"resume-by-id-{uuid.uuid4()}"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(path, thread_id)

        appended_path = append_turn_to_thread_rollout(
            root,
            thread_id,
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "resume"}]},
            (
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": f"answer {marker}"}],
                },
            ),
            timestamp="2025-01-02T00:00:04Z",
        )

        self.assertEqual(appended_path, path)
        self.assertEqual(find_session_rollout_containing_response_marker(root, marker), path)
        self.assertEqual(count_session_rollout_files(root), 1)
        self.assertIsNone(append_turn_to_thread_rollout(root, "not-a-uuid", None, ()))

    def test_append_turn_to_latest_thread_rollout_respects_cwd_filter_and_all(self):
        root = workspace_tempdir()
        id_a = str(uuid.uuid4())
        id_b = str(uuid.uuid4())
        cwd_a = str(root / "a")
        cwd_b = str(root / "b")
        marker_a = f"resume-last-a-{uuid.uuid4()}"
        marker_b = f"resume-last-b-{uuid.uuid4()}"
        marker_c = f"resume-last-c-{uuid.uuid4()}"
        path_a = write_thread_rollout(root, "2025-01-01T00-00-00", id_a, message="first", cwd=cwd_a)
        path_b = write_thread_rollout(root, "2025-01-02T00-00-00", id_b, message="second", cwd=cwd_b)

        appended_for_cwd = append_turn_to_latest_thread_rollout(
            root,
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "resume cwd"}]},
            (
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": f"cwd match {marker_a}"}],
                },
            ),
            current_cwd=Path(cwd_a),
            timestamp="2025-01-03T00:00:00Z",
        )
        appended_all = append_turn_to_latest_thread_rollout(
            root,
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "resume all"}]},
            (
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": f"all match {marker_b}"}],
                },
            ),
            current_cwd=Path(cwd_a),
            include_all=True,
            timestamp="2025-01-03T00:00:01Z",
        )
        appended_after_cwd_update = append_turn_to_latest_thread_rollout(
            root,
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "resume after all"}]},
            (
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": f"after cwd update {marker_c}"}],
                },
            ),
            current_cwd=Path(cwd_a),
            timestamp="2025-01-03T00:00:02Z",
        )

        self.assertEqual(appended_for_cwd, path_a)
        self.assertEqual(appended_all, path_b)
        self.assertEqual(appended_after_cwd_update, path_b)
        self.assertEqual(read_thread_item_from_rollout(path_b).cwd, Path(cwd_a))
        self.assertEqual(find_session_rollout_containing_response_marker(root, marker_a), path_a)
        self.assertEqual(find_session_rollout_containing_response_marker(root, marker_b), path_b)
        self.assertEqual(find_session_rollout_containing_response_marker(root, marker_c), path_b)
        self.assertEqual(count_session_rollout_files(root), 2)

    def test_rollout_date_parts_extracts_directory_components(self):
        file_name = "rollout-2025-03-01T09-00-00-123.jsonl"

        self.assertEqual(rollout_date_parts(file_name), ("2025", "03", "01"))

    def test_rollout_date_parts_rejects_non_rollout_name(self):
        self.assertIsNone(rollout_date_parts("session-2025-03-01.jsonl"))

    def test_parse_cursor_accepts_rfc3339_and_filename_timestamp(self):
        rfc3339 = parse_cursor("2025-03-04T09:00:00Z")
        filename_style = parse_cursor("2025-03-04T09-00-00")

        self.assertIsInstance(rfc3339, Cursor)
        self.assertEqual(rfc3339.to_json(), "2025-03-04T09:00:00Z")
        self.assertEqual(filename_style.to_json(), "2025-03-04T09:00:00Z")

    def test_parse_cursor_rejects_legacy_pipe_format(self):
        self.assertIsNone(parse_cursor("2025-03-04T09:00:00Z|abc"))

    def test_parse_timestamp_uuid_from_filename_extracts_timestamp_and_uuid(self):
        thread_id = str(uuid.UUID(int=42))

        parsed = parse_timestamp_uuid_from_filename(f"rollout-2025-03-04T09-08-07-{thread_id}.jsonl")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed[0].isoformat(), "2025-03-04T09:08:07+00:00")
        self.assertEqual(parsed[1], thread_id)
        self.assertIsNone(parse_timestamp_uuid_from_filename("rollout-2025-03-04T09-08-07-not-a-uuid.jsonl"))

    def test_read_head_for_summary_keeps_session_meta_and_response_items(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = root / "rollout.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {"timestamp": "x", "type": "compacted", "payload": {"message": "skip"}},
                {"timestamp": "x", "type": "response_item", "payload": {"id": "msg"}},
                {"not": "json"},
            ],
        )

        head = read_head_for_summary(path)

        self.assertEqual(head[0]["id"], thread_id)
        self.assertEqual(head[1], {"id": "msg"})

    def test_read_session_meta_line_requires_first_head_record_to_be_metadata(self):
        root = workspace_tempdir()
        path = root / "rollout.jsonl"
        path.write_text(
            json.dumps({"timestamp": "x", "type": "response_item", "payload": {"id": "msg"}}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "does not start with session metadata"):
            read_session_meta_line(path)

    def test_read_session_meta_line_parses_flattened_metadata_and_git(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = root / "rollout.jsonl"
        payload = session_meta_payload(thread_id)
        payload["git"] = {"commit_hash": "abc", "branch": "main"}
        path.write_text(
            json.dumps({"timestamp": "x", "type": "session_meta", "payload": payload}) + "\n",
            encoding="utf-8",
        )

        meta_line = read_session_meta_line(path)

        self.assertEqual(meta_line.meta.id, thread_id)
        self.assertEqual(meta_line.meta.source, "cli")
        self.assertIsNotNone(meta_line.git)
        self.assertEqual(meta_line.git.branch, "main")

    def test_read_thread_item_from_rollout_parses_preview_and_git_metadata(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = write_thread_rollout(
            root,
            "2025-03-04T09-08-07",
            thread_id,
            message="before\n## My request for Codex: inspect this",
            git={"commit_hash": "abc123", "branch": "main", "repository_url": "https://example.test/repo"},
        )

        item = read_thread_item_from_rollout(path)

        self.assertIsNotNone(item)
        self.assertEqual(item.thread_id, thread_id)
        self.assertEqual(item.preview, "inspect this")
        self.assertEqual(item.first_user_message, "inspect this")
        self.assertEqual(item.cwd, Path("."))
        self.assertEqual(item.git_branch, "main")
        self.assertEqual(item.git_sha, "abc123")
        self.assertEqual(item.git_origin_url, "https://example.test/repo")

    def test_read_thread_item_from_rollout_uses_goal_objective_preview(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = write_thread_rollout(root, "2025-03-04T09-08-07", thread_id, message=None)
        with path.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    {
                        "timestamp": "2025-03-04T09-08-07",
                        "type": "event_msg",
                        "payload": {
                            "type": "thread_goal_updated",
                            "goal": {"objective": "optimize the benchmark"},
                        },
                    }
                )
                + "\n"
            )

        item = read_thread_item_from_rollout(path)

        self.assertIsNotNone(item)
        self.assertEqual(item.preview, "optimize the benchmark")
        self.assertIsNone(item.first_user_message)

    def test_session_index_path_and_append_thread_name(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())

        append_thread_name(root, thread_id, "first")

        self.assertTrue(session_index_path(root).exists())
        self.assertEqual(find_thread_name_by_id(root, thread_id), "first")

    def test_find_thread_name_by_id_prefers_latest_entry(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        append_session_index_entry(root, SessionIndexEntry(thread_id, "first", "2024-01-01T00:00:00Z"))
        append_session_index_entry(root, SessionIndexEntry(thread_id, "second", "2024-01-02T00:00:00Z"))

        self.assertEqual(find_thread_name_by_id(root, thread_id), "second")

    def test_find_thread_names_by_ids_prefers_latest_entry(self):
        root = workspace_tempdir()
        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())
        append_session_index_entry(root, SessionIndexEntry(id1, "first", "2024-01-01T00:00:00Z"))
        append_session_index_entry(root, SessionIndexEntry(id2, "other", "2024-01-01T00:00:00Z"))
        append_session_index_entry(root, SessionIndexEntry(id1, "latest", "2024-01-02T00:00:00Z"))

        self.assertEqual(find_thread_names_by_ids(root, {id1, id2}), {id1: "latest", id2: "other"})

    def test_find_thread_path_by_id_str_requires_uuid_and_searches_sessions(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        rollout = root / SESSIONS_SUBDIR / "2024" / "01" / "01" / f"rollout-2024-01-01T00-00-00-{thread_id}.jsonl"
        write_rollout(rollout, thread_id)

        self.assertEqual(find_thread_path_by_id_str(root, thread_id), rollout)
        self.assertIsNone(find_thread_path_by_id_str(root, "not-a-uuid"))
        self.assertIsNone(find_archived_thread_path_by_id_str(root, thread_id))

    def test_find_thread_meta_by_name_skips_partial_or_historical_entries(self):
        root = workspace_tempdir()
        saved_id = str(uuid.uuid4())
        partial_id = str(uuid.uuid4())
        renamed_id = str(uuid.uuid4())
        rollout_dir = root / SESSIONS_SUBDIR / "2024" / "01" / "01"
        saved_rollout = rollout_dir / f"rollout-2024-01-01T00-00-00-{saved_id}.jsonl"
        partial_rollout = rollout_dir / f"rollout-2024-01-01T00-00-01-{partial_id}.jsonl"
        renamed_rollout = rollout_dir / f"rollout-2024-01-01T00-00-02-{renamed_id}.jsonl"
        write_rollout(saved_rollout, saved_id)
        partial_rollout.parent.mkdir(parents=True, exist_ok=True)
        partial_rollout.write_text("", encoding="utf-8")
        write_rollout(renamed_rollout, renamed_id)
        append_session_index_entry(root, SessionIndexEntry(saved_id, "same", "2024-01-01T00:00:00Z"))
        append_session_index_entry(root, SessionIndexEntry(partial_id, "same", "2024-01-02T00:00:00Z"))
        append_session_index_entry(root, SessionIndexEntry(renamed_id, "same", "2024-01-03T00:00:00Z"))
        append_session_index_entry(root, SessionIndexEntry(renamed_id, "different", "2024-01-04T00:00:00Z"))

        found = find_thread_meta_by_name_str(root, "same")

        self.assertIsNotNone(found)
        self.assertEqual(found[0], saved_rollout)
        self.assertEqual(found[1].meta.id, saved_id)

    def test_get_threads_returns_empty_page_for_missing_root(self):
        root = workspace_tempdir()

        page = get_threads_in_root(root / "missing", page_size=10)

        self.assertEqual(page.items, [])
        self.assertIsNone(page.next_cursor)
        self.assertEqual(page.num_scanned_files, 0)

    def test_get_threads_orders_by_created_at_and_paginates(self):
        root = workspace_tempdir()
        id1 = str(uuid.UUID(int=1))
        id2 = str(uuid.UUID(int=2))
        id3 = str(uuid.UUID(int=3))
        write_thread_rollout(root, "2025-01-01T12-00-00", id1, message="first")
        write_thread_rollout(root, "2025-01-02T12-00-00", id2, message="second")
        write_thread_rollout(root, "2025-01-03T12-00-00", id3, message="third")

        page1 = get_threads(root, page_size=2, allowed_sources=("cli",), model_providers=("test-provider",))
        page2 = get_threads(root, page_size=2, cursor=page1.next_cursor)

        self.assertEqual([item.thread_id for item in page1.items], [id3, id2])
        self.assertEqual([item.preview for item in page1.items], ["third", "second"])
        self.assertIsNotNone(page1.next_cursor)
        self.assertEqual(page1.num_scanned_files, 3)
        self.assertEqual([item.thread_id for item in page2.items], [id1])
        self.assertIsNone(page2.next_cursor)

    def test_get_threads_filters_source_provider_and_cwd(self):
        root = workspace_tempdir()
        allowed_id = str(uuid.uuid4())
        wrong_source_id = str(uuid.uuid4())
        wrong_provider_id = str(uuid.uuid4())
        write_thread_rollout(root, "2025-01-01T12-00-00", allowed_id, model_provider=None, cwd=".")
        write_thread_rollout(root, "2025-01-02T12-00-00", wrong_source_id, source="vscode", cwd=".")
        write_thread_rollout(root, "2025-01-03T12-00-00", wrong_provider_id, model_provider="other", cwd=".")

        page = get_threads(
            root,
            page_size=10,
            allowed_sources=("cli",),
            model_providers=("test-provider",),
            cwd_filters=(Path("."),),
            default_provider="test-provider",
        )

        self.assertEqual([item.thread_id for item in page.items], [allowed_id])

    def test_get_threads_excludes_rollouts_without_preview(self):
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        write_thread_rollout(root, "2025-01-01T12-00-00", thread_id, message=None)

        page = get_threads(root, page_size=10)

        self.assertEqual(page.items, [])

    def test_get_threads_can_sort_by_updated_at(self):
        root = workspace_tempdir()
        older_id = str(uuid.uuid4())
        newer_id = str(uuid.uuid4())
        older_path = write_thread_rollout(root, "2025-01-01T12-00-00", older_id, message="older created")
        newer_path = write_thread_rollout(root, "2025-01-02T12-00-00", newer_id, message="newer created")
        os.utime(older_path, (1_800_000_000, 1_800_000_000))
        os.utime(newer_path, (1_700_000_000, 1_700_000_000))

        page = get_threads(root, page_size=10, sort_key=ThreadSortKey.UPDATED_AT)

        self.assertEqual([item.thread_id for item in page.items], [older_id, newer_id])


if __name__ == "__main__":
    unittest.main()
