import unittest
from pathlib import Path

from pycodex.core.state.turn import (
    ActiveTurn,
    MailboxDeliveryPhase,
    PendingRequestPermissions,
    TurnState,
    merge_permission_profiles,
    response_sender,
)
from pycodex.protocol.models import (
    AdditionalPermissionProfile,
    FileSystemAccessMode,
    FileSystemPermissions,
    FileSystemPath,
    FileSystemSandboxEntry,
    NetworkPermissions,
)
from pycodex.protocol.request_permissions import RequestPermissionProfile


class CoreStateTurnTests(unittest.TestCase):
    # Rust source:
    # codex/codex-rs/core/src/state/turn.rs
    # Permission merge source:
    # codex/codex-rs/sandboxing/src/policy_transforms.rs

    def test_active_turn_default_creates_empty_turn_state(self) -> None:
        active = ActiveTurn()

        self.assertIsNone(active.task)
        self.assertIsInstance(active.turn_state, TurnState)
        self.assertTrue(active.turn_state.accepts_mailbox_delivery_for_current_turn())
        self.assertIsNone(active.turn_state.granted_permissions())
        self.assertFalse(active.turn_state.strict_auto_review_enabled())

    def test_insert_remove_pending_request_permissions_returns_previous_values(self) -> None:
        state = TurnState()
        first = PendingRequestPermissions(
            response_sender(),
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            Path.cwd(),
        )
        second = PendingRequestPermissions(
            response_sender(),
            RequestPermissionProfile(
                file_system=FileSystemPermissions.from_read_write_roots(write=(Path.cwd(),))
            ),
            Path.cwd(),
        )

        self.assertIsNone(state.insert_pending_request_permissions("call-1", first))
        self.assertIs(
            state.insert_pending_request_permissions("call-1", second),
            first,
        )
        self.assertIs(state.remove_pending_request_permissions("call-1"), second)
        self.assertIsNone(state.remove_pending_request_permissions("call-1"))

    def test_insert_remove_pending_approval_returns_previous_values(self) -> None:
        # Rust source: TurnState::insert_pending_approval / remove_pending_approval
        state = TurnState()
        first = object()
        second = object()

        self.assertIsNone(state.insert_pending_approval("approval-1", first))
        self.assertIs(state.insert_pending_approval("approval-1", second), first)
        self.assertIs(state.remove_pending_approval("approval-1"), second)
        self.assertIsNone(state.remove_pending_approval("approval-1"))

    def test_insert_remove_pending_user_input_returns_previous_values(self) -> None:
        # Rust source: TurnState::insert_pending_user_input / remove_pending_user_input
        state = TurnState()
        first = object()
        second = object()

        self.assertIsNone(state.insert_pending_user_input("input-1", first))
        self.assertIs(state.insert_pending_user_input("input-1", second), first)
        self.assertIs(state.remove_pending_user_input("input-1"), second)
        self.assertIsNone(state.remove_pending_user_input("input-1"))

    def test_insert_remove_pending_elicitation_returns_previous_values(self) -> None:
        # Rust source: TurnState::insert_pending_elicitation / remove_pending_elicitation
        state = TurnState()
        first = object()
        second = object()

        self.assertIsNone(state.insert_pending_elicitation("server", "request-1", first))
        self.assertIs(state.insert_pending_elicitation("server", "request-1", second), first)
        self.assertIs(state.remove_pending_elicitation("server", "request-1"), second)
        self.assertIsNone(state.remove_pending_elicitation("server", "request-1"))

    def test_insert_remove_pending_dynamic_tool_returns_previous_values(self) -> None:
        # Rust source: TurnState::insert_pending_dynamic_tool / remove_pending_dynamic_tool
        state = TurnState()
        first = object()
        second = object()

        self.assertIsNone(state.insert_pending_dynamic_tool("tool-1", first))
        self.assertIs(state.insert_pending_dynamic_tool("tool-1", second), first)
        self.assertIs(state.remove_pending_dynamic_tool("tool-1"), second)
        self.assertIsNone(state.remove_pending_dynamic_tool("tool-1"))

    def test_clear_pending_waiters_clears_all_waiter_maps(self) -> None:
        state = TurnState()
        state.insert_pending_approval("approval", object())
        state.insert_pending_request_permissions(
            "permissions",
            PendingRequestPermissions(
                response_sender(),
                RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
                Path.cwd(),
            ),
        )
        state.insert_pending_user_input("input", object())
        state.insert_pending_elicitation("server", "request", object())
        state.insert_pending_dynamic_tool("tool", object())

        state.clear_pending_waiters()

        self.assertEqual(state.pending_approvals, {})
        self.assertEqual(state.pending_request_permissions, {})
        self.assertEqual(state.pending_user_input, {})
        self.assertEqual(state.pending_elicitations, {})
        self.assertEqual(state.pending_dynamic_tools, {})

    def test_mailbox_delivery_phase_matches_rust_state_machine_helpers(self) -> None:
        state = TurnState()

        self.assertTrue(state.accepts_mailbox_delivery_for_current_turn())
        state.set_mailbox_delivery_phase(MailboxDeliveryPhase.NEXT_TURN)
        self.assertFalse(state.accepts_mailbox_delivery_for_current_turn())
        state.accept_mailbox_delivery_for_current_turn()
        self.assertTrue(state.accepts_mailbox_delivery_for_current_turn())

    def test_record_granted_permissions_merges_like_rust_policy_transform(self) -> None:
        state = TurnState()
        read_entry = FileSystemSandboxEntry(
            FileSystemPath.explicit_path(Path.cwd() / "read"),
            FileSystemAccessMode.READ,
        )
        write_entry = FileSystemSandboxEntry(
            FileSystemPath.explicit_path(Path.cwd() / "write"),
            FileSystemAccessMode.WRITE,
        )

        state.record_granted_permissions(
            AdditionalPermissionProfile(
                network=NetworkPermissions(),
                file_system=FileSystemPermissions(entries=(read_entry,)),
            )
        )
        state.record_granted_permissions(
            AdditionalPermissionProfile(
                network=NetworkPermissions(enabled=True),
                file_system=FileSystemPermissions(entries=(read_entry, write_entry)),
            )
        )

        self.assertEqual(
            state.granted_permissions(),
            AdditionalPermissionProfile(
                network=NetworkPermissions(enabled=True),
                file_system=FileSystemPermissions(entries=(read_entry, write_entry)),
            ),
        )

    def test_merge_permission_profiles_filters_empty_results_like_rust(self) -> None:
        self.assertIsNone(
            merge_permission_profiles(
                AdditionalPermissionProfile(network=NetworkPermissions()),
                AdditionalPermissionProfile(),
            )
        )
        self.assertEqual(
            merge_permission_profiles(
                None,
                AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
            ),
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )

    def test_merge_permission_profiles_preserves_unbounded_deny_glob_depth(self) -> None:
        deny_glob = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("**/*.secret"),
            FileSystemAccessMode.DENY,
        )
        shallow_deny_glob = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("src/**/*.secret"),
            FileSystemAccessMode.DENY,
        )

        merged = merge_permission_profiles(
            AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(deny_glob,),
                    glob_scan_max_depth=None,
                )
            ),
            AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(shallow_deny_glob,),
                    glob_scan_max_depth=3,
                )
            ),
        )

        self.assertEqual(merged.file_system.glob_scan_max_depth, None)
        self.assertEqual(
            merged.file_system.entries,
            (deny_glob, shallow_deny_glob),
        )

    def test_strict_auto_review_flag_is_sticky(self) -> None:
        state = TurnState()

        self.assertFalse(state.strict_auto_review_enabled())
        state.enable_strict_auto_review()
        state.enable_strict_auto_review()
        self.assertTrue(state.strict_auto_review_enabled())

    def test_type_boundaries(self) -> None:
        state = TurnState()

        with self.assertRaises(TypeError):
            state.insert_pending_request_permissions("call", object())
        with self.assertRaises(TypeError):
            state.insert_pending_approval(1, object())
        with self.assertRaises(TypeError):
            PendingRequestPermissions(response_sender(), object(), Path.cwd())
        with self.assertRaises(TypeError):
            state.record_granted_permissions(object())


if __name__ == "__main__":
    unittest.main()
