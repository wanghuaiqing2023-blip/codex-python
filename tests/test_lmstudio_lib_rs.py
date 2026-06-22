"""Parity tests for ``codex-lmstudio/src/lib.rs``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable

import pytest

from pycodex.lmstudio import DEFAULT_OSS_MODEL, LMStudioClient, ensure_oss_ready


@dataclass
class Config:
    model: str | None = None


class FakeClient:
    def __init__(self, models: list[str] | Exception) -> None:
        self.models = models
        self.calls: list[tuple[str, str | None]] = []

    async def fetch_models(self) -> list[str]:
        self.calls.append(("fetch_models", None))
        if isinstance(self.models, Exception):
            raise self.models
        return self.models

    async def download_model(self, model: str) -> None:
        self.calls.append(("download_model", model))

    async def load_model(self, model: str) -> None:
        self.calls.append(("load_model", model))


class FailingDownloadClient(FakeClient):
    async def download_model(self, model: str) -> None:
        self.calls.append(("download_model", model))
        raise OSError("download failed")


class FailingLoadClient(FakeClient):
    async def load_model(self, model: str) -> None:
        self.calls.append(("load_model", model))
        raise OSError("load failed")


def run(coro: Awaitable[Any]) -> Any:
    return asyncio.run(coro)


async def _ready(config: Config, client: FakeClient) -> None:
    async def factory(received: Config) -> FakeClient:
        assert received is config
        return client

    spawned: list[Awaitable[Any]] = []

    def spawner(awaitable: Awaitable[Any]) -> None:
        spawned.append(awaitable)

    await ensure_oss_ready(config, client_factory=factory, task_spawner=spawner)
    for awaitable in spawned:
        await awaitable


def test_default_oss_model_matches_rust_constant() -> None:
    # Rust source: lib.rs::DEFAULT_OSS_MODEL.
    assert DEFAULT_OSS_MODEL == "openai/gpt-oss-20b"


def test_lmstudio_client_is_reexported_from_crate_root() -> None:
    # Rust source: lib.rs::pub use client::LMStudioClient.
    assert LMStudioClient.__name__ == "LMStudioClient"


def test_ensure_oss_ready_uses_default_model_and_skips_download_when_present() -> None:
    # Rust source: ensure_oss_ready uses DEFAULT_OSS_MODEL when config.model is None.
    client = FakeClient([DEFAULT_OSS_MODEL])

    run(_ready(Config(), client))

    assert client.calls == [
        ("fetch_models", None),
        ("load_model", DEFAULT_OSS_MODEL),
    ]


def test_ensure_oss_ready_downloads_missing_explicit_model_then_loads() -> None:
    # Rust source: missing selected model triggers download_model before spawn load.
    client = FakeClient(["other-model"])

    run(_ready(Config(model="custom-model"), client))

    assert client.calls == [
        ("fetch_models", None),
        ("download_model", "custom-model"),
        ("load_model", "custom-model"),
    ]


def test_ensure_oss_ready_ignores_fetch_models_error_and_still_loads() -> None:
    # Rust source: fetch_models Err is logged and is not fatal.
    client = FakeClient(OSError("models unavailable"))

    run(_ready(Config(model="custom-model"), client))

    assert client.calls == [
        ("fetch_models", None),
        ("load_model", "custom-model"),
    ]


def test_ensure_oss_ready_propagates_download_error() -> None:
    # Rust source: download_model is awaited and its error propagates.
    client = FailingDownloadClient([])

    async def scenario() -> None:
        async def factory(_config: Config) -> FailingDownloadClient:
            return client

        await ensure_oss_ready(Config(model="missing"), client_factory=factory, task_spawner=lambda awaitable: None)

    with pytest.raises(OSError, match="download failed"):
        run(scenario())
    assert client.calls == [
        ("fetch_models", None),
        ("download_model", "missing"),
    ]


def test_ensure_oss_ready_ignores_background_load_error() -> None:
    # Rust source: spawned load_model logs failures without changing Ok result.
    client = FailingLoadClient(["model-a"])

    run(_ready(Config(model="model-a"), client))

    assert client.calls == [
        ("fetch_models", None),
        ("load_model", "model-a"),
    ]
