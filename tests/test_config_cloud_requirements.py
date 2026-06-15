import asyncio
import unittest

from pycodex.config import (
    CloudRequirementsLoadError,
    CloudRequirementsLoadErrorCode,
    CloudRequirementsLoader,
)


def run(coro):
    return asyncio.run(coro)


class ConfigCloudRequirementsTests(unittest.TestCase):
    def test_default_loader_returns_none(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/cloud_requirements.rs
        # Rust source: CloudRequirementsLoader::default returns Ok(None).
        loader = CloudRequirementsLoader()

        self.assertIsNone(run(loader.get()))

    def test_shared_future_runs_once(self) -> None:
        # Rust test: shared_future_runs_once
        calls = 0

        async def load() -> dict[str, object]:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return {"features": {"plugins": False}}

        async def exercise() -> tuple[object, object]:
            loader = CloudRequirementsLoader.new(load())
            return await asyncio.gather(loader.get(), loader.get())

        first, second = run(exercise())

        self.assertEqual(first, {"features": {"plugins": False}})
        self.assertEqual(second, first)
        self.assertEqual(calls, 1)

    def test_get_returns_cloned_mapping_after_resolution(self) -> None:
        # Rust Shared future clones the Output for each waiter.
        async def load() -> dict[str, object]:
            return {"approval_policy": "on-request"}

        async def exercise() -> tuple[dict[str, object], dict[str, object]]:
            loader = CloudRequirementsLoader.new(load())
            first = await loader.get()
            assert first is not None
            first["approval_policy"] = "never"
            second = await loader.get()
            assert second is not None
            return first, second

        first, second = run(exercise())

        self.assertEqual(first, {"approval_policy": "never"})
        self.assertEqual(second, {"approval_policy": "on-request"})

    def test_load_error_accessors_match_rust_shape(self) -> None:
        # Rust source: CloudRequirementsLoadError::new, code(), status_code(), Display.
        error = CloudRequirementsLoadError.new(CloudRequirementsLoadErrorCode.AUTH, 401, "login required")

        self.assertEqual(error.code(), CloudRequirementsLoadErrorCode.AUTH)
        self.assertEqual(error.status_code(), 401)
        self.assertEqual(str(error), "login required")

    def test_failed_future_is_shared(self) -> None:
        # Rust Shared future returns the same cloned error output for every waiter.
        calls = 0

        async def load() -> None:
            nonlocal calls
            calls += 1
            raise CloudRequirementsLoadError.new(
                CloudRequirementsLoadErrorCode.REQUEST_FAILED,
                503,
                "service unavailable",
            )

        async def exercise() -> tuple[str, str]:
            loader = CloudRequirementsLoader.new(load())
            first, second = await asyncio.gather(
                _get_error_message(loader),
                _get_error_message(loader),
            )
            return first, second

        first, second = run(exercise())

        self.assertEqual(first, "service unavailable")
        self.assertEqual(second, "service unavailable")
        self.assertEqual(calls, 1)


async def _get_error_message(loader: CloudRequirementsLoader) -> str:
    try:
        await loader.get()
    except CloudRequirementsLoadError as exc:
        return str(exc)
    raise AssertionError("expected CloudRequirementsLoadError")


if __name__ == "__main__":
    unittest.main()
