import asyncio
import gc
import unittest
import warnings

import pycodex.core.session.turn.runtime as turn_runtime


class AsyncOnlyCancellationToken:
    async def cancelled(self) -> None:
        return None


class CoreTurnCancellationWaiterTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_waiter_helper_does_not_create_unawaited_coroutine(self) -> None:
        # Rust source: codex-rs/core/src/session/turn.rs.
        # Contract: cancellation waiting is registered at an async runtime task
        # boundary; helper code must not create a bare waiter future early.
        token = AsyncOnlyCancellationToken()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", RuntimeWarning)
            waiter = turn_runtime._token_cancelled_waiter(token)
            self.assertTrue(callable(waiter))
            gc.collect()

        self.assertEqual(
            [str(warning.message) for warning in caught if issubclass(warning.category, RuntimeWarning)],
            [],
        )

    async def test_cancelled_waiter_is_awaited_through_runtime_task_boundary(self) -> None:
        # Rust source: codex-rs/core/src/session/turn.rs.
        # Contract: the async cancellation waiter is consumed only by the task
        # boundary that races model sampling or tool execution.
        waiter = turn_runtime._token_cancelled_waiter(AsyncOnlyCancellationToken())

        await turn_runtime._await_token_cancelled(waiter)


if __name__ == "__main__":
    unittest.main()
