from __future__ import annotations

import asyncio
from types import SimpleNamespace

from pycodex.memories.write import CODEX_LIMIT_ID, rate_limits_check, rate_limits_ok, snapshot_allows_startup
from pycodex.protocol import RateLimitReachedType, RateLimitSnapshot, RateLimitWindow


def snapshot(
    primary_used_percent: float | None,
    secondary_used_percent: float | None,
) -> RateLimitSnapshot:
    return RateLimitSnapshot(
        limit_id=CODEX_LIMIT_ID,
        limit_name=None,
        primary=None if primary_used_percent is None else RateLimitWindow(primary_used_percent),
        secondary=None if secondary_used_percent is None else RateLimitWindow(secondary_used_percent),
        credits=None,
        plan_type=None,
        rate_limit_reached_type=None,
    )


def test_startup_check_uses_configured_remaining_threshold() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/guard.rs + src/guard_tests.rs::startup_check_uses_configured_remaining_threshold
    # Contract: max used percent is 100 - clamp(min_remaining_percent, 0, 100).
    rate_limits = snapshot(89.9, 50.0)

    assert snapshot_allows_startup(rate_limits, 10)
    assert not snapshot_allows_startup(rate_limits, 11)


def test_startup_check_skips_when_primary_or_secondary_is_too_low() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/guard.rs + src/guard_tests.rs::startup_check_skips_when_primary_or_secondary_is_too_low
    # Contract: both primary and secondary windows must be at or below the configured max-used percent.
    assert not snapshot_allows_startup(snapshot(75.1, 10.0), 25)
    assert not snapshot_allows_startup(snapshot(10.0, 75.1), 25)
    assert snapshot_allows_startup(snapshot(74.9, 74.9), 25)


def test_startup_check_skips_when_limit_is_reached() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/guard.rs + src/guard_tests.rs::startup_check_skips_when_limit_is_reached
    # Contract: an explicit rate_limit_reached_type blocks startup regardless of window percentages.
    rate_limits = RateLimitSnapshot(
        limit_id=CODEX_LIMIT_ID,
        primary=RateLimitWindow(10.0),
        secondary=RateLimitWindow(10.0),
        rate_limit_reached_type=RateLimitReachedType.RATE_LIMIT_REACHED,
    )

    assert not snapshot_allows_startup(rate_limits, 25)


class FakeAuth:
    def __init__(self, backend: bool = True) -> None:
        self.backend = backend

    def uses_codex_backend(self) -> bool:
        return self.backend


class FakeAuthManager:
    def __init__(self, auth=None) -> None:
        self.auth_value = auth
        self.calls: list[str] = []

    async def auth(self):
        self.calls.append("auth")
        return self.auth_value


class FakeBackendClient:
    def __init__(self, snapshots=None, *, error: Exception | None = None) -> None:
        self.snapshots = snapshots
        self.error = error
        self.calls = 0

    async def get_rate_limits_many(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.snapshots


def memories_config(min_remaining_percent: int):
    return SimpleNamespace(memories=SimpleNamespace(min_rate_limit_remaining_percent=min_remaining_percent))


def test_rate_limits_ok_allows_when_auth_missing_or_not_backend() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/guard.rs::rate_limits_check
    # Contract: missing auth or non-Codex-backend auth returns None, so rate_limits_ok defaults to true.
    assert asyncio.run(rate_limits_check(FakeAuthManager(None), memories_config(25))) is None
    assert asyncio.run(rate_limits_ok(FakeAuthManager(None), memories_config(25)))

    backend_client = FakeBackendClient([snapshot(99.0, 99.0)])
    config = memories_config(25)
    config.backend_client_factory = lambda *_args: backend_client

    assert asyncio.run(rate_limits_check(FakeAuthManager(FakeAuth(False)), config)) is None
    assert backend_client.calls == 0
    assert asyncio.run(rate_limits_ok(FakeAuthManager(FakeAuth(False)), config))


def test_rate_limits_check_selects_codex_limit_before_first_snapshot() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/guard.rs::rate_limits_check
    # Contract: when multiple snapshots are returned, the Codex limit id is selected before falling back to the first snapshot.
    other = snapshot(99.0, 99.0)
    other = RateLimitSnapshot(limit_id="other", primary=other.primary, secondary=other.secondary)
    codex = snapshot(10.0, 10.0)
    client = FakeBackendClient([other, codex])
    config = memories_config(25)
    config.chatgpt_base_url = "https://chatgpt.example"
    factory_calls = []

    def factory(base_url, auth):
        factory_calls.append((base_url, auth))
        return client

    config.backend_client_factory = factory
    auth = FakeAuth(True)

    assert asyncio.run(rate_limits_check(FakeAuthManager(auth), config)) is True
    assert factory_calls == [("https://chatgpt.example", auth)]
    assert client.calls == 1


def test_rate_limits_check_falls_back_to_first_snapshot_and_blocks() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/guard.rs::rate_limits_check
    # Contract: without a Codex limit id, the first snapshot controls startup.
    first = RateLimitSnapshot(limit_id="other", primary=RateLimitWindow(90.0), secondary=RateLimitWindow(10.0))
    second = RateLimitSnapshot(limit_id="another", primary=RateLimitWindow(10.0), secondary=RateLimitWindow(10.0))
    client = FakeBackendClient([first, second])
    config = memories_config(25)
    config.backend_client_factory = lambda *_args: client

    assert asyncio.run(rate_limits_check(FakeAuthManager(FakeAuth(True)), config)) is False
    assert not asyncio.run(rate_limits_ok(FakeAuthManager(FakeAuth(True)), config))


def test_rate_limits_ok_defaults_true_on_client_or_fetch_failures() -> None:
    # Rust crate: codex-memories-write
    # Rust module/source: src/guard.rs::rate_limits_ok
    # Contract: backend client construction, fetch failures, and empty snapshots return None, so startup is allowed.
    config = memories_config(25)
    config.backend_client_factory = lambda *_args: (_ for _ in ()).throw(RuntimeError("construct failed"))
    assert asyncio.run(rate_limits_check(FakeAuthManager(FakeAuth(True)), config)) is None
    assert asyncio.run(rate_limits_ok(FakeAuthManager(FakeAuth(True)), config))

    config = memories_config(25)
    config.backend_client_factory = lambda *_args: FakeBackendClient(error=RuntimeError("fetch failed"))
    assert asyncio.run(rate_limits_check(FakeAuthManager(FakeAuth(True)), config)) is None
    assert asyncio.run(rate_limits_ok(FakeAuthManager(FakeAuth(True)), config))

    config = memories_config(25)
    config.backend_client_factory = lambda *_args: FakeBackendClient([])
    assert asyncio.run(rate_limits_check(FakeAuthManager(FakeAuth(True)), config)) is None
    assert asyncio.run(rate_limits_ok(FakeAuthManager(FakeAuth(True)), config))
