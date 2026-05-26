from __future__ import annotations

import unittest

from pycodex.core import (
    AgentMetadata,
    AgentRegistry,
    exceeds_thread_spawn_depth_limit,
    next_thread_spawn_depth,
    session_depth,
)
from pycodex.protocol import AgentPath, SessionSource, SubAgentSource, ThreadId
from pycodex.protocol.error import CodexErr


def agent_metadata(thread_id: ThreadId, agent_path: AgentPath | None = None) -> AgentMetadata:
    return AgentMetadata(agent_id=thread_id, agent_path=agent_path)


class AgentRegistryTests(unittest.TestCase):
    def test_session_depth_defaults_to_zero_for_root_sources(self) -> None:
        self.assertEqual(session_depth(SessionSource.cli()), 0)

    def test_thread_spawn_depth_increments_and_enforces_limit(self) -> None:
        source = SessionSource.subagent(
            SubAgentSource.thread_spawn(parent_thread_id=ThreadId.new(), depth=1)
        )

        child_depth = next_thread_spawn_depth(source)

        self.assertEqual(child_depth, 2)
        self.assertTrue(exceeds_thread_spawn_depth_limit(child_depth, 1))

    def test_non_thread_spawn_subagents_default_to_depth_zero(self) -> None:
        source = SessionSource.subagent(SubAgentSource.review())

        self.assertEqual(session_depth(source), 0)
        self.assertEqual(next_thread_spawn_depth(source), 1)
        self.assertFalse(exceeds_thread_spawn_depth_limit(1, 1))

    def test_reservation_release_releases_slot(self) -> None:
        registry = AgentRegistry()
        reservation = registry.reserve_spawn_slot(max_threads=1)
        reservation.release()

        second = registry.reserve_spawn_slot(max_threads=1)
        second.release()

    def test_context_manager_releases_slot(self) -> None:
        registry = AgentRegistry()

        with registry.reserve_spawn_slot(max_threads=1):
            self.assertEqual(registry.total_count, 1)

        self.assertEqual(registry.total_count, 0)

    def test_commit_holds_slot_until_release(self) -> None:
        registry = AgentRegistry()
        reservation = registry.reserve_spawn_slot(max_threads=1)
        thread_id = ThreadId.new()
        reservation.commit(agent_metadata(thread_id))

        with self.assertRaises(CodexErr) as caught:
            registry.reserve_spawn_slot(max_threads=1)
        self.assertEqual(caught.exception.kind, "agent_limit_reached")
        self.assertEqual(caught.exception.payload, 1)

        registry.release_spawned_thread(thread_id)
        self.assertEqual(registry.total_count, 0)

    def test_release_ignores_unknown_thread_id(self) -> None:
        registry = AgentRegistry()
        reservation = registry.reserve_spawn_slot(max_threads=1)
        thread_id = ThreadId.new()
        reservation.commit(agent_metadata(thread_id))

        registry.release_spawned_thread(ThreadId.new())

        with self.assertRaises(CodexErr):
            registry.reserve_spawn_slot(max_threads=1)
        registry.release_spawned_thread(thread_id)

    def test_release_is_idempotent_for_registered_threads(self) -> None:
        registry = AgentRegistry()
        first = registry.reserve_spawn_slot(max_threads=1)
        first_id = ThreadId.new()
        first.commit(agent_metadata(first_id))
        registry.release_spawned_thread(first_id)

        second = registry.reserve_spawn_slot(max_threads=1)
        second_id = ThreadId.new()
        second.commit(agent_metadata(second_id))
        registry.release_spawned_thread(first_id)

        with self.assertRaises(CodexErr):
            registry.reserve_spawn_slot(max_threads=1)
        registry.release_spawned_thread(second_id)

    def test_failed_spawn_keeps_nickname_marked_used(self) -> None:
        registry = AgentRegistry()
        first = registry.reserve_spawn_slot()
        self.assertEqual(first.reserve_agent_nickname_with_preference(["alpha"]), "alpha")
        first.release()

        second = registry.reserve_spawn_slot()
        self.assertEqual(second.reserve_agent_nickname_with_preference(["alpha", "beta"]), "beta")
        second.release()

    def test_agent_nickname_resets_used_pool_when_exhausted(self) -> None:
        registry = AgentRegistry()
        first = registry.reserve_spawn_slot()
        self.assertEqual(first.reserve_agent_nickname_with_preference(["alpha"]), "alpha")
        first.commit(agent_metadata(ThreadId.new()))

        second = registry.reserve_spawn_slot()
        self.assertEqual(second.reserve_agent_nickname_with_preference(["alpha"]), "alpha the 2nd")
        self.assertEqual(registry.nickname_reset_count, 1)
        second.release()

    def test_preferred_nickname_is_reserved_even_if_used(self) -> None:
        registry = AgentRegistry()
        first = registry.reserve_spawn_slot()
        self.assertEqual(first.reserve_agent_nickname_with_preference(["alpha"], preferred="chosen"), "chosen")
        first.release()

        second = registry.reserve_spawn_slot()
        self.assertEqual(second.reserve_agent_nickname_with_preference(["alpha"], preferred="chosen"), "chosen")
        second.release()

    def test_released_nickname_stays_used_until_pool_reset(self) -> None:
        registry = AgentRegistry()
        first = registry.reserve_spawn_slot()
        first_id = ThreadId.new()
        self.assertEqual(first.reserve_agent_nickname_with_preference(["alpha"]), "alpha")
        first.commit(agent_metadata(first_id))
        registry.release_spawned_thread(first_id)

        second = registry.reserve_spawn_slot()
        second_id = ThreadId.new()
        self.assertEqual(second.reserve_agent_nickname_with_preference(["alpha", "beta"]), "beta")
        second.commit(agent_metadata(second_id))
        registry.release_spawned_thread(second_id)

        third = registry.reserve_spawn_slot()
        self.assertEqual(third.reserve_agent_nickname_with_preference(["alpha", "beta"]), "alpha the 2nd")
        self.assertEqual(registry.nickname_reset_count, 1)
        third.release()

    def test_empty_nickname_pool_is_rejected(self) -> None:
        registry = AgentRegistry()
        reservation = registry.reserve_spawn_slot()

        with self.assertRaises(CodexErr) as caught:
            reservation.reserve_agent_nickname_with_preference([])

        self.assertEqual(caught.exception.kind, "unsupported_operation")
        reservation.release()

    def test_register_root_thread_indexes_root_path_without_counting(self) -> None:
        registry = AgentRegistry()
        root_thread_id = ThreadId.new()

        registry.register_root_thread(root_thread_id)

        self.assertEqual(registry.agent_id_for_path(AgentPath.root()), root_thread_id)
        registry.release_spawned_thread(root_thread_id)
        self.assertEqual(registry.total_count, 0)

    def test_reserved_agent_path_is_released_when_spawn_fails(self) -> None:
        registry = AgentRegistry()
        first = registry.reserve_spawn_slot()
        first.reserve_agent_path("/root/researcher")
        first.release()

        second = registry.reserve_spawn_slot()
        second.reserve_agent_path("/root/researcher")
        second.release()

    def test_reserved_agent_path_rejects_duplicates(self) -> None:
        registry = AgentRegistry()
        first = registry.reserve_spawn_slot()
        first.reserve_agent_path("/root/researcher")
        second = registry.reserve_spawn_slot()

        with self.assertRaises(CodexErr) as caught:
            second.reserve_agent_path("/root/researcher")

        self.assertEqual(caught.exception.kind, "unsupported_operation")
        second.release()
        first.release()

    def test_committed_agent_path_is_indexed_until_release(self) -> None:
        registry = AgentRegistry()
        thread_id = ThreadId.new()
        path = AgentPath.from_string("/root/researcher")
        reservation = registry.reserve_spawn_slot()
        reservation.reserve_agent_path(path)
        reservation.commit(agent_metadata(thread_id, path))

        self.assertEqual(registry.agent_id_for_path(path), thread_id)
        self.assertEqual(registry.agent_metadata_for_thread(thread_id).agent_path, path)  # type: ignore[union-attr]
        self.assertEqual(registry.live_agents()[0].agent_id, thread_id)

        registry.release_spawned_thread(thread_id)
        self.assertIsNone(registry.agent_id_for_path(path))

    def test_update_last_task_message(self) -> None:
        registry = AgentRegistry()
        thread_id = ThreadId.new()
        reservation = registry.reserve_spawn_slot()
        reservation.commit(agent_metadata(thread_id))

        registry.update_last_task_message(thread_id, "latest task")

        self.assertEqual(registry.agent_metadata_for_thread(thread_id).last_task_message, "latest task")  # type: ignore[union-attr]
        registry.release_spawned_thread(thread_id)


if __name__ == "__main__":
    unittest.main()
