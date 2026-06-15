import asyncio
import json
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from pycodex.model_provider.models_endpoint import OpenAiModelsEndpoint
from pycodex.model_provider_info import ModelProviderInfo
from pycodex.models_manager.model_info import model_info_from_slug
from pycodex.protocol import ModelVisibility


class _Server:
    def __init__(self, body: dict, *, etag: str | None = None) -> None:
        self.requests: list[dict[str, object]] = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                requests.append(
                    {
                        "path": self.path,
                        "authorization": self.headers.get("Authorization"),
                    }
                )
                payload = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                if etag is not None:
                    self.send_header("ETag", etag)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format, *args):
                return None

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address
        return f"http://{host}:{port}/v1"

    def close(self) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=5)
        self.httpd.server_close()


def _model_mapping(slug: str) -> dict:
    model = replace(
        model_info_from_slug(slug),
        visibility=ModelVisibility.LIST,
        supported_in_api=True,
        priority=0,
        used_fallback_model_metadata=False,
    )
    return {
        "slug": model.slug,
        "display_name": model.display_name,
        "description": model.description,
        "default_reasoning_level": "medium",
        "supported_reasoning_levels": [],
        "shell_type": model.shell_type.value,
        "visibility": model.visibility.value,
        "supported_in_api": model.supported_in_api,
        "priority": model.priority,
        "upgrade": None,
        "base_instructions": model.base_instructions,
        "model_messages": None,
        "supports_reasoning_summaries": model.supports_reasoning_summaries,
        "support_verbosity": model.support_verbosity,
        "default_verbosity": None,
        "apply_patch_tool_type": None,
        "truncation_policy": {
            "mode": model.truncation_policy.mode.value,
            "limit": model.truncation_policy.limit,
        },
        "supports_parallel_tool_calls": model.supports_parallel_tool_calls,
        "supports_image_detail_original": model.supports_image_detail_original,
        "context_window": model.context_window,
        "max_context_window": model.max_context_window,
        "experimental_supported_tools": [],
    }


def test_openai_models_endpoint_fetches_models_with_client_version_and_etag() -> None:
    # Rust crate/module: codex-model-provider::models_endpoint via codex-api ModelsClient.
    server = _Server({"models": [_model_mapping("endpoint-model")]}, etag='"abc"')
    try:
        provider = ModelProviderInfo(
            name="test",
            base_url=server.url,
            experimental_bearer_token="provider-token",
        )
        endpoint = OpenAiModelsEndpoint(provider)

        response, etag = asyncio.run(endpoint.list_models("0.99.0"))

        assert [model.slug for model in response.models] == ["endpoint-model"]
        assert etag == '"abc"'
        assert server.requests == [
            {
                "path": "/v1/models?client_version=0.99.0",
                "authorization": "Bearer provider-token",
            }
        ]
    finally:
        server.close()


def test_openai_models_endpoint_preserves_existing_query_params() -> None:
    # Rust behavior: client_version appends with '&' when the request already has a query.
    server = _Server({"models": []})
    try:
        provider = ModelProviderInfo(name="test", base_url=f"{server.url}?api-version=2026-01-01")
        endpoint = OpenAiModelsEndpoint(provider)

        response, etag = asyncio.run(endpoint.list_models("1.2.3"))

        assert response.models == ()
        assert etag is None
        assert server.requests[0]["path"] == "/v1/models?api-version=2026-01-01&client_version=1.2.3"
    finally:
        server.close()


def test_openai_models_endpoint_reports_command_auth_and_backend_usage() -> None:
    # Rust crate/module: codex-model-provider::models_endpoint
    provider = ModelProviderInfo(auth={"command": "print-token", "cwd": "."})
    endpoint = OpenAiModelsEndpoint(provider)

    assert endpoint.has_command_auth() is True
    assert asyncio.run(endpoint.uses_codex_backend()) is False
