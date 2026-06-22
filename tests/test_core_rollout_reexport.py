import unittest

import pycodex.rollout as rollout_impl
from pycodex.core import rollout
from pycodex.protocol import SessionSource


class CoreRolloutReexportTests(unittest.TestCase):
    def test_core_rollout_reexports_existing_rollout_surface(self) -> None:
        # Rust: codex-rs/core/src/rollout.rs re-exports codex_rollout symbols.
        self.assertIs(rollout.Cursor, rollout_impl.Cursor)
        self.assertIs(rollout.SessionMeta, rollout_impl.SessionMeta)
        self.assertIs(rollout.ThreadItem, rollout_impl.ThreadItem)
        self.assertIs(rollout.ThreadSortKey, rollout_impl.ThreadSortKey)
        self.assertIs(rollout.ThreadsPage, rollout_impl.ThreadsPage)
        self.assertIs(rollout.parse_cursor, rollout_impl.parse_cursor)
        self.assertIs(rollout.read_head_for_summary, rollout_impl.read_head_for_summary)
        self.assertIs(rollout.find_thread_path_by_id_str, rollout_impl.find_thread_path_by_id_str)
        self.assertIs(rollout.find_conversation_path_by_id_str, rollout_impl.find_thread_path_by_id_str)
        self.assertIs(rollout_impl.find_conversation_path_by_id_str, rollout_impl.find_thread_path_by_id_str)

    def test_interactive_session_sources_match_rust_rollout_constant(self) -> None:
        # Rust: codex-rs/rollout/src/lib.rs::INTERACTIVE_SESSION_SOURCES.
        self.assertEqual(
            rollout_impl.INTERACTIVE_SESSION_SOURCES,
            (
                SessionSource.cli(),
                SessionSource.vscode(),
                SessionSource.custom_source("atlas"),
                SessionSource.custom_source("chatgpt"),
            ),
        )
        self.assertIs(rollout.INTERACTIVE_SESSION_SOURCES, rollout_impl.INTERACTIVE_SESSION_SOURCES)

    def test_core_rollout_exposes_small_enums_and_local_bridges(self) -> None:
        # Rust: codex-rs/core/src/rollout.rs also re-exports policy/list enums and local submodules.
        self.assertEqual(rollout.SortDirection.ASC.value, "asc")
        self.assertEqual(rollout.SortDirection.DESC.value, "desc")
        self.assertIs(rollout.SortDirection, rollout_impl.SortDirection)
        self.assertEqual(rollout.EventPersistenceMode.LIMITED.value, "limited")
        self.assertEqual(rollout.EventPersistenceMode.EXTENDED.value, "extended")
        self.assertTrue(callable(rollout.map_session_init_error))
        self.assertTrue(callable(rollout.truncate_rollout_to_last_n_fork_turns))
        self.assertTrue(callable(rollout.truncate_rollout_before_nth_user_message_from_start))


if __name__ == "__main__":
    unittest.main()
