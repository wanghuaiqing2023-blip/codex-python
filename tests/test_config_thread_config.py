import asyncio
import unittest
from pathlib import Path

from pycodex.config import (
    NoopThreadConfigLoader,
    RemoteThreadConfigLoader,
    SessionThreadConfig,
    StaticThreadConfigLoader,
    ThreadConfigContext,
    ThreadConfigLoadError,
    ThreadConfigLoadErrorCode,
    ThreadConfigSource,
    UserThreadConfig,
)
from pycodex.config.thread_config import (
    load_thread_config_request,
    model_provider_auth_from_proto,
    model_provider_from_proto,
    remote_status_to_error,
    session_thread_config_from_proto,
    session_thread_config_to_toml,
    thread_config_source_from_proto,
    thread_config_source_to_layer,
)
from pycodex.network_proxy import ConfigLayerEntry, ConfigLayerSource


def run(coro):
    return asyncio.run(coro)


class ConfigThreadConfigTests(unittest.TestCase):
    def test_loader_returns_session_and_user_sources(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/thread_config.rs
        # Rust test: loader_returns_session_and_user_sources
        session = SessionThreadConfig(
            model_provider="local",
            model_providers={"local": _test_provider("local")},
            features={"plugins": False},
        )
        loader = StaticThreadConfigLoader.new(
            [
                ThreadConfigSource.session(session),
                ThreadConfigSource.user(UserThreadConfig()),
            ]
        )

        sources = run(loader.load(ThreadConfigContext(thread_id="thread-1")))

        self.assertEqual(
            sources,
            [
                ThreadConfigSource.session(session),
                ThreadConfigSource.user(UserThreadConfig()),
            ],
        )

    def test_loader_translates_sources_to_config_layers(self) -> None:
        # Rust test: loader_translates_sources_to_config_layers
        session = SessionThreadConfig(
            model_provider="local",
            model_providers={"local": _test_provider("local")},
            features={"plugins": False},
        )
        loader = StaticThreadConfigLoader.new(
            [
                ThreadConfigSource.user(),
                ThreadConfigSource.session(session),
            ]
        )

        layers = run(loader.load_config_layers(ThreadConfigContext(cwd=Path("/tmp/project"))))

        self.assertEqual(
            layers,
            [
                ConfigLayerEntry(
                    ConfigLayerSource.session_flags(),
                    {
                        "model_provider": "local",
                        "model_providers": {"local": _test_provider("local")},
                        "features": {"plugins": False},
                    },
                )
            ],
        )

    def test_noop_loader_returns_no_sources_or_layers(self) -> None:
        # Rust source: NoopThreadConfigLoader returns an empty Vec.
        loader = NoopThreadConfigLoader()

        self.assertEqual(run(loader.load(ThreadConfigContext())), [])
        self.assertEqual(run(loader.load_config_layers(ThreadConfigContext())), [])

    def test_user_source_and_empty_session_source_do_not_create_layers(self) -> None:
        # Rust source: UserThreadConfig has no TOML-backed fields yet, and an
        # empty session TOML table is suppressed.
        self.assertIsNone(thread_config_source_to_layer(ThreadConfigSource.user()))
        self.assertIsNone(thread_config_source_to_layer(ThreadConfigSource.session(SessionThreadConfig())))

    def test_session_thread_config_to_toml_omits_empty_fields_and_sorts_features(self) -> None:
        # Rust source: session_thread_config_to_toml inserts only non-empty fields.
        config = SessionThreadConfig(features={"z": True, "a": False})

        self.assertEqual(session_thread_config_to_toml(config), {"features": {"a": False, "z": True}})

    def test_thread_config_load_error_accessors_match_rust_shape(self) -> None:
        # Rust source: ThreadConfigLoadError::new, code(), status_code(), Display.
        error = ThreadConfigLoadError.new(ThreadConfigLoadErrorCode.PARSE, 400, "bad config")

        self.assertEqual(error.code(), ThreadConfigLoadErrorCode.PARSE)
        self.assertEqual(error.status_code(), 400)
        self.assertEqual(str(error), "bad config")

    def test_remote_request_sets_context_and_timeout_like_rust(self) -> None:
        # Rust remote test: load_thread_config_request_sets_timeout.
        request = load_thread_config_request(ThreadConfigContext(thread_id="thread-1", cwd=Path("/tmp/project")))

        self.assertEqual(
            request,
            {
                "thread_id": "thread-1",
                "cwd": str(Path("/tmp/project")),
                "timeout_seconds": 5,
                "grpc_timeout": "5000000u",
            },
        )

    def test_remote_status_to_error_maps_auth_timeout_and_request_failures(self) -> None:
        # Rust source: thread_config::remote::remote_status_to_error.
        self.assertEqual(remote_status_to_error({"code": "Unauthenticated"}).code(), ThreadConfigLoadErrorCode.AUTH)
        self.assertEqual(remote_status_to_error({"code": "permission-denied"}).code(), ThreadConfigLoadErrorCode.AUTH)
        self.assertEqual(remote_status_to_error({"code": "DeadlineExceeded"}).code(), ThreadConfigLoadErrorCode.TIMEOUT)
        self.assertEqual(remote_status_to_error({"code": "Unavailable"}).code(), ThreadConfigLoadErrorCode.REQUEST_FAILED)
        self.assertIn("remote thread config request failed", str(remote_status_to_error({"code": "Unavailable"})))

    def test_remote_proto_conversion_round_trips_provider_and_sources(self) -> None:
        # Rust remote tests: model_provider_proto_roundtrips_through_domain_type,
        # plus source conversion used by load_thread_config_calls_remote_service.
        provider_id, provider = model_provider_from_proto(_test_provider_proto("local"))

        self.assertEqual(provider_id, "local")
        self.assertEqual(provider["name"], "Local")
        self.assertEqual(provider["wire_api"], "responses")
        self.assertEqual(provider["auth"]["command"], "token-helper")
        self.assertEqual(provider["auth"]["timeout_ms"], 5000)

        session = session_thread_config_from_proto(
            {
                "model_provider": "local",
                "model_providers": [_test_provider_proto("local")],
                "features": {"tools": True, "plugins": False},
            }
        )
        source = thread_config_source_from_proto({"session": session.__dict__})

        self.assertEqual(source.kind, "session")
        self.assertEqual(source.config.model_provider, "local")
        self.assertEqual(source.config.features, {"plugins": False, "tools": True})
        self.assertEqual(thread_config_source_from_proto({"user": {}}), ThreadConfigSource.user())

    def test_remote_proto_parse_errors_fail_closed(self) -> None:
        # Rust source: remote parse_error paths for missing source, missing id,
        # omitted/unknown wire_api, zero timeout, and invalid cwd.
        cases = [
            lambda: thread_config_source_from_proto({}),
            lambda: model_provider_from_proto({"id": "", "wire_api": "responses"}),
            lambda: model_provider_from_proto({"id": "local", "wire_api": "unspecified"}),
            lambda: model_provider_from_proto({"id": "local", "wire_api": "unknown"}),
            lambda: model_provider_auth_from_proto({"command": "x", "args": [], "timeout_ms": 0, "cwd": "/tmp"}),
            lambda: model_provider_auth_from_proto({"command": "x", "args": [], "timeout_ms": 1, "cwd": "relative"}),
        ]

        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(ThreadConfigLoadError) as raised:
                    case()
                self.assertEqual(raised.exception.code(), ThreadConfigLoadErrorCode.PARSE)

    def test_remote_loader_uses_injected_client_boundary(self) -> None:
        # The Python port keeps concrete gRPC out of scope, but preserves the
        # loader contract through an injectable client boundary.
        requests = []

        async def client(request):
            requests.append(request)
            return {
                "sources": [
                    {
                        "session": {
                            "model_provider": "local",
                            "model_providers": [_test_provider_proto("local")],
                            "features": {"plugins": False},
                        }
                    },
                    {"user": {}},
                ]
            }

        loader = RemoteThreadConfigLoader.new("http://127.0.0.1:1", client=client)
        loaded = run(loader.load(ThreadConfigContext(thread_id="thread-1", cwd=Path("/tmp/project"))))

        self.assertEqual(requests[0]["thread_id"], "thread-1")
        self.assertEqual(requests[0]["grpc_timeout"], "5000000u")
        self.assertEqual(
            loaded,
            [
                ThreadConfigSource.session(
                    SessionThreadConfig(
                        model_provider="local",
                        model_providers={"local": model_provider_from_proto(_test_provider_proto("local"))[1]},
                        features={"plugins": False},
                    )
                ),
                ThreadConfigSource.user(),
            ],
        )


def _test_provider(name: str) -> dict[str, object]:
    return {
        "name": name,
        "base_url": "http://127.0.0.1:8061/api/codex",
        "wire_api": "responses",
        "requires_openai_auth": False,
        "supports_websockets": True,
    }


def _test_provider_proto(provider_id: str) -> dict[str, object]:
    return {
        "id": provider_id,
        "name": "Local",
        "base_url": "http://127.0.0.1:8061/api/codex",
        "wire_api": "responses",
        "auth": {
            "command": "token-helper",
            "args": ["--json"],
            "timeout_ms": 5000,
            "refresh_interval_ms": 300000,
            "cwd": str(Path.cwd()),
        },
        "query_params": {"api-version": "2026-04-16"},
        "http_headers": {"X-Test": "enabled"},
        "env_http_headers": {"X-Env": "LOCAL_HEADER"},
        "request_max_retries": 7,
        "stream_max_retries": 8,
        "stream_idle_timeout_ms": 9000,
        "websocket_connect_timeout_ms": 10000,
        "requires_openai_auth": False,
        "supports_websockets": True,
    }


if __name__ == "__main__":
    unittest.main()
