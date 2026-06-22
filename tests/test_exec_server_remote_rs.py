from __future__ import annotations

import asyncio
import base64
import hashlib

import pytest

import pycodex.exec_server as exec_server
from pycodex.exec_server import (
    EnvironmentRegistryClient,
    EnvironmentRegistryRegistrationResponse,
    ExecServerError,
    ExecServerRuntimePaths,
    RemoteEnvironmentConfig,
    endpoint_url,
    environment_registry_auth_error,
    environment_registry_http_error,
    normalize_base_url,
    normalize_environment_id,
    preview_error_body,
    registry_error_message,
    run_remote_environment,
)


def test_register_environment_posts_with_auth_provider_headers() -> None:
    # Rust crate/module/test:
    # codex-exec-server/src/remote.rs::tests::register_environment_posts_with_auth_provider_headers.
    # Contract: registry registration POSTs to the normalized endpoint with
    # auth-provider headers and decodes the typed registration response.
    async def run() -> tuple[EnvironmentRegistryRegistrationResponse, RecordingHttp]:
        http = RecordingHttp(
            FakeResponse(
                200,
                json_body={
                    "environment_id": "env-1",
                    "url": "wss://rendezvous.test/cloud-agent/default/ws/environment/env-1?role=environment&sig=abc",
                },
            )
        )
        client = EnvironmentRegistryClient.new(
            " https://registry.example/ ",
            StaticRegistryAuthProvider(),
            http=http,
        )
        response = await client.register_environment("environment-requested")
        return response, http

    response, http = asyncio.run(run())

    assert response == EnvironmentRegistryRegistrationResponse(
        environment_id="env-1",
        url="wss://rendezvous.test/cloud-agent/default/ws/environment/env-1?role=environment&sig=abc",
    )
    assert http.posts == [
        {
            "url": "https://registry.example/cloud/environment/environment-requested/register",
            "headers": {
                "authorization": "Bearer registry-token",
                "chatgpt-account-id": "workspace-123",
            },
            "follow_redirects": False,
        }
    ]


def test_register_environment_does_not_follow_redirects_with_auth_headers() -> None:
    # Rust test:
    # codex-exec-server/src/remote.rs::tests::register_environment_does_not_follow_redirects_with_auth_headers.
    # Contract: registry client disables redirects so auth headers are not
    # forwarded to redirect targets.
    async def run() -> tuple[ExecServerError, RecordingHttp]:
        http = RecordingHttp(FakeResponse(302, body="redirecting"))
        client = EnvironmentRegistryClient.new(
            "https://registry.example",
            StaticRegistryAuthProvider(),
            http=http,
        )
        with pytest.raises(ExecServerError) as exc_info:
            await client.register_environment("environment-requested")
        return exc_info.value, http

    error, http = asyncio.run(run())

    assert error.kind == "environment_registry_http"
    assert error.status == 302
    assert error.code is None
    assert error.message == "redirecting"
    assert http.posts[0]["follow_redirects"] is False


def test_debug_output_redacts_auth_provider() -> None:
    # Rust test: codex-exec-server/src/remote.rs::tests::debug_output_redacts_auth_provider.
    config = RemoteEnvironmentConfig.new(
        "https://registry.example",
        "env-1",
        StaticRegistryAuthProvider(),
    )
    client = EnvironmentRegistryClient.new(
        "https://registry.example",
        StaticRegistryAuthProvider(),
        http=RecordingHttp(FakeResponse(200, json_body={"environment_id": "env-1", "url": "wss://x"})),
    )

    assert "<redacted>" in repr(config)
    assert "<redacted>" in repr(client)
    assert "workspace-123" not in repr(config)
    assert "workspace-123" not in repr(client)


def test_remote_environment_config_normalizes_environment_id_and_defaults_name() -> None:
    # Rust source contract: RemoteEnvironmentConfig::new trims environment id
    # and fills the default public name.
    config = RemoteEnvironmentConfig.new("https://registry.example", " env-1 ", {})

    assert config.environment_id == "env-1"
    assert config.name == "codex-exec-server"
    with pytest.raises(ExecServerError, match="environment id is required"):
        RemoteEnvironmentConfig.new("https://registry.example", "   ", {})


def test_base_url_endpoint_and_error_helpers_match_rust_shapes() -> None:
    # Rust source contract: base URLs trim surrounding whitespace and trailing
    # slash, endpoint paths are joined with one slash, and registry error bodies
    # prefer nested error.message before body preview fallbacks.
    assert normalize_base_url(" https://registry.example/// ") == "https://registry.example"
    assert endpoint_url("https://registry.example", "/cloud/environment/env/register") == (
        "https://registry.example/cloud/environment/env/register"
    )
    with pytest.raises(ExecServerError, match="environment registry base URL is required"):
        normalize_base_url(" / ")

    body = '{"error":{"code":"bad_request","message":"bad env"}}'
    assert registry_error_message(body) == "bad env"
    assert preview_error_body("  abc  ") == "abc"
    assert preview_error_body(" \n ") is None

    auth = environment_registry_auth_error(401, body)
    assert auth.kind == "environment_registry_auth"
    assert str(auth) == "environment registry authentication failed (401 Unauthorized): bad env"

    http_error = environment_registry_http_error(500, body)
    assert http_error.kind == "environment_registry_http"
    assert http_error.status == 500
    assert http_error.code == "bad_request"
    assert http_error.message == "bad env"


def test_run_remote_environment_registers_connects_serves_and_resets_backoff(tmp_path) -> None:
    # Rust source contract:
    # codex-exec-server/src/remote.rs::run_remote_environment.
    # Contract: each loop registers the environment, prints the registered id,
    # connects to the returned rendezvous URL, resets backoff to 1s on connect
    # success, serves the websocket with a cloned ConnectionProcessor, then
    # sleeps and doubles the next backoff.
    async def run() -> tuple[list[str], list[str], list[str], list[int], str]:
        registry = RecordingRegistryClient(
            [
                EnvironmentRegistryRegistrationResponse("env-1", "wss://relay/one"),
                EnvironmentRegistryRegistrationResponse("env-2", "wss://relay/two"),
            ]
        )
        connected: list[str] = []
        served: list[str] = []
        sleeps: list[int] = []
        stderr = TextSink()

        async def connector(url: str) -> str:
            connected.append(url)
            return f"websocket:{url}"

        async def serve(websocket: str, processor: object) -> None:
            assert processor.__class__.__name__ == "ConnectionProcessor"
            served.append(websocket)

        async def fake_sleep(seconds: int) -> None:
            sleeps.append(seconds)

        await run_remote_environment(
            RemoteEnvironmentConfig.new("https://registry.example", " env-requested ", StaticRegistryAuthProvider()),
            ExecServerRuntimePaths.new(tmp_path / "codex", None),
            registry_client=registry,
            websocket_connector=connector,
            serve_environment=serve,
            sleep=fake_sleep,
            max_iterations=2,
            stderr=stderr,
        )
        return registry.requests, connected, served, sleeps, stderr.text

    requests, connected, served, sleeps, stderr = asyncio.run(run())

    assert requests == ["env-requested", "env-requested"]
    assert connected == ["wss://relay/one", "wss://relay/two"]
    assert served == ["websocket:wss://relay/one", "websocket:wss://relay/two"]
    assert sleeps == [1, 1]
    assert "registered with environment_id env-1" in stderr
    assert "registered with environment_id env-2" in stderr


def test_run_remote_environment_connect_failure_uses_exponential_backoff(tmp_path) -> None:
    # Rust source contract:
    # codex-exec-server/src/remote.rs::run_remote_environment connect error
    # branch and `(backoff * 2).min(30s)` update.
    async def run() -> tuple[list[str], list[int]]:
        registry = RecordingRegistryClient(
            [
                EnvironmentRegistryRegistrationResponse("env-1", "wss://relay/1"),
                EnvironmentRegistryRegistrationResponse("env-2", "wss://relay/2"),
                EnvironmentRegistryRegistrationResponse("env-3", "wss://relay/3"),
                EnvironmentRegistryRegistrationResponse("env-4", "wss://relay/4"),
                EnvironmentRegistryRegistrationResponse("env-5", "wss://relay/5"),
                EnvironmentRegistryRegistrationResponse("env-6", "wss://relay/6"),
            ]
        )
        connected: list[str] = []
        sleeps: list[int] = []

        async def connector(url: str) -> object:
            connected.append(url)
            raise OSError("dial failed")

        async def fake_sleep(seconds: int) -> None:
            sleeps.append(seconds)

        await run_remote_environment(
            RemoteEnvironmentConfig.new("https://registry.example", "env-requested", StaticRegistryAuthProvider()),
            ExecServerRuntimePaths.new(tmp_path / "codex", None),
            registry_client=registry,
            websocket_connector=connector,
            sleep=fake_sleep,
            max_iterations=6,
            stderr=TextSink(),
        )
        return connected, sleeps

    connected, sleeps = asyncio.run(run())

    assert connected == [
        "wss://relay/1",
        "wss://relay/2",
        "wss://relay/3",
        "wss://relay/4",
        "wss://relay/5",
        "wss://relay/6",
    ]
    assert sleeps == [1, 2, 4, 8, 16, 30]


def test_run_remote_environment_propagates_registration_errors(tmp_path) -> None:
    # Rust source contract:
    # codex-exec-server/src/remote.rs::run_remote_environment uses `?` on
    # register_environment before any websocket connect or backoff sleep.
    async def run() -> None:
        registry = RecordingRegistryClient([], error=ExecServerError.environment_registry_auth("nope"))

        async def connector(_url: str) -> object:
            raise AssertionError("connect should not run after register failure")

        async def fake_sleep(_seconds: int) -> None:
            raise AssertionError("sleep should not run after register failure")

        await run_remote_environment(
            RemoteEnvironmentConfig.new("https://registry.example", "env-requested", StaticRegistryAuthProvider()),
            ExecServerRuntimePaths.new(tmp_path / "codex", None),
            registry_client=registry,
            websocket_connector=connector,
            sleep=fake_sleep,
            max_iterations=1,
            stderr=TextSink(),
        )

    with pytest.raises(ExecServerError, match="nope"):
        asyncio.run(run())


def test_run_remote_environment_default_connector_uses_stdlib_websocket(tmp_path, monkeypatch) -> None:
    # Rust source contract:
    # codex-exec-server/src/remote.rs::run_remote_environment.
    # Anchor: connect_async(response.url.as_str()) followed by
    # run_multiplexed_environment(websocket, processor.clone()) on success.
    # Contract: when no connector is injected, Python performs the concrete
    # dependency-light websocket handshake for the registry rendezvous URL and
    # passes the connected websocket to the multiplexed environment boundary.
    async def run() -> tuple[list[str], list[str], RemoteHandshakeWriter]:
        reader = asyncio.StreamReader()
        writer = RemoteHandshakeWriter(reader)
        opened: list[str] = []
        served: list[str] = []

        async def fake_open_connection(host: str, port: int, **kwargs: object):
            opened.append(f"{host}:{port}:{kwargs.get('ssl') is not None}")
            return reader, writer

        async def serve(websocket: object, processor: object) -> None:
            assert websocket.__class__.__name__ == "_StreamWebSocket"
            assert processor.__class__.__name__ == "ConnectionProcessor"
            served.append(websocket.__class__.__name__)

        monkeypatch.setattr(exec_server.asyncio, "open_connection", fake_open_connection)
        await run_remote_environment(
            RemoteEnvironmentConfig.new("https://registry.example", "env-requested", StaticRegistryAuthProvider()),
            ExecServerRuntimePaths.new(tmp_path / "codex", None),
            registry_client=RecordingRegistryClient(
                [
                    EnvironmentRegistryRegistrationResponse(
                        "env-1",
                        "ws://127.0.0.1:7777/cloud-agent/default/ws/environment/env-1?role=environment&sig=abc",
                    )
                ]
            ),
            serve_environment=serve,
            sleep=lambda _seconds: None,
            max_iterations=1,
            stderr=TextSink(),
        )
        return opened, served, writer

    opened, served, writer = asyncio.run(run())

    assert opened == ["127.0.0.1:7777:False"]
    assert served == ["_StreamWebSocket"]
    assert writer.http_request.startswith(
        "GET /cloud-agent/default/ws/environment/env-1?role=environment&sig=abc HTTP/1.1\r\n"
    )
    assert "host: 127.0.0.1:7777\r\n" in writer.http_request
    assert "sec-websocket-key:" in writer.http_request.lower()


class StaticRegistryAuthProvider:
    def to_auth_headers(self) -> dict[str, str]:
        return {
            "authorization": "Bearer registry-token",
            "chatgpt-account-id": "workspace-123",
        }


class FakeResponse:
    def __init__(self, status: int, body: str = "", json_body=None) -> None:
        self.status = status
        self.body = body
        self.json_body = json_body

    def json(self):
        return self.json_body

    def text(self) -> str:
        return self.body


class RecordingHttp:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.posts: list[dict[str, object]] = []

    async def post(self, url: str, headers: dict[str, str], follow_redirects: bool) -> FakeResponse:
        self.posts.append(
            {
                "url": url,
                "headers": headers,
                "follow_redirects": follow_redirects,
            }
        )
        return self.response


class RecordingRegistryClient:
    def __init__(
        self,
        responses: list[EnvironmentRegistryRegistrationResponse],
        *,
        error: ExecServerError | None = None,
    ) -> None:
        self.responses = list(responses)
        self.error = error
        self.requests: list[str] = []

    async def register_environment(self, environment_id: str) -> EnvironmentRegistryRegistrationResponse:
        self.requests.append(environment_id)
        if self.error is not None:
            raise self.error
        if not self.responses:
            raise AssertionError("unexpected register_environment call")
        return self.responses.pop(0)


class TextSink:
    def __init__(self) -> None:
        self.text = ""

    def write(self, value: str) -> int:
        self.text += value
        return len(value)

    def flush(self) -> None:
        pass


class RemoteHandshakeWriter:
    def __init__(self, reader: asyncio.StreamReader) -> None:
        self.reader = reader
        self.http_request = ""

    def write(self, data: bytes) -> None:
        self.http_request += data.decode("ascii")
        key = request_header(self.http_request, "sec-websocket-key")
        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        self.reader.feed_data(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "upgrade: websocket\r\n"
                "connection: Upgrade\r\n"
                f"sec-websocket-accept: {accept}\r\n"
                "\r\n"
            ).encode("ascii")
        )

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


def request_header(request: str, name: str) -> str:
    prefix = f"{name.lower()}:"
    for line in request.split("\r\n"):
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"missing request header {name}")
