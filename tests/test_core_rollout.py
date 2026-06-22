import json
import os
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pycodex.core import (
    SESSIONS_SUBDIR,
    Anchor,
    Config,
    Cursor,
    EventPersistenceMode,
    RolloutRecorder,
    RolloutRecorderParams,
    RolloutWriterState,
    RolloutConfig,
    SqliteMetricsRecorder,
    SortDirection,
    SessionIndexEntry,
    SessionMeta,
    append_event_msg_to_rollout,
    append_response_item_to_rollout,
    append_session_index_entry,
    append_thread_name,
    apply_rollout_items,
    bounded_originator_tag_value,
    append_turn_context_to_rollout,
    append_turn_to_latest_thread_rollout,
    append_turn_to_thread_rollout,
    append_turn_to_rollout,
    count_session_rollout_files,
    cursor_to_anchor,
    fill_missing_thread_item_metadata,
    find_rollout_path_by_id,
    find_session_rollout_containing_response_marker,
    first_rollout_content_match_snippet,
    find_archived_thread_path_by_id_str,
    find_thread_meta_by_name_str,
    find_thread_name_by_id,
    find_thread_names_by_ids,
    find_thread_path_by_id_str,
    get_threads,
    get_threads_in_root,
    list_thread_ids_db,
    list_threads_db,
    list_threads_from_state_metadata,
    last_user_image_count_in_rollout,
    materialize_session_rollout,
    parse_cursor,
    parse_timestamp_uuid_from_filename,
    persisted_rollout_items,
    read_event_msgs_from_rollout,
    read_head_for_summary,
    read_repair_rollout_path,
    read_model_history_from_rollout,
    read_rollout_reconstruction_from_rollout,
    read_response_items_from_rollout,
    read_session_meta_line,
    read_thread_item_from_rollout,
    rollout_date_parts,
    search_rollout_paths,
    session_index_path,
    should_persist_event_msg,
    should_persist_response_item,
    should_persist_response_item_for_memories,
    sqlite_metrics_recorder,
    ThreadItem,
    ThreadMetadata,
    ThreadMetadataBuilder,
    ThreadListLayout,
    ThreadSortKey,
    thread_item_from_state_metadata,
    mark_thread_memory_mode_polluted,
    touch_thread_updated_at,
    with_originator,
)
from pycodex.protocol import AgentPath, EventMsg, InterAgentCommunication, SessionSource, ThreadId, TurnAbortReason, TurnAbortedEvent, USER_MESSAGE_BEGIN


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


def inter_agent_assistant_payload(text: str) -> dict:
    communication = InterAgentCommunication(
        author=AgentPath.root(),
        recipient=AgentPath.from_string("/root/worker"),
        other_recipients=(),
        content=text,
        trigger_turn=True,
    )
    return communication.to_response_input_item().to_mapping()


def turn_context_payload(*, turn_id: str | None, model: str, realtime_active: bool | None) -> dict:
    payload = {
        "cwd": ".",
        "approval_policy": "never",
        "sandbox_policy": {"type": "read-only", "network_access": False},
        "model": model,
    }
    if turn_id is not None:
        payload["turn_id"] = turn_id
    if realtime_active is not None:
        payload["realtime_active"] = realtime_active
    return payload


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
    def test_rollout_config_from_view_copies_config_values(self):
        # Rust parity: codex-rollout/src/config.rs::RolloutConfig::from_view.
        root = workspace_tempdir()
        view = {
            "codex_home": root / "codex",
            "sqlite_home": root / "sqlite",
            "cwd": root / "cwd",
            "model_provider_id": "test-provider",
            "generate_memories": True,
        }

        config = RolloutConfig.from_view(view)

        self.assertIs(Config, RolloutConfig)
        self.assertEqual(config.codex_home, root / "codex")
        self.assertEqual(config.sqlite_home, root / "sqlite")
        self.assertEqual(config.cwd, root / "cwd")
        self.assertEqual(config.model_provider_id, "test-provider")
        self.assertTrue(config.generate_memories)

    def test_policy_response_item_persistence_matches_rust(self):
        # Rust parity: codex-rollout/src/policy.rs::should_persist_response_item.
        self.assertTrue(should_persist_response_item({"type": "message", "role": "assistant"}))
        self.assertTrue(should_persist_response_item({"type": "function_call"}))
        self.assertFalse(should_persist_response_item({"type": "compaction_trigger"}))
        self.assertFalse(should_persist_response_item({"type": "other"}))

    def test_policy_memory_response_item_persistence_matches_rust(self):
        # Rust parity: codex-rollout/src/policy.rs::should_persist_response_item_for_memories.
        self.assertTrue(should_persist_response_item_for_memories({"type": "message", "role": "user"}))
        self.assertFalse(should_persist_response_item_for_memories({"type": "message", "role": "developer"}))
        self.assertTrue(should_persist_response_item_for_memories({"type": "function_call_output"}))
        self.assertFalse(should_persist_response_item_for_memories({"type": "reasoning"}))

    def test_policy_event_persistence_modes_match_rust(self):
        # Rust parity: codex-rollout/src/policy.rs::should_persist_event_msg.
        self.assertTrue(should_persist_event_msg({"type": "user_message"}, EventPersistenceMode.LIMITED))
        self.assertFalse(should_persist_event_msg({"type": "exec_command_end"}, EventPersistenceMode.LIMITED))
        self.assertTrue(should_persist_event_msg({"type": "exec_command_end"}, EventPersistenceMode.EXTENDED))
        self.assertFalse(should_persist_event_msg({"type": "warning"}, EventPersistenceMode.EXTENDED))
        self.assertTrue(should_persist_event_msg({"type": "item_completed", "item": {"type": "plan"}}, "limited"))
        self.assertFalse(should_persist_event_msg({"type": "item_completed", "item": {"type": "message"}}, "extended"))

    def test_policy_persisted_rollout_items_sanitizes_extended_exec_output(self):
        # Rust parity: codex-rollout/src/policy.rs::persisted_rollout_items extended sanitization.
        long_output = "x" * 10050
        items = [
            {"type": "event_msg", "payload": {"type": "warning", "message": "skip"}},
            {
                "type": "event_msg",
                "payload": {
                    "type": "exec_command_end",
                    "aggregated_output": long_output,
                    "stdout": "stdout",
                    "stderr": "stderr",
                    "formatted_output": "formatted",
                },
            },
            {"type": "response_item", "payload": {"type": "compaction_trigger"}},
            {"type": "turn_context", "payload": {"cwd": "."}},
        ]

        persisted = persisted_rollout_items(items, EventPersistenceMode.EXTENDED)

        self.assertEqual([item["type"] for item in persisted], ["event_msg", "turn_context"])
        payload = persisted[0]["payload"]
        self.assertEqual(payload["type"], "exec_command_end")
        self.assertEqual(len(payload["aggregated_output"]), 10000)
        self.assertEqual(payload["stdout"], "")
        self.assertEqual(payload["stderr"], "")
        self.assertEqual(payload["formatted_output"], "")

    def test_search_rollout_paths_scans_sessions_and_archived_roots(self):
        # Rust parity: codex-rollout/src/search.rs::search_rollout_paths fallback scan.
        root = workspace_tempdir()
        sessions_id = str(uuid.uuid4())
        archived_id = str(uuid.uuid4())
        sessions_path = root / SESSIONS_SUBDIR / "2025" / "01" / "01" / f"rollout-2025-01-01T00-00-00-{sessions_id}.jsonl"
        archived_path = root / "archived_sessions" / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{archived_id}.jsonl"
        write_rollout(
            sessions_path,
            sessions_id,
            [{"timestamp": "2025-01-01T00:00:00Z", "type": "event_msg", "payload": {"type": "user_message", "message": "Find Quoted Needle", "kind": "plain"}}],
        )
        write_rollout(
            archived_path,
            archived_id,
            [{"timestamp": "2025-01-02T00:00:00Z", "type": "event_msg", "payload": {"type": "user_message", "message": "archived quoted needle", "kind": "plain"}}],
        )

        self.assertEqual(search_rollout_paths(None, root, False, "quoted needle"), {sessions_path})
        self.assertEqual(search_rollout_paths(None, root, True, "QUOTED NEEDLE"), {archived_path})
        self.assertEqual(search_rollout_paths(None, root / "missing", False, "needle"), set())

    def test_first_rollout_content_match_snippet_extracts_conversation_text(self):
        # Rust parity: codex-rollout/src/search.rs::first_rollout_content_match_snippet.
        root = workspace_tempdir()
        path = root / "rollout.jsonl"
        lines = [
            {"timestamp": "2025-01-01T00:00:00Z", "type": "session_meta", "payload": session_meta_payload(str(uuid.uuid4()))},
            {
                "timestamp": "2025-01-01T00:00:01Z",
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": f"ignored prefix {USER_MESSAGE_BEGIN}\nhello   Needle   with\nspacing",
                    "kind": "plain",
                },
            },
            {
                "timestamp": "2025-01-01T00:00:02Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "Needle ignored"}]},
            },
        ]
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

        self.assertEqual(first_rollout_content_match_snippet(path, "needle"), "hello Needle with spacing")

    def test_sqlite_metrics_recorder_appends_bounded_originator_tag(self):
        # Rust parity: codex-rollout/src/sqlite_metrics.rs::recorder and with_originator.
        calls: list[tuple[str, str, object, list[tuple[str, str]]]] = []

        class Metrics:
            def counter(self, name: str, inc: int, tags: list[tuple[str, str]]) -> None:
                calls.append(("counter", name, inc, tags))

            def record_duration(self, name: str, duration: object, tags: list[tuple[str, str]]) -> None:
                calls.append(("duration", name, duration, tags))

        recorder = sqlite_metrics_recorder(Metrics(), "codex_exec")
        unknown = SqliteMetricsRecorder(Metrics(), "not a known originator!")

        recorder.counter("db.count", 2, [("operation", "open")])
        unknown.record_duration("db.duration", 1.5, [])

        self.assertEqual(bounded_originator_tag_value("codex_exec"), "codex_exec")
        self.assertEqual(bounded_originator_tag_value("not a known originator!"), "other")
        self.assertEqual(
            with_originator([("operation", "open")], "codex_exec"),
            [("operation", "open"), ("originator", "codex_exec")],
        )
        self.assertEqual(calls[0], ("counter", "db.count", 2, [("operation", "open"), ("originator", "codex_exec")]))
        self.assertEqual(calls[1], ("duration", "db.duration", 1.5, [("originator", "other")]))

    def test_state_db_list_thread_ids_maps_cursor_filters_and_errors(self):
        # Rust parity: codex-rollout/src/state_db.rs::cursor_to_anchor and list_thread_ids_db.
        root = workspace_tempdir()
        cursor = Cursor(datetime(2025, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc))
        calls: list[tuple[object, ...]] = []

        class Runtime:
            def codex_home(self) -> Path:
                return root

            def list_thread_ids(
                self,
                page_size: int,
                anchor: Anchor | None,
                sort_key: str,
                allowed_sources: list[str],
                model_providers: list[str] | None,
                archived_only: bool,
            ) -> list[str]:
                calls.append((page_size, anchor, sort_key, allowed_sources, model_providers, archived_only))
                return ["thread-a"]

        class FailingRuntime(Runtime):
            def list_thread_ids(self, *args: object) -> list[str]:
                raise OSError("db unavailable")

        anchor = cursor_to_anchor(cursor)
        result = list_thread_ids_db(
            Runtime(),
            root,
            10,
            cursor,
            ThreadSortKey.UPDATED_AT,
            (SessionSource.cli(), SessionSource.custom_source("atlas")),
            ("provider-a",),
            True,
            "test-stage",
        )

        self.assertEqual(result, ["thread-a"])
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor.ts.microsecond, 123000)
        self.assertEqual(calls[0][0], 10)
        self.assertEqual(calls[0][1], anchor)
        self.assertEqual(calls[0][2], "updated_at")
        self.assertEqual(calls[0][3], ["cli", '{"custom":"atlas"}'])
        self.assertEqual(calls[0][4], ["provider-a"])
        self.assertEqual(calls[0][5], True)
        self.assertIsNone(list_thread_ids_db(None, root, 10, None, ThreadSortKey.CREATED_AT, (), None, False, "none"))
        self.assertIsNone(list_thread_ids_db(FailingRuntime(), root, 10, None, ThreadSortKey.CREATED_AT, (), None, False, "fail"))

    def test_state_db_list_threads_maps_filters_and_drops_stale_paths(self):
        # Rust parity: codex-rollout/src/state_db.rs::list_threads_db.
        root = workspace_tempdir()
        cwd = root / "cwd"
        cwd.mkdir()
        valid_path = root / SESSIONS_SUBDIR / "2025" / "01" / "01" / f"rollout-2025-01-01T00-00-00-{uuid.uuid4()}.jsonl"
        write_rollout(valid_path, str(uuid.uuid4()))
        stale_path = root / SESSIONS_SUBDIR / "2099" / "01" / "01" / f"rollout-2099-01-01T00-00-00-{uuid.uuid4()}.jsonl"
        calls: list[tuple[int, dict[str, object]]] = []
        deleted: list[str] = []

        class Page:
            def __init__(self) -> None:
                self.items = [
                    {"id": "valid", "rollout_path": valid_path},
                    {"id": "stale", "rollout_path": stale_path},
                ]
                self.next_cursor = None

        class Runtime:
            def codex_home(self) -> Path:
                return root

            def list_threads(self, page_size: int, options: dict[str, object]) -> Page:
                calls.append((page_size, options))
                return Page()

            def delete_thread(self, thread_id: str) -> None:
                deleted.append(thread_id)

        page = list_threads_db(
            Runtime(),
            root,
            25,
            None,
            ThreadSortKey.CREATED_AT,
            SortDirection.DESC,
            (SessionSource.cli(),),
            None,
            (cwd,),
            False,
            "needle",
        )

        self.assertIsNotNone(page)
        self.assertEqual([item["id"] for item in page.items], ["valid"])
        self.assertEqual(deleted, ["stale"])
        self.assertEqual(calls[0][0], 25)
        options = calls[0][1]
        self.assertEqual(options["archived_only"], False)
        self.assertEqual(options["allowed_sources"], ["cli"])
        self.assertIsNone(options["model_providers"])
        self.assertEqual(options["cwd_filters"], [cwd.resolve(strict=False)])
        self.assertIsNone(options["anchor"])
        self.assertEqual(options["sort_key"], "created_at")
        self.assertEqual(options["sort_direction"], "desc")
        self.assertEqual(options["search_term"], "needle")
        self.assertIsNone(list_threads_db(None, root, 1, None, ThreadSortKey.CREATED_AT, SortDirection.ASC, (), None, None, False, None))

    def test_state_db_small_adapters_forward_and_swallow_errors(self):
        # Rust parity: codex-rollout/src/state_db.rs find_rollout_path_by_id,
        # mark_thread_memory_mode_polluted, and touch_thread_updated_at.
        root = workspace_tempdir()
        rollout_path = root / "rollout.jsonl"
        touched_at = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        calls: list[tuple[str, object, object]] = []

        class Memories:
            def mark_thread_memory_mode_polluted(self, thread_id: str) -> None:
                calls.append(("memory", thread_id, None))

        class Runtime:
            def __init__(self, fail: bool = False) -> None:
                self.fail = fail

            def find_rollout_path_by_id(self, thread_id: str, archived_only: bool | None) -> Path | None:
                calls.append(("find", thread_id, archived_only))
                if self.fail:
                    raise OSError("db unavailable")
                return rollout_path

            def memories(self) -> Memories:
                if self.fail:
                    raise OSError("db unavailable")
                return Memories()

            def touch_thread_updated_at(self, thread_id: str, updated_at: datetime) -> bool:
                calls.append(("touch", thread_id, updated_at))
                if self.fail:
                    raise OSError("db unavailable")
                return True

        runtime = Runtime()
        failing = Runtime(fail=True)

        self.assertEqual(find_rollout_path_by_id(runtime, "thread-a", True, "find-stage"), rollout_path)
        mark_thread_memory_mode_polluted(runtime, "thread-a", "memory-stage")
        self.assertTrue(touch_thread_updated_at(runtime, "thread-a", touched_at, "touch-stage"))
        self.assertEqual(
            calls,
            [
                ("find", "thread-a", True),
                ("memory", "thread-a", None),
                ("touch", "thread-a", touched_at),
            ],
        )
        self.assertIsNone(find_rollout_path_by_id(None, "thread-a", None, "missing"))
        self.assertIsNone(find_rollout_path_by_id(failing, "thread-a", None, "failing"))
        mark_thread_memory_mode_polluted(None, "thread-a", "missing")
        mark_thread_memory_mode_polluted(failing, "thread-a", "failing")
        self.assertFalse(touch_thread_updated_at(None, "thread-a", touched_at, "missing"))
        self.assertFalse(touch_thread_updated_at(runtime, None, touched_at, "missing-thread"))
        self.assertFalse(touch_thread_updated_at(failing, "thread-a", touched_at, "failing"))

    def test_state_db_read_repair_rollout_path_fast_path_updates_existing_metadata(self):
        # Rust parity: codex-rollout/src/state_db.rs::read_repair_rollout_path fast path.
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        old_path = root / "old.jsonl"
        new_path = root / SESSIONS_SUBDIR / "2025" / "01" / "01" / f"rollout-2025-01-01T00-00-00-{thread_id}.jsonl"
        metadata = ThreadMetadata(
            id=thread_id,
            rollout_path=old_path,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            source="cli",
            model_provider="test-provider",
            cwd=root / "cwd" / ".." / "cwd",
            cli_version="test",
            first_user_message="hello",
            preview="hello",
        )
        upserts: list[ThreadMetadata] = []
        test_case = self

        class Runtime:
            def get_thread(self, value: str) -> ThreadMetadata | None:
                test_case.assertEqual(value, thread_id)
                return metadata

            def upsert_thread(self, value: ThreadMetadata) -> None:
                upserts.append(value)

        read_repair_rollout_path(Runtime(), thread_id, True, new_path)

        self.assertEqual(len(upserts), 1)
        self.assertEqual(upserts[0].rollout_path, new_path)
        self.assertEqual(upserts[0].cwd, (root / "cwd").resolve(strict=False))
        self.assertEqual(upserts[0].archived_at, metadata.updated_at)

    def test_state_db_read_repair_rollout_path_slow_path_rebuilds_missing_row(self):
        # Rust parity: codex-rollout/src/state_db.rs::read_repair_rollout_path slow path.
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        rollout_path = write_thread_rollout(
            root,
            "2025-01-03T13-00-00",
            thread_id,
            message="Hello from repaired rollout",
            source="cli",
            model_provider="test-provider",
            cwd=str(root / "cwd"),
        )
        upserts: list[ThreadMetadata] = []
        test_case = self

        class Runtime:
            def get_thread(self, value: str) -> ThreadMetadata | None:
                test_case.assertEqual(value, thread_id)
                return None

            def upsert_thread(self, value: ThreadMetadata) -> None:
                upserts.append(value)

        read_repair_rollout_path(Runtime(), thread_id, False, rollout_path, default_provider="fallback-provider")

        self.assertEqual(len(upserts), 1)
        self.assertEqual(upserts[0].id, thread_id)
        self.assertEqual(upserts[0].rollout_path, rollout_path)
        self.assertEqual(upserts[0].cwd, (root / "cwd").resolve(strict=False))
        self.assertIsNone(upserts[0].archived_at)

    def test_state_db_apply_rollout_items_normalizes_builder_and_falls_back_safely(self):
        # Rust parity: codex-rollout/src/state_db.rs::apply_rollout_items.
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        rollout_path = root / SESSIONS_SUBDIR / "2025" / "01" / "01" / f"rollout-2025-01-01T00-00-00-{thread_id}.jsonl"
        builder = ThreadMetadataBuilder(
            id=thread_id,
            rollout_path=root / "old.jsonl",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            cwd=root / "cwd" / ".." / "cwd",
        )
        items = [{"type": "event_msg", "payload": {"type": "agent_message", "message": "hello"}}]
        calls: list[tuple[ThreadMetadataBuilder, list[dict], str | None, datetime | None]] = []
        updated_at = datetime(2025, 1, 2, tzinfo=timezone.utc)

        class Runtime:
            def __init__(self, fail: bool = False) -> None:
                self.fail = fail

            def apply_rollout_items(
                self,
                value: ThreadMetadataBuilder,
                applied_items: list[dict],
                memory_mode: str | None,
                override: datetime | None,
            ) -> None:
                if self.fail:
                    raise OSError("db unavailable")
                calls.append((value, applied_items, memory_mode, override))

        apply_rollout_items(Runtime(), rollout_path, "fallback-provider", builder, items, "explicit", "disabled", updated_at)
        explicit_builder = calls[0][0]

        self.assertEqual(explicit_builder.rollout_path, rollout_path)
        self.assertEqual(explicit_builder.cwd, (root / "cwd").resolve(strict=False))
        self.assertEqual(explicit_builder.model_provider, "fallback-provider")
        self.assertEqual(calls[0][1], items)
        self.assertEqual(calls[0][2], "disabled")
        self.assertEqual(calls[0][3], updated_at)
        self.assertIsNone(builder.model_provider)
        self.assertEqual(builder.rollout_path, root / "old.jsonl")

        inferred_id = str(uuid.uuid4())
        inferred_path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{inferred_id}.jsonl"
        inferred_payload = session_meta_payload(inferred_id)
        inferred_payload["timestamp"] = "2024-01-01T00-00-00"
        inferred_item = {"type": "session_meta", "payload": inferred_payload}
        apply_rollout_items(Runtime(), inferred_path, "fallback-provider", None, [inferred_item], "inferred")

        inferred_builder = calls[1][0]
        self.assertEqual(inferred_builder.id, inferred_id)
        self.assertEqual(inferred_builder.rollout_path, inferred_path)
        self.assertEqual(inferred_builder.model_provider, "test-provider")

        apply_rollout_items(Runtime(), root / "invalid-name.jsonl", "fallback-provider", None, [], "missing-builder")
        apply_rollout_items(Runtime(fail=True), rollout_path, "fallback-provider", builder, items, "failing")
        self.assertEqual(len(calls), 2)

    def test_core_rollout_recorder_reexport_create_record_and_resume_history(self):
        # Rust source: codex-rs/core/src/rollout.rs re-exports
        # codex_rollout::{RolloutRecorder, RolloutRecorderParams}.
        # Rust behavior source: codex-rs/rollout/src/recorder.rs.
        root = workspace_tempdir()
        thread_id = ThreadId.new()
        config = type(
            "Config",
            (),
            {
                "codex_home": root,
                "sqlite_home": root,
                "cwd": root,
                "model_provider_id": "test-provider",
                "generate_memories": True,
            },
        )()
        params = RolloutRecorderParams.new(
            thread_id,
            None,
            SessionSource.exec(),
            None,
            base_instructions={},
            dynamic_tools=(),
        )

        recorder = RolloutRecorder.new(config, params)
        recorder.persist()
        recorder.record_canonical_items(
            (
                {
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "hello", "kind": "plain"},
                },
            )
        )
        recorder.flush()

        items, loaded_thread_id, parse_errors = RolloutRecorder.load_rollout_items(recorder.rollout_path)
        history = RolloutRecorder.get_rollout_history(recorder.rollout_path)
        resumed = RolloutRecorder.new(config, RolloutRecorderParams.resume(recorder.rollout_path))

        self.assertEqual(loaded_thread_id, thread_id)
        self.assertEqual(parse_errors, 0)
        self.assertEqual(items[0].type, "session_meta")
        self.assertEqual(items[1].type, "event_msg")
        self.assertEqual(history.type, "Resumed")
        self.assertIsNotNone(history.resumed)
        self.assertEqual(history.resumed.conversation_id, thread_id)
        self.assertEqual(history.resumed.rollout_path, recorder.rollout_path)
        self.assertEqual(resumed.rollout_path, recorder.rollout_path)

    def test_load_rollout_items_skips_legacy_ghost_snapshot_lines(self):
        # Rust source: codex-rs/rollout/src/recorder_tests.rs::load_rollout_items_skips_legacy_ghost_snapshot_lines.
        root = workspace_tempdir()
        path = root / "rollout.jsonl"
        thread_id = str(uuid.uuid4())
        ts = "2025-01-03T12:00:00Z"
        lines = [
            {
                "timestamp": ts,
                "type": "session_meta",
                "payload": {
                    "id": thread_id,
                    "timestamp": ts,
                    "cwd": ".",
                    "originator": "test_originator",
                    "cli_version": "test_version",
                    "source": "cli",
                    "model_provider": "test-provider",
                },
            },
            {
                "timestamp": ts,
                "type": "response_item",
                "payload": {
                    "type": "ghost_snapshot",
                    "ghost_commit": {
                        "id": "deadbeef",
                        "preexisting_untracked_dirs": [],
                        "preexisting_untracked_files": [],
                    },
                },
            },
            {
                "timestamp": ts,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hello"}],
                },
            },
        ]
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

        items, loaded_thread_id, parse_errors = RolloutRecorder.load_rollout_items(path)

        self.assertEqual(loaded_thread_id, ThreadId.from_string(thread_id))
        self.assertEqual(parse_errors, 0)
        self.assertEqual([item.type for item in items], ["session_meta", "response_item"])
        self.assertEqual(items[1].payload["type"], "message")

    def test_load_rollout_items_preserves_legacy_guardian_assessment_lines(self):
        # Rust source: codex-rs/rollout/src/recorder_tests.rs::load_rollout_items_preserves_legacy_guardian_assessment_lines.
        root = workspace_tempdir()
        path = root / "rollout.jsonl"
        thread_id = str(uuid.uuid4())
        ts = "2025-01-03T12:00:00Z"
        lines = [
            {
                "timestamp": ts,
                "type": "session_meta",
                "payload": {
                    "id": thread_id,
                    "timestamp": ts,
                    "cwd": ".",
                    "originator": "test_originator",
                    "cli_version": "test_version",
                    "source": "cli",
                    "model_provider": "test-provider",
                },
            },
            {
                "timestamp": ts,
                "type": "event_msg",
                "payload": {
                    "type": "guardian_assessment",
                    "id": "guardian-1",
                    "turn_id": "turn-1",
                    "status": "in_progress",
                    "action": {
                        "type": "command",
                        "source": "shell",
                        "command": "rm -rf /tmp/guardian",
                        "cwd": "C:\\tmp" if os.name == "nt" else "/tmp",
                    },
                },
            },
        ]
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

        items, loaded_thread_id, parse_errors = RolloutRecorder.load_rollout_items(path)

        self.assertEqual(loaded_thread_id, ThreadId.from_string(thread_id))
        self.assertEqual(parse_errors, 0)
        self.assertEqual([item.type for item in items], ["session_meta", "event_msg"])
        assessment = items[1].payload.payload
        self.assertEqual(assessment.id, "guardian-1")
        self.assertEqual(assessment.turn_id, "turn-1")
        self.assertEqual(assessment.started_at_ms, 0)

    def test_load_rollout_items_filters_legacy_ghost_snapshots_from_compaction_history(self):
        # Rust source: codex-rs/rollout/src/recorder_tests.rs::load_rollout_items_filters_legacy_ghost_snapshots_from_compaction_history.
        root = workspace_tempdir()
        path = root / "rollout.jsonl"
        thread_id = str(uuid.uuid4())
        ts = "2025-01-03T12:00:00Z"
        lines = [
            {
                "timestamp": ts,
                "type": "session_meta",
                "payload": {
                    "id": thread_id,
                    "timestamp": ts,
                    "cwd": ".",
                    "originator": "test_originator",
                    "cli_version": "test_version",
                    "source": "cli",
                    "model_provider": "test-provider",
                },
            },
            {
                "timestamp": ts,
                "type": "compacted",
                "payload": {
                    "message": "summary",
                    "replacement_history": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "kept"}],
                        },
                        {
                            "type": "ghost_snapshot",
                            "ghost_commit": {
                                "id": "deadbeef",
                                "preexisting_untracked_dirs": [],
                                "preexisting_untracked_files": [],
                            },
                        },
                    ],
                },
            },
        ]
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

        items, loaded_thread_id, parse_errors = RolloutRecorder.load_rollout_items(path)

        self.assertEqual(loaded_thread_id, ThreadId.from_string(thread_id))
        self.assertEqual(parse_errors, 0)
        self.assertEqual([item.type for item in items], ["session_meta", "compacted"])
        replacement_history = items[1].payload.replacement_history
        self.assertIsNotNone(replacement_history)
        self.assertEqual(len(replacement_history), 1)
        self.assertEqual(replacement_history[0]["type"], "message")

    def test_recorder_materializes_on_flush_with_pending_items(self):
        # Rust source: codex-rs/rollout/src/recorder_tests.rs::recorder_materializes_on_flush_with_pending_items.
        root = workspace_tempdir()
        thread_id = ThreadId.new()
        config = type(
            "Config",
            (),
            {
                "codex_home": root,
                "sqlite_home": root,
                "cwd": root,
                "model_provider_id": "test-provider",
                "generate_memories": True,
            },
        )()
        recorder = RolloutRecorder.new(
            config,
            RolloutRecorderParams.new(
                thread_id,
                None,
                SessionSource.exec(),
                None,
                base_instructions={},
                dynamic_tools=(),
            ),
        )

        self.assertFalse(recorder.rollout_path.exists())

        recorder.record_canonical_items(
            (
                {
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "buffered-event"},
                },
            )
        )
        recorder.flush()
        self.assertTrue(recorder.rollout_path.exists())

        recorder.record_canonical_items(
            (
                {
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "first-user-message", "kind": "plain"},
                },
            )
        )
        recorder.flush()
        recorder.persist()
        recorder.persist()

        text = recorder.rollout_path.read_text(encoding="utf-8")
        self.assertIn('"type":"session_meta"', text)
        self.assertIn("buffered-event", text)
        self.assertIn("first-user-message", text)

    def test_persist_reports_filesystem_error_and_retries_buffered_items(self):
        # Rust source: codex-rs/rollout/src/recorder_tests.rs
        # persist_reports_filesystem_error_and_retries_buffered_items.
        root = workspace_tempdir()
        thread_id = ThreadId.new()
        config = type(
            "Config",
            (),
            {
                "codex_home": root,
                "sqlite_home": root,
                "cwd": root,
                "model_provider_id": "test-provider",
                "generate_memories": True,
            },
        )()
        recorder = RolloutRecorder.new(
            config,
            RolloutRecorderParams.new(
                thread_id,
                None,
                SessionSource.exec(),
                None,
                base_instructions={},
                dynamic_tools=(),
            ),
        )
        rollout_path = recorder.rollout_path

        recorder.record_canonical_items(
            (
                {
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "buffered-before-persist"},
                },
            )
        )
        sessions_blocker_path = root / SESSIONS_SUBDIR
        sessions_blocker_path.write_text("", encoding="utf-8")

        with self.assertRaises(OSError):
            recorder.persist()
        self.assertFalse(rollout_path.exists())

        sessions_blocker_path.unlink()
        recorder.flush()
        text = rollout_path.read_text(encoding="utf-8")
        self.assertIn("buffered-before-persist", text)

    def test_writer_state_retries_write_error_before_reporting_flush_success(self):
        # Rust source: codex-rs/rollout/src/recorder_tests.rs
        # writer_state_retries_write_error_before_reporting_flush_success.
        root = workspace_tempdir()
        rollout_path = root / "rollout.jsonl"
        rollout_path.write_text("", encoding="utf-8")
        with rollout_path.open("r", encoding="utf-8") as read_only_file:
            state = RolloutWriterState(read_only_file, rollout_path, cwd=root)
            state.add_items(
                (
                    {
                        "type": "event_msg",
                        "payload": {"type": "agent_message", "message": "queued-after-writer-error"},
                    },
                )
            )
            state.flush()

        text_after_retry = rollout_path.read_text(encoding="utf-8")
        self.assertIn("queued-after-writer-error", text_after_retry)

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

    def test_read_model_history_from_rollout_rollback_counts_inter_agent_assistant_turns(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: reconstruct_history_rollback_counts_inter_agent_assistant_turns
        # Contract: session.rollout_reconstruction.history_rollback
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
                        "content": [{"type": "input_text", "text": "turn 1 user"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "turn 1 assistant"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "response_item",
                    "payload": inter_agent_assistant_payload("continue"),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "worker reply"}],
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

        self.assertEqual([item.content[0].text for item in items], ["turn 1 user", "turn 1 assistant"])

    def test_read_rollout_reconstruction_bare_turn_context_does_not_hydrate_metadata(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: record_initial_history_resumed_bare_turn_context_does_not_hydrate_previous_turn_settings
        # Contract: session.rollout_reconstruction.metadata_hydration
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(
                        turn_id="bare-turn-context",
                        model="previous-rollout-model",
                        realtime_active=True,
                    ),
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertEqual(reconstruction.history, ())
        self.assertIsNone(reconstruction.previous_turn_settings)
        self.assertIsNone(reconstruction.reference_context_item)

    def test_read_rollout_reconstruction_hydrates_metadata_from_lifecycle_turn_with_missing_context_id(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: record_initial_history_resumed_hydrates_previous_turn_settings_from_lifecycle_turn_with_missing_turn_context_id
        # Contract: session.rollout_reconstruction.metadata_hydration
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        turn_id = "lifecycle-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "seed"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(
                        turn_id=None,
                        model="previous-rollout-model",
                        realtime_active=True,
                    ),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": turn_id, "last_agent_message": None},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertIsNotNone(reconstruction.previous_turn_settings)
        self.assertEqual(reconstruction.previous_turn_settings.model, "previous-rollout-model")
        self.assertEqual(reconstruction.previous_turn_settings.realtime_active, True)
        self.assertIsNotNone(reconstruction.reference_context_item)
        self.assertIsNone(reconstruction.reference_context_item.turn_id)
        self.assertEqual(reconstruction.reference_context_item.model, "previous-rollout-model")

    def test_read_rollout_reconstruction_rollback_keeps_metadata_in_sync_for_completed_turns(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: reconstruct_history_rollback_keeps_history_and_metadata_in_sync_for_completed_turns
        # Contract: session.rollout_reconstruction.rollback_metadata
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        first_turn_id = "surviving-turn"
        rolled_back_turn_id = "rolled-back-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": first_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "turn 1 user"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=first_turn_id, model="surviving-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "turn 1 user"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "turn 1 assistant"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:05Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": first_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:06Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": rolled_back_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:07Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "turn 2 user"},
                },
                {
                    "timestamp": "2025-01-02T00:00:08Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(
                        turn_id=rolled_back_turn_id,
                        model="rolled-back-model",
                        realtime_active=False,
                    ),
                },
                {
                    "timestamp": "2025-01-02T00:00:09Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "turn 2 user"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:10Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "turn 2 assistant"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:11Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": rolled_back_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:12Z",
                    "type": "event_msg",
                    "payload": {"type": "thread_rolled_back", "num_turns": 1},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertEqual([item.content[0].text for item in reconstruction.history], ["turn 1 user", "turn 1 assistant"])
        self.assertIsNotNone(reconstruction.previous_turn_settings)
        self.assertEqual(reconstruction.previous_turn_settings.model, "surviving-model")
        self.assertEqual(reconstruction.previous_turn_settings.realtime_active, True)
        self.assertIsNotNone(reconstruction.reference_context_item)
        self.assertEqual(reconstruction.reference_context_item.turn_id, first_turn_id)
        self.assertEqual(reconstruction.reference_context_item.model, "surviving-model")

    def test_read_rollout_reconstruction_rollback_keeps_metadata_in_sync_for_incomplete_turn(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: reconstruct_history_rollback_keeps_history_and_metadata_in_sync_for_incomplete_turn
        # Contract: session.rollout_reconstruction.rollback_metadata
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        first_turn_id = "surviving-turn"
        incomplete_turn_id = "incomplete-rolled-back-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": first_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "turn 1 user"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=first_turn_id, model="surviving-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "turn 1 user"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "turn 1 assistant"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:05Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": first_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:06Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": incomplete_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:07Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "turn 2 user"},
                },
                {
                    "timestamp": "2025-01-02T00:00:08Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "turn 2 user"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:09Z",
                    "type": "event_msg",
                    "payload": {"type": "thread_rolled_back", "num_turns": 1},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertEqual([item.content[0].text for item in reconstruction.history], ["turn 1 user", "turn 1 assistant"])
        self.assertIsNotNone(reconstruction.previous_turn_settings)
        self.assertEqual(reconstruction.previous_turn_settings.model, "surviving-model")
        self.assertEqual(reconstruction.previous_turn_settings.realtime_active, True)
        self.assertIsNotNone(reconstruction.reference_context_item)
        self.assertEqual(reconstruction.reference_context_item.turn_id, first_turn_id)
        self.assertEqual(reconstruction.reference_context_item.model, "surviving-model")

    def test_read_rollout_reconstruction_rollback_skips_non_user_turns_for_metadata(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: reconstruct_history_rollback_skips_non_user_turns_for_history_and_metadata
        # Contract: session.rollout_reconstruction.rollback_boundaries
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        first_turn_id = "surviving-turn"
        rolled_back_turn_id = "rolled-back-user-turn"
        standalone_turn_id = "standalone-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": first_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "turn 1 user"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=first_turn_id, model="surviving-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "turn 1 user"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "turn 1 assistant"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:05Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": first_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:06Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": rolled_back_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:07Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "turn 2 user"},
                },
                {
                    "timestamp": "2025-01-02T00:00:08Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "turn 2 user"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:09Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "turn 2 assistant"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:10Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": rolled_back_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:11Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": standalone_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:12Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "standalone assistant"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:13Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": standalone_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:14Z",
                    "type": "event_msg",
                    "payload": {"type": "thread_rolled_back", "num_turns": 1},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertEqual([item.content[0].text for item in reconstruction.history], ["turn 1 user", "turn 1 assistant"])
        self.assertIsNotNone(reconstruction.previous_turn_settings)
        self.assertEqual(reconstruction.previous_turn_settings.model, "surviving-model")
        self.assertEqual(reconstruction.previous_turn_settings.realtime_active, True)
        self.assertIsNotNone(reconstruction.reference_context_item)
        self.assertEqual(reconstruction.reference_context_item.turn_id, first_turn_id)
        self.assertEqual(reconstruction.reference_context_item.model, "surviving-model")

    def test_read_rollout_reconstruction_rollback_clears_metadata_when_exceeding_user_turns(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: reconstruct_history_rollback_clears_history_and_metadata_when_exceeding_user_turns
        # Contract: session.rollout_reconstruction.rollback_boundaries
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        only_turn_id = "only-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": only_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "only user"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=only_turn_id, model="only-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "only user"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "only assistant"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:05Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": only_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:06Z",
                    "type": "event_msg",
                    "payload": {"type": "thread_rolled_back", "num_turns": 99},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertEqual(reconstruction.history, ())
        self.assertIsNone(reconstruction.previous_turn_settings)
        self.assertIsNone(reconstruction.reference_context_item)

    def test_read_rollout_reconstruction_resumed_rollback_skips_only_user_turns(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: record_initial_history_resumed_rollback_skips_only_user_turns
        # Contract: session.rollout_reconstruction.resumed_rollback_metadata
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        user_turn_id = "user-turn"
        standalone_turn_id = "standalone-task-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": user_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "seed"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=user_turn_id, model="previous-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": user_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "task_started",
                        "turn_id": standalone_turn_id,
                        "model_context_window": 128000,
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:05Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": standalone_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:06Z",
                    "type": "event_msg",
                    "payload": {"type": "thread_rolled_back", "num_turns": 1},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertEqual(reconstruction.history, ())
        self.assertIsNone(reconstruction.previous_turn_settings)
        self.assertIsNone(reconstruction.reference_context_item)

    def test_read_rollout_reconstruction_rollback_drops_incomplete_user_turn_compaction_metadata(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: record_initial_history_resumed_rollback_drops_incomplete_user_turn_compaction_metadata
        # Contract: session.rollout_reconstruction.compaction_metadata
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        previous_turn_id = "previous-turn"
        incomplete_turn_id = "incomplete-compacted-user-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": previous_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "seed"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=previous_turn_id, model="previous-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": previous_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "task_started",
                        "turn_id": incomplete_turn_id,
                        "model_context_window": 128000,
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:05Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "rolled back"},
                },
                {
                    "timestamp": "2025-01-02T00:00:06Z",
                    "type": "compacted",
                    "payload": {"message": "", "replacement_history": []},
                },
                {
                    "timestamp": "2025-01-02T00:00:07Z",
                    "type": "event_msg",
                    "payload": {"type": "thread_rolled_back", "num_turns": 1},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertEqual(reconstruction.history, ())
        self.assertIsNotNone(reconstruction.previous_turn_settings)
        self.assertEqual(reconstruction.previous_turn_settings.model, "previous-model")
        self.assertEqual(reconstruction.previous_turn_settings.realtime_active, True)
        self.assertIsNotNone(reconstruction.reference_context_item)
        self.assertEqual(reconstruction.reference_context_item.turn_id, previous_turn_id)
        self.assertEqual(reconstruction.reference_context_item.model, "previous-model")

    def test_read_rollout_reconstruction_does_not_seed_reference_context_item_after_compaction(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: record_initial_history_resumed_does_not_seed_reference_context_item_after_compaction
        # Contract: session.rollout_reconstruction.reference_context_seeding
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(
                        turn_id="bare-turn-context",
                        model="previous-model",
                        realtime_active=True,
                    ),
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "compacted",
                    "payload": {"message": "", "replacement_history": []},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertEqual(reconstruction.history, ())
        self.assertIsNone(reconstruction.previous_turn_settings)
        self.assertIsNone(reconstruction.reference_context_item)

    def test_read_rollout_reconstruction_legacy_compaction_without_replacement_history_preserves_user_summary(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: reconstruct_history_legacy_compaction_without_replacement_history_does_not_inject_current_initial_context
        # Contract: session.rollout_reconstruction.legacy_compaction
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
                        "content": [{"type": "input_text", "text": "before compact"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "assistant reply"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "compacted",
                    "payload": {"message": "legacy summary", "replacement_history": None},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertEqual([item.role for item in reconstruction.history], ["user", "user"])
        self.assertEqual([item.content[0].text for item in reconstruction.history], ["before compact", "legacy summary"])
        self.assertIsNone(reconstruction.reference_context_item)

    def test_read_rollout_reconstruction_legacy_compaction_without_replacement_history_clears_later_reference_context(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: reconstruct_history_legacy_compaction_without_replacement_history_clears_later_reference_context_item
        # Contract: session.rollout_reconstruction.legacy_compaction
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        current_turn_id = "current-turn"
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
                        "content": [{"type": "input_text", "text": "before compact"}],
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "compacted",
                    "payload": {"message": "legacy summary", "replacement_history": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": current_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "after legacy compact"},
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=current_turn_id, model="current-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:05Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": current_turn_id, "last_agent_message": None},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertIsNone(reconstruction.reference_context_item)

    def test_read_rollout_reconstruction_turn_context_after_compaction_reestablishes_reference_context(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: record_initial_history_resumed_turn_context_after_compaction_reestablishes_reference_context_item
        # Contract: session.rollout_reconstruction.reference_context_reestablish
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        previous_turn_id = "previous-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": previous_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "seed"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "compacted",
                    "payload": {"message": "", "replacement_history": []},
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(
                        turn_id=previous_turn_id,
                        model="previous-rollout-model",
                        realtime_active=True,
                    ),
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": previous_turn_id, "last_agent_message": None},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertIsNotNone(reconstruction.previous_turn_settings)
        self.assertEqual(reconstruction.previous_turn_settings.model, "previous-rollout-model")
        self.assertEqual(reconstruction.previous_turn_settings.realtime_active, True)
        self.assertIsNotNone(reconstruction.reference_context_item)
        self.assertEqual(reconstruction.reference_context_item.turn_id, previous_turn_id)
        self.assertEqual(reconstruction.reference_context_item.model, "previous-rollout-model")

    def test_read_rollout_reconstruction_aborted_turn_without_id_clears_active_turn_for_compaction_accounting(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: record_initial_history_resumed_aborted_turn_without_id_clears_active_turn_for_compaction_accounting
        # Contract: session.rollout_reconstruction.aborted_turn_accounting
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        previous_turn_id = "previous-turn"
        aborted_turn_id = "aborted-turn-without-id"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": previous_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "seed"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=previous_turn_id, model="previous-rollout-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": previous_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": aborted_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:05Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "aborted"},
                },
                {
                    "timestamp": "2025-01-02T00:00:06Z",
                    "type": "event_msg",
                    "payload": {"type": "turn_aborted", "turn_id": None, "reason": "interrupted"},
                },
                {
                    "timestamp": "2025-01-02T00:00:07Z",
                    "type": "compacted",
                    "payload": {"message": "", "replacement_history": []},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertIsNotNone(reconstruction.previous_turn_settings)
        self.assertEqual(reconstruction.previous_turn_settings.model, "previous-rollout-model")
        self.assertEqual(reconstruction.previous_turn_settings.realtime_active, True)
        self.assertIsNone(reconstruction.reference_context_item)

    def test_read_rollout_reconstruction_unmatched_abort_preserves_active_turn_for_later_context(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: record_initial_history_resumed_unmatched_abort_preserves_active_turn_for_later_turn_context
        # Contract: session.rollout_reconstruction.aborted_turn_accounting
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        previous_turn_id = "previous-turn"
        current_turn_id = "current-turn"
        unmatched_abort_turn_id = "other-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": previous_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "seed"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=previous_turn_id, model="previous-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": previous_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": current_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:05Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "current"},
                },
                {
                    "timestamp": "2025-01-02T00:00:06Z",
                    "type": "event_msg",
                    "payload": {"type": "turn_aborted", "turn_id": unmatched_abort_turn_id, "reason": "interrupted"},
                },
                {
                    "timestamp": "2025-01-02T00:00:07Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=current_turn_id, model="current-rollout-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:08Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": current_turn_id, "last_agent_message": None},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertIsNotNone(reconstruction.previous_turn_settings)
        self.assertEqual(reconstruction.previous_turn_settings.model, "current-rollout-model")
        self.assertEqual(reconstruction.previous_turn_settings.realtime_active, True)
        self.assertIsNotNone(reconstruction.reference_context_item)
        self.assertEqual(reconstruction.reference_context_item.turn_id, current_turn_id)
        self.assertEqual(reconstruction.reference_context_item.model, "current-rollout-model")

    def test_read_rollout_reconstruction_trailing_incomplete_turn_compaction_clears_reference_context(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: record_initial_history_resumed_trailing_incomplete_turn_compaction_clears_reference_context_item
        # Contract: session.rollout_reconstruction.trailing_incomplete_turn
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        previous_turn_id = "previous-turn"
        incomplete_turn_id = "trailing-incomplete-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": previous_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "seed"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=previous_turn_id, model="previous-rollout-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": previous_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": incomplete_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:05Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "incomplete"},
                },
                {
                    "timestamp": "2025-01-02T00:00:06Z",
                    "type": "compacted",
                    "payload": {"message": "", "replacement_history": []},
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertIsNotNone(reconstruction.previous_turn_settings)
        self.assertEqual(reconstruction.previous_turn_settings.model, "previous-rollout-model")
        self.assertEqual(reconstruction.previous_turn_settings.realtime_active, True)
        self.assertIsNone(reconstruction.reference_context_item)

    def test_read_rollout_reconstruction_trailing_incomplete_turn_preserves_turn_context_item(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: record_initial_history_resumed_trailing_incomplete_turn_preserves_turn_context_item
        # Contract: session.rollout_reconstruction.trailing_incomplete_turn
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        current_turn_id = "current-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": current_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "incomplete"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=current_turn_id, model="current-rollout-model", realtime_active=True),
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertIsNotNone(reconstruction.previous_turn_settings)
        self.assertEqual(reconstruction.previous_turn_settings.model, "current-rollout-model")
        self.assertEqual(reconstruction.previous_turn_settings.realtime_active, True)
        self.assertIsNotNone(reconstruction.reference_context_item)
        self.assertEqual(reconstruction.reference_context_item.turn_id, current_turn_id)
        self.assertEqual(reconstruction.reference_context_item.model, "current-rollout-model")

    def test_read_rollout_reconstruction_replaced_incomplete_compacted_turn_clears_reference_context(self):
        # Source: rust_test_migrated
        # Rust crate: codex-core
        # Rust module: src/session/rollout_reconstruction.rs
        # Rust test: record_initial_history_resumed_replaced_incomplete_compacted_turn_clears_reference_context_item
        # Contract: session.rollout_reconstruction.replaced_incomplete_compacted_turn
        root = workspace_tempdir()
        thread_id = str(uuid.uuid4())
        previous_turn_id = "previous-turn"
        compacted_incomplete_turn_id = "compacted-incomplete-turn"
        replacing_turn_id = "replacing-turn"
        path = root / SESSIONS_SUBDIR / "2025" / "01" / "02" / f"rollout-2025-01-02T00-00-00-{thread_id}.jsonl"
        write_rollout(
            path,
            thread_id,
            [
                {
                    "timestamp": "2025-01-02T00:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": previous_turn_id, "model_context_window": 128000},
                },
                {
                    "timestamp": "2025-01-02T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "seed"},
                },
                {
                    "timestamp": "2025-01-02T00:00:02Z",
                    "type": "turn_context",
                    "payload": turn_context_payload(turn_id=previous_turn_id, model="previous-rollout-model", realtime_active=True),
                },
                {
                    "timestamp": "2025-01-02T00:00:03Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": previous_turn_id, "last_agent_message": None},
                },
                {
                    "timestamp": "2025-01-02T00:00:04Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "task_started",
                        "turn_id": compacted_incomplete_turn_id,
                        "model_context_window": 128000,
                    },
                },
                {
                    "timestamp": "2025-01-02T00:00:05Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "compacted"},
                },
                {
                    "timestamp": "2025-01-02T00:00:06Z",
                    "type": "compacted",
                    "payload": {"message": "", "replacement_history": []},
                },
                {
                    "timestamp": "2025-01-02T00:00:07Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "task_started",
                        "turn_id": replacing_turn_id,
                        "model_context_window": 128000,
                    },
                },
            ],
        )

        reconstruction = read_rollout_reconstruction_from_rollout(path)

        self.assertIsNotNone(reconstruction.previous_turn_settings)
        self.assertEqual(reconstruction.previous_turn_settings.model, "previous-rollout-model")
        self.assertEqual(reconstruction.previous_turn_settings.realtime_active, True)
        self.assertIsNone(reconstruction.reference_context_item)

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

    def test_get_threads_cwd_filter_reads_latest_turn_context(self):
        # Rust parity: codex-rollout/src/recorder_tests.rs
        # resume_candidate_matches_cwd_reads_latest_turn_context.
        root = workspace_tempdir()
        thread_id = str(uuid.UUID(int=9012))
        stale_cwd = root / "stale"
        latest_cwd = root / "latest"
        stale_cwd.mkdir()
        latest_cwd.mkdir()

        path = write_thread_rollout(
            root,
            "2025-01-03T13-00-00",
            thread_id,
            message="candidate with stale session cwd",
            cwd=str(stale_cwd),
        )
        payload = turn_context_payload(turn_id="turn-1", model="test-model", realtime_active=None)
        payload["cwd"] = str(latest_cwd)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "timestamp": "2025-01-03T13:00:01Z",
                        "type": "turn_context",
                        "payload": payload,
                    }
                )
                + "\n"
            )

        latest_page = get_threads(root, page_size=10, cwd_filters=(latest_cwd,), default_provider="test-provider")
        stale_page = get_threads(root, page_size=10, cwd_filters=(stale_cwd,), default_provider="test-provider")

        self.assertEqual([item.path for item in latest_page.items], [path])
        self.assertEqual(stale_page.items, [])

    def test_fill_missing_thread_item_metadata_preserves_identity_and_prefers_state_git_fields(self):
        # Rust parity: codex-rollout/src/recorder_tests.rs
        # fill_missing_thread_item_metadata_preserves_identity_and_prefers_state_git_fields.
        filesystem_thread_id = str(uuid.uuid4())
        state_thread_id = str(uuid.uuid4())
        filesystem_path = Path("/tmp/filesystem-rollout.jsonl")
        state_path = Path("/tmp/state-rollout.jsonl")
        item = ThreadItem(
            path=filesystem_path,
            thread_id=filesystem_thread_id,
            first_user_message="filesystem message",
            preview="filesystem preview",
            git_branch="filesystem-branch",
            git_sha="filesystem-sha",
            git_origin_url="https://example.com/filesystem.git",
        )
        state_item = ThreadItem(
            path=state_path,
            thread_id=state_thread_id,
            first_user_message="state message",
            preview="state preview",
            cwd=Path("/tmp/state-cwd"),
            git_branch="state-branch",
            git_sha="state-sha",
            git_origin_url="https://example.com/state.git",
            source="exec",
            agent_nickname="state-agent",
            agent_role="state-role",
            model_provider="state-provider",
            cli_version="state-version",
            created_at="2025-01-03T16:00:00Z",
            updated_at="2025-01-03T16:01:02.003Z",
        )

        merged = fill_missing_thread_item_metadata(item, state_item)

        self.assertEqual(merged.path, filesystem_path)
        self.assertEqual(merged.thread_id, filesystem_thread_id)
        self.assertEqual(merged.first_user_message, "filesystem message")
        self.assertEqual(merged.preview, "filesystem preview")
        self.assertEqual(merged.cwd, Path("/tmp/state-cwd"))
        self.assertEqual(merged.git_branch, "state-branch")
        self.assertEqual(merged.git_sha, "state-sha")
        self.assertEqual(merged.git_origin_url, "https://example.com/state.git")
        self.assertEqual(merged.source, "exec")
        self.assertEqual(merged.agent_nickname, "state-agent")
        self.assertEqual(merged.agent_role, "state-role")
        self.assertEqual(merged.model_provider, "state-provider")
        self.assertEqual(merged.cli_version, "state-version")
        self.assertEqual(merged.created_at, "2025-01-03T16:00:00Z")
        self.assertEqual(merged.updated_at, "2025-01-03T16:01:02.003Z")

    def test_list_threads_metadata_filter_overlays_state_db_list_metadata(self):
        # Rust parity: codex-rollout/src/recorder_tests.rs
        # list_threads_metadata_filter_overlays_state_db_list_metadata.
        root = workspace_tempdir()
        thread_id = str(uuid.UUID(int=9015))
        rollout_path = write_thread_rollout(
            root,
            "2025-01-03T16-00-00",
            thread_id,
            message="Hello from user",
            source="cli",
            model_provider="test-provider",
            cwd=str(root),
        )
        filesystem_item = get_threads(root, page_size=10, allowed_sources=("cli",), default_provider="test-provider").items[0]
        state_metadata = ThreadMetadata(
            id=thread_id,
            rollout_path=rollout_path,
            created_at=datetime(2025, 1, 3, 16, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 3, 16, 1, 2, 3000, tzinfo=timezone.utc),
            source="cli",
            model_provider="test-provider",
            cwd=root,
            cli_version="state-version",
            git_branch="sqlite-branch",
            git_sha="sqlite-sha",
            git_origin_url="https://example.com/repo.git",
            first_user_message="Hello from user",
            preview="Hello from user",
        )

        overlaid = fill_missing_thread_item_metadata(filesystem_item, thread_item_from_state_metadata(state_metadata))

        self.assertEqual(overlaid.path, rollout_path)
        self.assertEqual(overlaid.thread_id, thread_id)
        self.assertEqual(overlaid.git_branch, "sqlite-branch")
        self.assertEqual(overlaid.git_sha, "sqlite-sha")
        self.assertEqual(overlaid.git_origin_url, "https://example.com/repo.git")
        self.assertEqual(overlaid.created_at, filesystem_item.created_at)
        self.assertEqual(overlaid.updated_at, filesystem_item.updated_at)

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

    def test_find_thread_names_by_ids_ignores_invalid_rows_and_empty_names(self):
        # Rust source: codex-rs/rollout/src/session_index.rs find_thread_names_by_ids.
        root = workspace_tempdir()
        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())
        path = session_index_path(root)
        path.write_text(
            "\n".join(
                (
                    "",
                    "not-json",
                    json.dumps(SessionIndexEntry(id1, "   ", "2024-01-01T00:00:00Z").to_mapping()),
                    json.dumps(SessionIndexEntry(id2, "usable", "2024-01-02T00:00:00Z").to_mapping()),
                )
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(find_thread_names_by_ids(root, {id1, id2}), {id2: "usable"})

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

    def test_get_threads_db_disabled_does_not_skip_paginated_items(self):
        # Rust source: codex-rs/rollout/src/recorder_tests.rs::list_threads_db_disabled_does_not_skip_paginated_items.
        root = workspace_tempdir()
        newest_id = str(uuid.UUID(int=9001))
        middle_id = str(uuid.UUID(int=9002))
        oldest_id = str(uuid.UUID(int=9003))
        newest = write_thread_rollout(root, "2025-01-03T12-00-00", newest_id, message="newest")
        middle = write_thread_rollout(root, "2025-01-02T12-00-00", middle_id, message="middle")
        write_thread_rollout(root, "2025-01-01T12-00-00", oldest_id, message="oldest")

        page1 = get_threads(root, page_size=1, default_provider="test-provider")
        page2 = get_threads(root, page_size=1, cursor=page1.next_cursor, default_provider="test-provider")

        self.assertEqual(len(page1.items), 1)
        self.assertEqual(page1.items[0].path, newest)
        self.assertIsNotNone(page1.next_cursor)
        self.assertEqual(len(page2.items), 1)
        self.assertEqual(page2.items[0].path, middle)

    def test_list_threads_state_db_only_skips_jsonl_repair_scan(self):
        # Rust parity: codex-rollout/src/recorder_tests.rs
        # list_threads_state_db_only_skips_jsonl_repair_scan.
        root = workspace_tempdir()
        thread_id = str(uuid.UUID(int=9012))
        rollout_path = write_thread_rollout(
            root,
            "2025-01-03T14-00-00",
            thread_id,
            message="Hello from user",
            source="cli",
            model_provider="test-provider",
            cwd=str(root),
        )
        cwd_filters = (root,)

        state_only_page = list_threads_from_state_metadata(
            (),
            page_size=10,
            cwd_filters=cwd_filters,
            default_provider="test-provider",
        )
        repaired_page = get_threads(root, page_size=10, cwd_filters=cwd_filters, default_provider="test-provider")
        state_metadata = ThreadMetadata(
            id=thread_id,
            rollout_path=rollout_path,
            created_at=datetime(2025, 1, 3, 14, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 3, 14, 0, 0, tzinfo=timezone.utc),
            source="cli",
            model_provider="test-provider",
            cwd=root,
            cli_version="test-version",
            first_user_message="Hello from user",
            preview="Hello from user",
        )
        repaired_state_only_page = list_threads_from_state_metadata(
            (state_metadata,),
            page_size=10,
            cwd_filters=cwd_filters,
            default_provider="test-provider",
        )

        self.assertEqual(state_only_page.items, [])
        self.assertEqual([item.path for item in repaired_page.items], [rollout_path])
        self.assertEqual([item.path for item in repaired_state_only_page.items], [rollout_path])

    def test_list_threads_db_enabled_drops_missing_rollout_paths(self):
        # Rust parity: codex-rollout/src/recorder_tests.rs
        # list_threads_db_enabled_drops_missing_rollout_paths.
        root = workspace_tempdir()
        thread_id = str(uuid.UUID(int=9010))
        stale_path = root / SESSIONS_SUBDIR / "2099" / "01" / "01" / f"rollout-2099-01-01T00-00-00-{thread_id}.jsonl"
        state_metadata = ThreadMetadata(
            id=thread_id,
            rollout_path=stale_path,
            created_at=datetime(2025, 1, 3, 13, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 3, 13, 0, 0, tzinfo=timezone.utc),
            source="cli",
            model_provider="test-provider",
            cwd=root,
            cli_version="test-version",
            first_user_message="Hello from user",
            preview="Hello from user",
        )
        deleted: list[str] = []

        class Runtime:
            def delete_thread(self, value: str) -> None:
                deleted.append(value)

        page = list_threads_from_state_metadata(
            (state_metadata,),
            page_size=10,
            default_provider="test-provider",
            repair_runtime=Runtime(),
            drop_missing_rollout_paths=True,
        )

        self.assertEqual(page.items, [])
        self.assertEqual(deleted, [thread_id])

    def test_list_threads_db_enabled_repairs_stale_rollout_paths(self):
        # Rust parity: codex-rollout/src/recorder_tests.rs
        # list_threads_db_enabled_repairs_stale_rollout_paths.
        root = workspace_tempdir()
        thread_id = str(uuid.UUID(int=9011))
        real_path = write_thread_rollout(
            root,
            "2025-01-03T13-00-00",
            thread_id,
            message="Hello from user",
            source="cli",
            model_provider="test-provider",
            cwd=str(root),
        )
        stale_path = root / SESSIONS_SUBDIR / "2099" / "01" / "01" / f"rollout-2099-01-01T00-00-00-{thread_id}.jsonl"
        state_metadata = ThreadMetadata(
            id=thread_id,
            rollout_path=stale_path,
            created_at=datetime(2025, 1, 3, 13, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 3, 13, 0, 0, tzinfo=timezone.utc),
            source="cli",
            model_provider="test-provider",
            cwd=root,
            cli_version="test-version",
            first_user_message="Hello from user",
            preview="Hello from user",
        )
        repaired: dict[str, Path] = {}

        class Runtime:
            def update_thread_rollout_path(self, value: str, path: Path) -> None:
                repaired[value] = Path(path)

        page = list_threads_from_state_metadata(
            (state_metadata,),
            page_size=1,
            default_provider="test-provider",
            repair_runtime=Runtime(),
            codex_home=root,
            repair_stale_rollout_paths=True,
        )

        self.assertEqual([item.path for item in page.items], [real_path])
        self.assertEqual(repaired, {thread_id: real_path})

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

    def test_get_threads_default_filter_returns_filesystem_scan_results(self):
        # Rust parity: codex-rollout/src/recorder_tests.rs
        # list_threads_default_filter_returns_filesystem_scan_results.
        root = workspace_tempdir()
        thread_id = str(uuid.UUID(int=9013))
        real_cwd = root / "real-cwd"
        stale_cwd = root / "stale-cwd"
        real_cwd.mkdir()
        stale_cwd.mkdir()
        write_thread_rollout(
            root,
            "2025-01-03T13-00-00",
            thread_id,
            message="Hello from user",
            source="cli",
            model_provider="test-provider",
            cwd=str(real_cwd),
        )

        page = get_threads(root, page_size=10, cwd_filters=(stale_cwd,), default_provider="test-provider")

        self.assertEqual(page.items, [])

    def test_get_threads_search_filters_by_session_index_title(self):
        root = workspace_tempdir()
        matching_id = str(uuid.uuid4())
        other_id = str(uuid.uuid4())
        matching = write_thread_rollout(root, "2025-01-02T12-00-00", matching_id, source="cli")
        write_thread_rollout(root, "2025-01-01T12-00-00", other_id, source="cli")
        append_thread_name(root, matching_id, "needle current title")
        append_thread_name(root, other_id, "boring title")

        page = get_threads(root, page_size=10, search_term="needle", default_provider="test-provider")

        self.assertEqual([item.path for item in page.items], [matching])

    def test_get_threads_search_repairs_stale_state_db_hits_before_returning(self):
        # Rust parity: codex-rollout/src/recorder_tests.rs
        # list_threads_search_repairs_stale_state_db_hits_before_returning.
        root = workspace_tempdir()
        thread_id = str(uuid.UUID(int=9014))
        write_thread_rollout(
            root,
            "2025-01-03T15-00-00",
            thread_id,
            message="Hello from user",
            source="cli",
            model_provider="test-provider",
            cwd=str(root),
        )
        append_thread_name(root, thread_id, "current title without search token")

        page = get_threads(root, page_size=10, search_term="needle", default_provider="test-provider")

        self.assertEqual(page.items, [])

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

    def test_get_threads_in_root_flat_layout_only_scans_root_files(self):
        # Rust source: codex-rs/rollout/src/list.rs ThreadListLayout::Flat.
        root = workspace_tempdir()
        top_id = str(uuid.uuid4())
        nested_id = str(uuid.uuid4())
        top_path = root / f"rollout-2025-01-02T12-00-00-{top_id}.jsonl"
        nested_path = root / "2025" / "01" / "03" / f"rollout-2025-01-03T12-00-00-{nested_id}.jsonl"
        for path, thread_id, message in (
            (top_path, top_id, "top-level"),
            (nested_path, nested_id, "nested"),
        ):
            payload = session_meta_payload(thread_id)
            payload.update({"timestamp": "2025-01-02T12-00-00", "source": "cli", "model_provider": "test-provider"})
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "\n".join(
                    json.dumps(line)
                    for line in (
                        {"timestamp": "2025-01-02T12-00-00", "type": "session_meta", "payload": payload},
                        {
                            "timestamp": "2025-01-02T12-00-00",
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": message, "kind": "plain"},
                        },
                    )
                )
                + "\n",
                encoding="utf-8",
            )

        page = get_threads_in_root(root, page_size=10, layout=ThreadListLayout.FLAT)

        self.assertEqual([item.thread_id for item in page.items], [top_id])
        self.assertEqual(page.items[0].path, top_path)


if __name__ == "__main__":
    unittest.main()
