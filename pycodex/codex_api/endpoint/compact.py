"""Compact endpoint client for the Rust ``codex-api/src/endpoint/compact.rs`` contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from typing import Mapping

from pycodex.codex_client import HttpTransport
from pycodex.codex_client import TransportError
from pycodex.protocol import ResponseItem

from ..auth import SharedAuthProvider
from ..common import CompactionInput
from ..error import ApiError
from ..provider import Provider
from .models import _apply_auth
from .models import _merged_headers


@dataclass(frozen=True)
class CompactClient:
    transport: HttpTransport
    provider: Provider
    auth: SharedAuthProvider
    request_telemetry: object | None = None

    def with_telemetry(self, request: object | None) -> "CompactClient":
        return CompactClient(
            transport=self.transport,
            provider=self.provider,
            auth=self.auth,
            request_telemetry=request,
        )

    @staticmethod
    def path() -> str:
        return "responses/compact"

    async def compact(
        self,
        body: Any,
        extra_headers: Mapping[str, str] | None = None,
        request_timeout: float | None = None,
    ) -> tuple[ResponseItem, ...]:
        req = self.provider.build_request("POST", self.path()).with_headers(
            _merged_headers(self.provider.headers, extra_headers)
        )
        req = req.with_json(body)
        if request_timeout is not None:
            req = _with_timeout(req, request_timeout)
        req = await _apply_auth(self.auth, req)

        try:
            resp = self.transport.execute(req)
        except TransportError as exc:
            raise ApiError.transport_error(exc) from exc

        try:
            payload = json.loads(resp.body.decode("utf-8"))
            output = payload["output"]
            if not isinstance(output, list):
                raise TypeError("output must be a list")
            return tuple(ResponseItem.from_mapping(item) for item in output)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ApiError.stream(str(exc)) from exc

    async def compact_input(
        self,
        input: CompactionInput,
        extra_headers: Mapping[str, str] | None = None,
        request_timeout: float | None = None,
    ) -> tuple[ResponseItem, ...]:
        try:
            body = input.to_json_dict()
        except (TypeError, ValueError) as exc:
            raise ApiError.stream(f"failed to encode compaction input: {exc}") from exc
        return await self.compact(body, extra_headers, request_timeout)


def _with_timeout(req, timeout: float):
    return type(req)(
        method=req.method,
        url=req.url,
        headers=req.headers,
        body=req.body,
        compression=req.compression,
        timeout=timeout,
    )
