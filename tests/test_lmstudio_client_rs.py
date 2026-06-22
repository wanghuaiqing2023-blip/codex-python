"""Parity tests for ``codex-lmstudio/src/client.rs``."""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pycodex.lmstudio.client import LMSTUDIO_CONNECTION_ERROR, LMStudioClient
from pycodex.model_provider_info import LMSTUDIO_OSS_PROVIDER_ID, ModelProviderInfo


class _Handler(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, Any]] = {}
    seen: list[tuple[str, str, dict[str, Any] | None]] = []

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook
        self._respond("GET", None)

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
        payload = json.loads(raw.decode("utf-8")) if raw else None
        self._respond("POST", payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _respond(self, method: str, payload: dict[str, Any] | None) -> None:
        type(self).seen.append((method, self.path, payload))
        status, body = type(self).routes.get((method, self.path), (404, None))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if body is not None:
            self.wfile.write(json.dumps(body).encode("utf-8"))


class Server:
    def __init__(self, routes: dict[tuple[str, str], tuple[int, Any]]) -> None:
        _Handler.routes = routes
        _Handler.seen = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "Server":
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def uri(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    @property
    def seen(self) -> list[tuple[str, str, dict[str, Any] | None]]:
        return list(_Handler.seen)


def run(coro):
    return asyncio.run(coro)


def test_fetch_models_happy_path() -> None:
    # Rust source: client.rs::tests::test_fetch_models_happy_path.
    with Server({("GET", "/models"): (200, {"data": [{"id": "openai/gpt-oss-20b"}]})}) as server:
        client = LMStudioClient.from_host_root(server.uri)
        assert run(client.fetch_models()) == ["openai/gpt-oss-20b"]


def test_fetch_models_no_data_array() -> None:
    # Rust source: client.rs::tests::test_fetch_models_no_data_array.
    with Server({("GET", "/models"): (200, {})}) as server:
        client = LMStudioClient.from_host_root(server.uri)
        with pytest.raises(ValueError, match="No 'data' array in response"):
            run(client.fetch_models())


def test_fetch_models_server_error() -> None:
    # Rust source: client.rs::tests::test_fetch_models_server_error.
    with Server({("GET", "/models"): (500, None)}) as server:
        client = LMStudioClient.from_host_root(server.uri)
        with pytest.raises(OSError, match="Failed to fetch models: 500"):
            run(client.fetch_models())


def test_check_server_happy_path_and_error() -> None:
    # Rust source: client.rs::tests::test_check_server_happy_path and
    # test_check_server_error.
    with Server({("GET", "/models"): (200, {})}) as server:
        run(LMStudioClient.from_host_root(server.uri).check_server())

    with Server({("GET", "/models"): (404, None)}) as server:
        with pytest.raises(OSError, match="Server returned error: 404"):
            run(LMStudioClient.from_host_root(server.uri).check_server())


def test_check_server_connection_failure_message() -> None:
    client = LMStudioClient.from_host_root("http://127.0.0.1:1")
    with pytest.raises(OSError, match="LM Studio is not responding"):
        run(client.check_server())
    assert "lms server start" in LMSTUDIO_CONNECTION_ERROR


def test_load_model_posts_empty_response_probe() -> None:
    # Rust source: client.rs::load_model sends `/responses` with max_output_tokens 1.
    with Server({("POST", "/responses"): (200, {"ok": True})}) as server:
        run(LMStudioClient.from_host_root(server.uri).load_model("openai/gpt-oss-20b"))
        assert server.seen == [
            (
                "POST",
                "/responses",
                {"model": "openai/gpt-oss-20b", "input": "", "max_output_tokens": 1},
            )
        ]


def test_load_model_server_error() -> None:
    with Server({("POST", "/responses"): (503, None)}) as server:
        with pytest.raises(OSError, match="Failed to load model: 503"):
            run(LMStudioClient.from_host_root(server.uri).load_model("model"))


def test_find_lms_with_mock_home_fallback_and_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust source: client.rs::tests::test_find_lms_with_mock_home.
    monkeypatch.setattr("shutil.which", lambda _name: None)
    name = "lms.exe" if __import__("sys").platform.startswith("win") else "lms"
    executable = tmp_path / ".lmstudio" / "bin" / name
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")

    assert LMStudioClient.find_lms_with_home_dir(str(tmp_path)) == str(executable)

    with pytest.raises(FileNotFoundError, match="LM Studio not found"):
        LMStudioClient.find_lms_with_home_dir(str(tmp_path / "missing"))


def test_find_lms_prefers_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust source: client.rs::find_lms first tries `lms` in PATH.
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")
    assert LMStudioClient.find_lms() == "lms"


def test_from_host_root() -> None:
    # Rust source: client.rs::tests::test_from_host_root.
    assert LMStudioClient.from_host_root("http://localhost:1234").base_url == "http://localhost:1234"
    assert LMStudioClient.from_host_root("https://example.com:8080/api").base_url == "https://example.com:8080/api"


def test_try_from_provider_uses_lmstudio_base_url() -> None:
    with Server({("GET", "/v1/models"): (200, {})}) as server:
        config = SimpleNamespace(
            model_providers={
                LMSTUDIO_OSS_PROVIDER_ID: ModelProviderInfo(name="gpt-oss", base_url=f"{server.uri}/v1")
            }
        )
        client = run(LMStudioClient.try_from_provider(config))
        assert client.base_url == f"{server.uri}/v1"


def test_try_from_provider_reports_missing_or_invalid_provider() -> None:
    with pytest.raises(FileNotFoundError, match="Built-in provider lmstudio not found"):
        run(LMStudioClient.try_from_provider(SimpleNamespace(model_providers={})))

    with pytest.raises(ValueError, match="oss provider must have a base_url"):
        run(
            LMStudioClient.try_from_provider(
                SimpleNamespace(model_providers={LMSTUDIO_OSS_PROVIDER_ID: {"name": "gpt-oss"}})
            )
        )


def test_download_model_runs_lms_get(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust source: client.rs::download_model invokes `lms get --yes <model>`.
    calls: list[list[str]] = []

    @dataclass
    class Result:
        returncode: int

    def fake_run(args, **_kwargs):
        calls.append(list(args))
        return Result(0)

    monkeypatch.setattr(LMStudioClient, "find_lms", staticmethod(lambda: "lms"))
    monkeypatch.setattr("subprocess.run", fake_run)

    run(LMStudioClient.from_host_root("http://localhost:1234").download_model("model-a"))

    assert calls == [["lms", "get", "--yes", "model-a"]]
