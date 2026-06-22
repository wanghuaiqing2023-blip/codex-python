"""Parity tests for Rust ``codex-ollama/src/lib.rs``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pycodex.ollama import (
    DEFAULT_OSS_MODEL,
    CliProgressReporter,
    OllamaClient,
    PullEvent,
    Version,
    ensure_oss_ready,
    ensure_responses_supported,
    min_responses_version,
    supports_responses,
)
from pycodex.ollama.pull import Status


@dataclass
class Config:
    model: str | None = None
    model_providers: dict[str, object] | None = None


class FakeClient:
    def __init__(self, models=None, version=None, fetch_error: Exception | None = None) -> None:
        self.models = list(models or [])
        self.version = version
        self.fetch_error = fetch_error
        self.calls: list[tuple[str, object | None]] = []

    async def fetch_models(self) -> list[str]:
        self.calls.append(("fetch_models", None))
        if self.fetch_error is not None:
            raise self.fetch_error
        return list(self.models)

    async def pull_with_reporter(self, model: str, reporter) -> None:
        self.calls.append(("pull_with_reporter", model))
        reporter.on_event(Status(f"pulled {model}"))

    async def fetch_version(self):
        self.calls.append(("fetch_version", None))
        return self.version


class RecordingReporter:
    def __init__(self) -> None:
        self.events: list[PullEvent] = []

    def on_event(self, event: PullEvent) -> None:
        self.events.append(event)


def run(coro):
    return asyncio.run(coro)


def test_crate_root_reexports_and_default_model() -> None:
    # Rust source: lib.rs public re-exports and DEFAULT_OSS_MODEL.
    assert DEFAULT_OSS_MODEL == "gpt-oss:20b"
    assert OllamaClient is not None
    assert CliProgressReporter is not None


def test_supports_responses_version_cutoff_matches_rust_tests() -> None:
    # Rust source: supports_responses_for_dev_zero / before_cutoff / at_or_after_cutoff.
    assert min_responses_version() == Version(0, 13, 4)
    assert supports_responses(Version(0, 0, 0))
    assert not supports_responses(Version(0, 13, 3))
    assert supports_responses(Version(0, 13, 4))
    assert supports_responses(Version(0, 14, 0))


def test_ensure_oss_ready_uses_default_model_and_skips_existing() -> None:
    # Rust source: config.model None falls back to DEFAULT_OSS_MODEL; present model skips pull.
    client = FakeClient(models=[DEFAULT_OSS_MODEL])

    async def factory(config):
        assert config.model is None
        return client

    run(ensure_oss_ready(Config(), client_factory=factory))
    assert client.calls == [("fetch_models", None)]


def test_ensure_oss_ready_pulls_missing_explicit_model() -> None:
    # Rust source: if model is not present locally, pull_with_reporter is invoked.
    client = FakeClient(models=["other"])
    reporter = RecordingReporter()

    async def factory(_config):
        return client

    run(
        ensure_oss_ready(
            Config(model="wanted"),
            client_factory=factory,
            reporter_factory=lambda: reporter,
        )
    )

    assert client.calls == [("fetch_models", None), ("pull_with_reporter", "wanted")]
    assert reporter.events == [Status("pulled wanted")]


def test_ensure_oss_ready_ignores_fetch_models_error() -> None:
    # Rust source: fetch_models Err is warning-only and not fatal.
    client = FakeClient(fetch_error=OSError("tags failed"))

    async def factory(_config):
        return client

    run(ensure_oss_ready(Config(model="wanted"), client_factory=factory))
    assert client.calls == [("fetch_models", None)]


def test_ensure_responses_supported_accepts_missing_dev_and_new_versions() -> None:
    # Rust source: missing/unparseable endpoint returns Ok, dev zero and >= cutoff are accepted.
    for version in (None, Version(0, 0, 0), Version(0, 13, 4), Version(0, 14, 0)):
        client = FakeClient(version=version)

        async def factory(_provider, client=client):
            return client

        run(ensure_responses_supported(object(), client_factory=factory))
        assert client.calls == [("fetch_version", None)]


def test_ensure_responses_supported_rejects_old_version() -> None:
    client = FakeClient(version=Version(0, 13, 3))

    async def factory(_provider):
        return client

    with pytest.raises(OSError, match=r"Ollama 0\.13\.3 is too old\. Codex requires Ollama 0\.13\.4 or newer\."):
        run(ensure_responses_supported(object(), client_factory=factory))
