import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.protocol import (
    AdditionalPermissionProfile,
    NetworkPermissions,
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsResponse,
)


class CoreSessionRequestPermissionsTests(unittest.IsolatedAsyncioTestCase):
    # Rust source:
    # codex/codex-rs/core/src/session/mod.rs

    async def test_request_permissions_uses_turn_cwd_like_rust_entrypoint(self) -> None:
        # Rust behavior source: Session::request_permissions forwards to
        # request_permissions_for_cwd with turn_context.cwd.
        turn_cwd = Path.cwd()
        captured = {}

        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            captured["parent_ctx"] = parent_ctx
            captured["call_id"] = call_id
            captured["args"] = args
            captured["cwd"] = cwd
            captured["cancel_token"] = cancel_token
            return RequestPermissionsResponse(
                permissions=args.permissions,
                scope=PermissionGrantScope.TURN,
            )

        session = InMemoryCodexSession(
            cwd=Path.cwd() / "session-default",
            request_permissions_callback=callback,
        )
        parent_ctx = SimpleNamespace(cwd=turn_cwd)
        cancel_token = object()
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            reason="Need network",
        )

        response = await session.request_permissions(
            parent_ctx,
            "call-rust-entry",
            args,
            cancel_token,
        )

        self.assertIs(captured["parent_ctx"], parent_ctx)
        self.assertEqual(captured["call_id"], "call-rust-entry")
        self.assertEqual(captured["args"], args)
        self.assertEqual(captured["cwd"], turn_cwd)
        self.assertIs(captured["cancel_token"], cancel_token)
        self.assertEqual(
            response,
            RequestPermissionsResponse(
                permissions=args.permissions,
                scope=PermissionGrantScope.TURN,
            ),
        )

    async def test_request_permissions_falls_back_to_session_cwd_when_context_lacks_cwd(self) -> None:
        # Python compatibility boundary: Rust TurnContext always has cwd, but the
        # in-memory Python session may be exercised with a lightweight context.
        session_cwd = Path.cwd()
        captured = {}

        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            captured["cwd"] = cwd
            return RequestPermissionsResponse(
                permissions=args.permissions,
                scope=PermissionGrantScope.TURN,
            )

        session = InMemoryCodexSession(
            cwd=session_cwd,
            request_permissions_callback=callback,
        )
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions(
            SimpleNamespace(),
            "call-no-cwd",
            args,
            None,
        )

        self.assertEqual(captured["cwd"], session_cwd)
        self.assertEqual(response.permissions, args.permissions)

    async def test_notify_request_permissions_response_completes_pending_event_round_trip(self) -> None:
        # Rust behavior source:
        # codex/codex-rs/core/src/session/mod.rs notify_request_permissions_response
        # normalizes the response, records grants, and sends it to the pending waiter.
        session = InMemoryCodexSession(
            cwd=Path.cwd(),
            request_permissions_event_roundtrip_enabled=True,
        )
        parent_ctx = SimpleNamespace(cwd=Path.cwd(), turn_id="turn-1")
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            reason="Need network",
        )

        task = asyncio.create_task(
            session.request_permissions(parent_ctx, "call-pending", args, None)
        )
        await asyncio.sleep(0)

        self.assertIn("call-pending", session.active_turn.turn_state.pending_request_permissions)
        self.assertEqual(session.emitted_events[-1].type, "request_permissions")
        self.assertEqual(session.emitted_events[-1].payload.call_id, "call-pending")
        self.assertEqual(session.emitted_events[-1].payload.turn_id, "turn-1")
        self.assertEqual(session.emitted_events[-1].payload.reason, "Need network")
        self.assertEqual(session.emitted_events[-1].payload.permissions, args.permissions)

        await session.notify_request_permissions_response(
            "call-pending",
            RequestPermissionsResponse(
                permissions=args.permissions,
                scope=PermissionGrantScope.TURN,
                strict_auto_review=True,
            ),
        )
        response = await task

        self.assertEqual(
            response,
            RequestPermissionsResponse(
                permissions=args.permissions,
                scope=PermissionGrantScope.TURN,
                strict_auto_review=True,
            ),
        )
        self.assertNotIn("call-pending", session.active_turn.turn_state.pending_request_permissions)
        self.assertEqual(
            await session.granted_turn_permissions(),
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )
        self.assertTrue(await session.strict_auto_review())

    async def test_notify_request_permissions_response_ignores_unmatched_call_id(self) -> None:
        # Rust test source: notify_request_permissions_response_ignores_unmatched_call_id.
        session = InMemoryCodexSession(cwd=Path.cwd())

        await session.notify_request_permissions_response(
            "missing-call",
            RequestPermissionsResponse(
                permissions=RequestPermissionProfile(
                    network=NetworkPermissions(enabled=True)
                ),
                scope=PermissionGrantScope.SESSION,
            ),
        )

        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())

    async def test_request_permissions_event_roundtrip_cancellation_removes_pending_entry(self) -> None:
        # Rust behavior source: request_permissions_for_cwd tokio::select cancellation branch
        # removes pending request_permissions and returns None.
        class CancellationToken:
            def __init__(self):
                self._event = asyncio.Event()

            def cancel(self):
                self._event.set()

            def is_cancelled(self):
                return self._event.is_set()

            async def cancelled(self):
                await self._event.wait()

        session = InMemoryCodexSession(
            cwd=Path.cwd(),
            request_permissions_event_roundtrip_enabled=True,
        )
        token = CancellationToken()
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )
        task = asyncio.create_task(
            session.request_permissions(
                SimpleNamespace(cwd=Path.cwd(), turn_id="turn-cancel"),
                "call-cancel",
                args,
                token,
            )
        )
        await asyncio.sleep(0)

        self.assertIn("call-cancel", session.active_turn.turn_state.pending_request_permissions)
        token.cancel()
        response = await task

        self.assertIsNone(response)
        self.assertNotIn("call-cancel", session.active_turn.turn_state.pending_request_permissions)
        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())


if __name__ == "__main__":
    unittest.main()
