"""Prepared parity tests for Rust ``codex-ollama/src/client.rs``.

Pytest is deferred until the full ``codex-ollama`` crate is functionally
complete, per the crate-level porting workflow.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from pycodex.model_provider_info import OLLAMA_OSS_PROVIDER_ID, ModelProviderInfo
from pycodex.ollama.client import HttpResponse, OLLAMA_CONNECTION_ERROR, OllamaClient, Version
from pycodex.ollama.pull import Error, PullEvent, Status, Success


class FakeTransport:
    def __init__(
        self,
        responses: dict[tuple[str, str], HttpResponse] | None = None,
        streams: dict[tuple[str, str], list[bytes]] | None = None,
        fail: Exception | None = None,
    ) -> None:
        self.responses = responses or {}
        self.streams = streams or {}
        self.fail = fail
        self.seen: list[tuple[str, str, Mapping[str, Any] | None]] = []

    def request(self, method: str, url: str, payload: Mapping[str, Any] | None = None) -> HttpResponse:
        self.seen.append((method, url, payload))
        if self.fail is not None:
            raise self.fail
        return self.responses.get((method, url), HttpResponse(status=404, body=b""))

    def stream(self, method: str, url: str, payload: Mapping[str, Any] | None = None):
        self.seen.append((method, url, payload))
        if self.fail is not None:
            raise self.fail
        response = self.responses.get((method, url), HttpResponse(status=200, body=b""))
        if not response.is_success():
            raise OSError(f"failed to start pull: HTTP {response.status}")
        yield from self.streams.get((method, url), [])


class RecordingReporter:
    def __init__(self) -> None:
        self.events: list[PullEvent] = []

    def on_event(self, event: PullEvent) -> None:
        self.events.append(event)


def run(coro):
    return asyncio.run(coro)


def test_fetch_models_happy_path_matches_rust() -> None:
    # Rust source: client.rs::tests::test_fetch_models_happy_path.
    transport = FakeTransport(
        {
            ("GET", "http://server/api/tags"): HttpResponse(
                200,
                b'{"models":[{"name":"llama3.2:3b"},{"name":"mistral"},{"id":"skip"}]}',
            )
        }
    )
    client = OllamaClient.from_host_root("http://server", transport=transport)
    assert run(client.fetch_models()) == ["llama3.2:3b", "mistral"]


def test_fetch_models_non_success_returns_empty_vec() -> None:
    # Rust source: fetch_models returns Ok(Vec::new()) for non-success status.
    transport = FakeTransport({("GET", "http://server/api/tags"): HttpResponse(500)})
    assert run(OllamaClient.from_host_root("http://server", transport=transport).fetch_models()) == []


def test_fetch_version_trims_v_prefix_and_rejects_unparseable() -> None:
    # Rust source: fetch_version trims whitespace and leading 'v' before semver parse.
    transport = FakeTransport(
        {
            ("GET", "http://server/api/version"): HttpResponse(200, b'{"version":" v0.14.1 "}')
        }
    )
    client = OllamaClient.from_host_root("http://server", transport=transport)
    assert run(client.fetch_version()) == Version(0, 14, 1)

    transport.responses[("GET", "http://server/api/version")] = HttpResponse(200, b'{"version":"nope"}')
    assert run(client.fetch_version()) is None


def test_probe_server_openai_compat_and_native_paths() -> None:
    # Rust source: probe_server chooses /v1/models for compat and /api/tags for native.
    transport = FakeTransport(
        {
            ("GET", "http://server/api/tags"): HttpResponse(200),
            ("GET", "http://server/v1/models"): HttpResponse(200),
        }
    )
    run(OllamaClient.from_host_root("http://server", transport=transport).probe_server())
    run(OllamaClient("http://server", uses_openai_compat=True, transport=transport).probe_server())
    assert transport.seen == [
        ("GET", "http://server/api/tags", None),
        ("GET", "http://server/v1/models", None),
    ]


def test_try_from_provider_normalizes_host_root_and_probes() -> None:
    transport = FakeTransport({("GET", "http://server/v1/models"): HttpResponse(200)})
    provider = ModelProviderInfo(name="gpt-oss", base_url="http://server/v1")
    client = run(OllamaClient.try_from_provider(provider, transport=transport))
    assert client.host_root == "http://server"
    assert client.uses_openai_compat


def test_try_from_oss_provider_missing_provider() -> None:
    with pytest.raises(FileNotFoundError, match="Built-in provider ollama not found"):
        run(OllamaClient.try_from_oss_provider(SimpleNamespace(model_providers={})))


def test_probe_server_connection_error_message() -> None:
    transport = FakeTransport(fail=OSError("boom"))
    with pytest.raises(OSError, match="No running Ollama server detected"):
        run(OllamaClient.from_host_root("http://server", transport=transport).probe_server())
    assert "ollama serve" in OLLAMA_CONNECTION_ERROR


def test_pull_model_stream_yields_parser_events_error_and_duplicate_success() -> None:
    # Rust source: parser events are yielded first, then client.rs yields Success again on status success.
    transport = FakeTransport(
        responses={("POST", "http://server/api/pull"): HttpResponse(200)},
        streams={
            ("POST", "http://server/api/pull"): [
                b'{"status":"downloading"}\n{"error":"missing"}\n',
            ]
        },
    )
    events = run(_collect(OllamaClient.from_host_root("http://server", transport=transport).pull_model_stream("m")))
    assert events == [Status("downloading"), Error("missing")]
    assert transport.seen == [("POST", "http://server/api/pull", {"model": "m", "stream": True})]

    transport = FakeTransport(
        responses={("POST", "http://server/api/pull"): HttpResponse(200)},
        streams={("POST", "http://server/api/pull"): [b'{"status":"success"}\n']},
    )
    events = run(_collect(OllamaClient.from_host_root("http://server", transport=transport).pull_model_stream("m")))
    assert events == [Status("success"), Success(), Success()]


def test_pull_with_reporter_success_error_and_unexpected_end() -> None:
    success_transport = FakeTransport(
        responses={("POST", "http://server/api/pull"): HttpResponse(200)},
        streams={("POST", "http://server/api/pull"): [b'{"status":"success"}\n']},
    )
    reporter = RecordingReporter()
    run(OllamaClient.from_host_root("http://server", transport=success_transport).pull_with_reporter("m", reporter))
    assert reporter.events[:2] == [Status("Pulling model m..."), Status("success")]
    assert isinstance(reporter.events[2], Success)

    error_transport = FakeTransport(
        responses={("POST", "http://server/api/pull"): HttpResponse(200)},
        streams={("POST", "http://server/api/pull"): [b'{"error":"missing"}\n']},
    )
    with pytest.raises(OSError, match="Pull failed: missing"):
        run(OllamaClient.from_host_root("http://server", transport=error_transport).pull_with_reporter("m", RecordingReporter()))

    empty_transport = FakeTransport(
        responses={("POST", "http://server/api/pull"): HttpResponse(200)},
        streams={("POST", "http://server/api/pull"): []},
    )
    with pytest.raises(OSError, match="Pull stream ended unexpectedly without success"):
        run(OllamaClient.from_host_root("http://server", transport=empty_transport).pull_with_reporter("m", RecordingReporter()))


async def _collect(stream) -> list[PullEvent]:
    return [event async for event in stream]
