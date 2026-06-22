"""Search endpoint client for the Rust ``codex-api/src/endpoint/search.rs`` contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping

from pycodex.codex_client import HttpTransport
from pycodex.codex_client import TransportError

from ..auth import SharedAuthProvider
from ..error import ApiError
from ..provider import Provider
from ..search import SearchRequest
from ..search import SearchResponse
from .models import _apply_auth
from .models import _merged_headers


@dataclass(frozen=True)
class SearchClient:
    transport: HttpTransport
    provider: Provider
    auth: SharedAuthProvider
    request_telemetry: object | None = None

    def with_telemetry(self, request: object | None) -> "SearchClient":
        return SearchClient(
            transport=self.transport,
            provider=self.provider,
            auth=self.auth,
            request_telemetry=request,
        )

    @staticmethod
    def path() -> str:
        return "alpha/search"

    async def search(
        self,
        request: SearchRequest,
        extra_headers: Mapping[str, str] | None = None,
    ) -> SearchResponse:
        req = self.provider.build_request("POST", self.path()).with_headers(
            _merged_headers(self.provider.headers, extra_headers)
        )
        try:
            req = req.with_json(request.to_json_dict())
        except (TypeError, ValueError) as exc:
            raise ApiError.stream(f"failed to encode search request: {exc}") from exc
        req = await _apply_auth(self.auth, req)

        try:
            resp = self.transport.execute(req)
        except TransportError as exc:
            raise ApiError.transport_error(exc) from exc

        try:
            payload = json.loads(resp.body.decode("utf-8"))
            return SearchResponse.from_json_dict(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ApiError.stream(f"failed to decode search response: {exc}") from exc

