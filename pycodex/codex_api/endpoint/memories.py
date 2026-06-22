"""Memories endpoint client for Rust ``codex-api/src/endpoint/memories.rs``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from pycodex.codex_client import HttpTransport
from pycodex.codex_client import TransportError

from ..auth import SharedAuthProvider
from ..common import MemorySummarizeInput
from ..common import MemorySummarizeOutput
from ..error import ApiError
from ..provider import Provider
from .models import _apply_auth
from .models import _merged_headers


@dataclass(frozen=True)
class MemoriesClient:
    """Client for ``memories/trace_summarize`` matching the Rust endpoint."""

    transport: HttpTransport
    provider: Provider
    auth: SharedAuthProvider
    request_telemetry: object | None = None

    def with_telemetry(self, request: object | None) -> "MemoriesClient":
        return MemoriesClient(
            transport=self.transport,
            provider=self.provider,
            auth=self.auth,
            request_telemetry=request,
        )

    @staticmethod
    def path() -> str:
        return "memories/trace_summarize"

    async def summarize(
        self,
        body: Any,
        extra_headers: Mapping[str, str] | None = None,
    ) -> tuple[MemorySummarizeOutput, ...]:
        request = self.provider.build_request("POST", self.path()).with_headers(
            _merged_headers(self.provider.headers, extra_headers)
        )
        request = request.with_json(body)
        request = await _apply_auth(self.auth, request)

        try:
            response = self.transport.execute(request)
        except TransportError as exc:
            raise ApiError.transport_error(exc) from exc

        try:
            payload = json.loads(response.body.decode("utf-8"))
            output = payload["output"]
            if not isinstance(output, list):
                raise TypeError("output must be a list")
            return tuple(MemorySummarizeOutput.from_json_dict(item) for item in output)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ApiError.stream(str(exc)) from exc

    async def summarize_input(
        self,
        input: MemorySummarizeInput,
        extra_headers: Mapping[str, str] | None = None,
    ) -> tuple[MemorySummarizeOutput, ...]:
        try:
            body = input.to_json_dict()
        except (TypeError, ValueError) as exc:
            raise ApiError.stream(f"failed to encode memory summarize input: {exc}") from exc
        return await self.summarize(body, extra_headers)
