import unittest
from types import SimpleNamespace

from pycodex.core.state_db_bridge import StateDbHandle, init_state_db


class StateDbBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_init_state_db_returns_none_without_initializer(self) -> None:
        self.assertIsNone(await init_state_db(SimpleNamespace()))

    async def test_init_state_db_wraps_sync_initializer_result(self) -> None:
        config = {"path": "state.db"}

        handle = await init_state_db(config, initializer=lambda cfg: {"opened": cfg["path"]})

        self.assertEqual(handle, StateDbHandle({"opened": "state.db"}))

    async def test_init_state_db_preserves_existing_handle(self) -> None:
        expected = StateDbHandle({"db": object()})

        self.assertIs(await init_state_db({}, initializer=lambda _cfg: expected), expected)

    async def test_init_state_db_supports_async_initializer_from_config(self) -> None:
        async def initializer(_cfg: object) -> dict[str, str]:
            return {"async": "ok"}

        config = SimpleNamespace(rollout_state_db_init=initializer)

        self.assertEqual(await init_state_db(config), StateDbHandle({"async": "ok"}))

    async def test_init_state_db_can_read_initializer_from_services(self) -> None:
        config = SimpleNamespace(
            services=SimpleNamespace(rollout_state_db_init=lambda _cfg: {"service": "ok"})
        )

        self.assertEqual(await init_state_db(config), StateDbHandle({"service": "ok"}))


if __name__ == "__main__":
    unittest.main()
