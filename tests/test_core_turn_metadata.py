import json
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from pycodex.core import (
    COMPACTION_KEY,
    FORKED_FROM_THREAD_ID_KEY,
    USER_INPUT_REQUESTED_DURING_TURN_KEY,
    WINDOW_ID_KEY,
    CompactionImplementation,
    CompactionPhase,
    CompactionReason,
    CompactionTrigger,
    CompactionTurnMetadata,
    McpTurnMetadataContext,
    TurnMetadataState,
    build_turn_metadata_header,
    merge_turn_metadata,
    permission_profile_sandbox_tag,
)
from pycodex.protocol import (
    PermissionProfile,
    ReasoningEffort,
    ThreadSource,
    WindowsSandboxLevel,
)


def run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


class CoreTurnMetadataTests(unittest.TestCase):
    def workspace_tempdir(self) -> Path:
        root = Path.cwd() / "tmp_tests_workspace"
        root.mkdir(exist_ok=True)
        path = root / f"turn-metadata-{uuid.uuid4()}"
        path.mkdir()
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def make_repo(self, name: str = "repo") -> Path:
        repo = self.workspace_tempdir() / name
        repo.mkdir()
        run_git(repo, "init")
        run_git(repo, "config", "user.name", "Test User")
        run_git(repo, "config", "user.email", "test@example.com")
        run_git(repo, "config", "core.autocrlf", "false")
        (repo / "README.md").write_text("hello\n", encoding="utf-8")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "-m", "initial")
        return repo

    def make_state(
        self,
        thread_source: ThreadSource | None = ThreadSource.USER,
    ) -> tuple[TurnMetadataState, PermissionProfile]:
        permission_profile = PermissionProfile.read_only()
        state = TurnMetadataState.new(
            session_id="session-a",
            thread_id="thread-a",
            thread_source=thread_source,
            turn_id="turn-a",
            cwd=self.workspace_tempdir(),
            permission_profile=permission_profile,
            windows_sandbox_level=WindowsSandboxLevel.DISABLED,
            enforce_managed_network=False,
        )
        return state, permission_profile

    def test_build_turn_metadata_header_includes_has_changes_for_clean_repo(self) -> None:
        repo_name = "repo-\u6771\u4eac"
        repo = self.make_repo(repo_name)

        header = build_turn_metadata_header(repo, "none")

        self.assertIsNotNone(header)
        self.assertTrue(header.isascii())
        self.assertNotIn("\u6771\u4eac", header)
        parsed = json.loads(header)
        self.assertEqual(parsed["sandbox"], "none")
        actual_repo_path = next(iter(parsed["workspaces"].keys()))
        self.assertEqual(actual_repo_path, str(repo))
        workspace = next(iter(parsed["workspaces"].values()))
        self.assertEqual(workspace["has_changes"], False)
        self.assertEqual(len(workspace["latest_git_commit_hash"]), 40)

    def test_build_turn_metadata_header_returns_sandbox_for_non_repo(self) -> None:
        with (
            patch("pycodex.core.turn_metadata.get_git_repo_root", return_value=None),
            patch("pycodex.core.turn_metadata.get_head_commit_hash", return_value=None),
            patch("pycodex.core.turn_metadata.get_git_remote_urls_assume_git_repo", return_value=None),
            patch("pycodex.core.turn_metadata.get_has_changes", return_value=None),
        ):
            header = build_turn_metadata_header(self.workspace_tempdir(), "none")

        self.assertEqual(json.loads(header), {"request_kind": "memory", "sandbox": "none"})

    def test_build_turn_metadata_header_marks_memory_without_workspace_metadata(self) -> None:
        # Rust source: codex-rs/core/src/turn_metadata.rs
        # Rust test: build_turn_metadata_header_marks_memory_without_workspace_metadata.
        # Behavior anchor: detached memory requests always emit request_kind=memory.
        with (
            patch("pycodex.core.turn_metadata.get_git_repo_root", return_value=None),
            patch("pycodex.core.turn_metadata.get_head_commit_hash", return_value=None),
            patch("pycodex.core.turn_metadata.get_git_remote_urls_assume_git_repo", return_value=None),
            patch("pycodex.core.turn_metadata.get_has_changes", return_value=None),
        ):
            header = build_turn_metadata_header(self.workspace_tempdir())

        self.assertEqual(json.loads(header), {"request_kind": "memory"})

    def test_turn_metadata_state_uses_platform_sandbox_tag(self) -> None:
        state, permission_profile = self.make_state()

        header = state.current_header_value()
        parsed = json.loads(header)

        expected_sandbox = permission_profile_sandbox_tag(
            permission_profile,
            WindowsSandboxLevel.DISABLED,
            False,
        )
        self.assertEqual(parsed["sandbox"], expected_sandbox)
        self.assertEqual(parsed["session_id"], "session-a")
        self.assertEqual(parsed["thread_id"], "thread-a")
        self.assertEqual(parsed["thread_source"], "user")
        self.assertNotIn("session_source", parsed)

    def test_turn_metadata_state_uses_explicit_subagent_thread_source(self) -> None:
        state, _permission_profile = self.make_state(ThreadSource.SUBAGENT)

        parsed = json.loads(state.current_header_value())

        self.assertEqual(parsed["thread_source"], "subagent")
        self.assertNotIn("session_source", parsed)

    def test_turn_metadata_state_includes_root_fork_lineage(self) -> None:
        # Rust source: codex-rs/core/src/turn_metadata.rs
        # Rust test: turn_metadata_state_includes_root_fork_lineage.
        # Behavior anchor: base turn metadata preserves forked_from_thread_id.
        permission_profile = PermissionProfile.read_only()
        state = TurnMetadataState.new(
            "session-a",
            "thread-a",
            "11111111-1111-4111-8111-111111111111",
            ThreadSource.USER,
            "turn-a",
            self.workspace_tempdir(),
            permission_profile,
            WindowsSandboxLevel.DISABLED,
            False,
        )

        parsed = json.loads(state.current_header_value())

        self.assertEqual(
            parsed[FORKED_FROM_THREAD_ID_KEY],
            "11111111-1111-4111-8111-111111111111",
        )

    def test_turn_metadata_state_includes_turn_started_at_unix_ms_after_start(self) -> None:
        state, _permission_profile = self.make_state()

        state.set_turn_started_at_unix_ms(1_700_000_000_123)
        parsed = json.loads(state.current_header_value())

        self.assertEqual(parsed["turn_started_at_unix_ms"], 1_700_000_000_123)

    def test_turn_metadata_state_includes_model_and_reasoning_effort_only_in_mcp_meta(self) -> None:
        state, _permission_profile = self.make_state(thread_source=None)

        header_json = json.loads(state.current_header_value())
        self.assertNotIn("model", header_json)
        self.assertNotIn("reasoning_effort", header_json)

        meta = state.current_meta_value_for_mcp_request(
            McpTurnMetadataContext("gpt-5.4", ReasoningEffort.HIGH)
        )
        self.assertEqual(meta["model"], "gpt-5.4")
        self.assertEqual(meta["reasoning_effort"], "high")

        meta_without_effort = state.current_meta_value_for_mcp_request(
            McpTurnMetadataContext("gpt-5.4", None)
        )
        self.assertEqual(meta_without_effort["model"], "gpt-5.4")
        self.assertNotIn("reasoning_effort", meta_without_effort)

    def test_turn_metadata_state_marks_user_input_requested_only_for_mcp_meta(self) -> None:
        state, _permission_profile = self.make_state(thread_source=None)

        header_json = json.loads(state.current_header_value())
        self.assertNotIn(USER_INPUT_REQUESTED_DURING_TURN_KEY, header_json)
        meta = state.current_meta_value_for_mcp_request(
            McpTurnMetadataContext("gpt-5.4", ReasoningEffort.HIGH)
        )
        self.assertNotIn(USER_INPUT_REQUESTED_DURING_TURN_KEY, meta)

        state.mark_user_input_requested_during_turn()

        header_json = json.loads(state.current_header_value())
        self.assertNotIn(USER_INPUT_REQUESTED_DURING_TURN_KEY, header_json)
        meta = state.current_meta_value_for_mcp_request(
            McpTurnMetadataContext("gpt-5.4", ReasoningEffort.HIGH)
        )
        self.assertEqual(meta[USER_INPUT_REQUESTED_DURING_TURN_KEY], True)

    def test_turn_metadata_state_ignores_client_turn_started_at_unix_ms_before_start(self) -> None:
        state, _permission_profile = self.make_state()

        state.set_responsesapi_client_metadata(
            {"turn_started_at_unix_ms": "client-supplied"}
        )
        parsed = json.loads(state.current_header_value())

        self.assertNotIn("turn_started_at_unix_ms", parsed)

    def test_turn_metadata_state_merges_client_metadata_without_replacing_reserved_fields(self) -> None:
        permission_profile = PermissionProfile.read_only()
        state = TurnMetadataState.new(
            "session-a",
            "thread-a",
            "44444444-4444-4444-8444-444444444444",
            ThreadSource.USER,
            "turn-a",
            self.workspace_tempdir(),
            permission_profile,
            WindowsSandboxLevel.DISABLED,
            False,
        )
        origin = "\u6771\u4eac"

        state.set_responsesapi_client_metadata(
            {
                "fiber_run_id": "fiber-123",
                "origin": origin,
                "model": "client-supplied",
                "reasoning_effort": "client-supplied",
                "session_id": "client-supplied",
                "thread_id": "client-supplied",
                "thread_source": "client-supplied",
                "turn_started_at_unix_ms": "client-supplied",
                "turn_id": "client-supplied",
                "forked_from_thread_id": "client-supplied",
                "request_kind": "client-supplied",
                "compaction": "client-supplied",
                "window_id": "client-supplied",
            }
        )
        state.set_turn_started_at_unix_ms(1_700_000_000_123)

        header = state.current_header_value()
        self.assertTrue(header.isascii())
        self.assertNotIn(origin, header)
        parsed = json.loads(header)

        self.assertEqual(parsed["fiber_run_id"], "fiber-123")
        self.assertEqual(parsed["origin"], origin)
        self.assertEqual(parsed["model"], "client-supplied")
        self.assertEqual(parsed["reasoning_effort"], "client-supplied")
        self.assertEqual(parsed["session_id"], "session-a")
        self.assertEqual(parsed["thread_id"], "thread-a")
        self.assertEqual(parsed["thread_source"], "user")
        self.assertEqual(parsed["turn_id"], "turn-a")
        self.assertEqual(parsed["turn_started_at_unix_ms"], 1_700_000_000_123)
        self.assertEqual(parsed["forked_from_thread_id"], "44444444-4444-4444-8444-444444444444")
        self.assertNotIn("request_kind", parsed)
        self.assertNotIn("compaction", parsed)
        self.assertNotIn("window_id", parsed)

        model_request_header = state.current_header_value_for_model_request("thread-a:1")
        model_request_json = json.loads(model_request_header)
        self.assertEqual(model_request_json["request_kind"], "turn")
        self.assertEqual(model_request_json[WINDOW_ID_KEY], "thread-a:1")

        meta = state.current_meta_value_for_mcp_request(
            McpTurnMetadataContext("gpt-5.4", ReasoningEffort.HIGH)
        )
        self.assertEqual(meta["model"], "gpt-5.4")
        self.assertEqual(meta["reasoning_effort"], "high")
        self.assertNotIn(WINDOW_ID_KEY, meta)

    def test_turn_metadata_state_overlays_request_kind_and_compaction(self) -> None:
        # Rust source: codex-rs/core/src/turn_metadata.rs
        # Rust test: turn_metadata_state_overlays_compaction_only_on_compaction_requests.
        state, _permission_profile = self.make_state()
        state.set_responsesapi_client_metadata({COMPACTION_KEY: "client-supplied"})

        prewarm_json = json.loads(state.current_header_value_for_prewarm("thread-a:0"))
        self.assertEqual(prewarm_json["request_kind"], "prewarm")
        self.assertEqual(prewarm_json[WINDOW_ID_KEY], "thread-a:0")
        self.assertNotIn(COMPACTION_KEY, prewarm_json)

        compact_json = json.loads(
            state.current_header_value_for_compaction(
                "thread-a:2",
                CompactionTurnMetadata(
                    CompactionTrigger.AUTO,
                    CompactionReason.CONTEXT_LIMIT,
                    CompactionImplementation.RESPONSES_COMPACTION_V2,
                    CompactionPhase.MID_TURN,
                ),
            )
        )

        self.assertEqual(compact_json["request_kind"], "compaction")
        self.assertEqual(compact_json[WINDOW_ID_KEY], "thread-a:2")
        self.assertEqual(
            compact_json[COMPACTION_KEY],
            {
                "trigger": "auto",
                "reason": "context_limit",
                "implementation": "responses_compaction_v2",
                "phase": "mid_turn",
                "strategy": "memento",
            },
        )

        regular_json = json.loads(state.current_header_value_for_model_request("thread-a:3"))
        self.assertEqual(regular_json["request_kind"], "turn")
        self.assertEqual(regular_json[WINDOW_ID_KEY], "thread-a:3")
        self.assertNotIn(COMPACTION_KEY, regular_json)

    def test_state_git_enrichment_adds_workspace_metadata(self) -> None:
        repo = self.make_repo()
        permission_profile = PermissionProfile.disabled()
        state = TurnMetadataState.new(
            session_id="session-a",
            thread_id="thread-a",
            thread_source=ThreadSource.USER,
            turn_id="turn-a",
            cwd=repo,
            permission_profile=permission_profile,
            windows_sandbox_level=WindowsSandboxLevel.DISABLED,
            enforce_managed_network=False,
        )

        state.spawn_git_enrichment_task()
        parsed = json.loads(state.current_header_value())

        workspace = parsed["workspaces"][str(repo)]
        self.assertEqual(workspace["has_changes"], False)
        self.assertEqual(len(workspace["latest_git_commit_hash"]), 40)

    def test_merge_turn_metadata_returns_none_when_no_extra_metadata(self) -> None:
        self.assertIsNone(merge_turn_metadata("{}", None, None))
        self.assertIsNone(merge_turn_metadata("not json", 123, None))

    def test_turn_metadata_rejects_non_rust_metadata_shapes(self) -> None:
        state, _permission_profile = self.make_state()

        with self.assertRaisesRegex(TypeError, "turn_started_at_unix_ms must be an integer"):
            state.set_turn_started_at_unix_ms("123")  # type: ignore[arg-type]

        with self.assertRaisesRegex(TypeError, "responsesapi_client_metadata value must be a string"):
            state.set_responsesapi_client_metadata({"bad": 123})  # type: ignore[dict-item]


if __name__ == "__main__":
    unittest.main()
