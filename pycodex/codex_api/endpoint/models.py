"""Models endpoint client for the Rust ``codex-api/src/endpoint/models.rs`` contract."""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Mapping

from pycodex.codex_client import HttpTransport
from pycodex.codex_client import Request
from pycodex.codex_client import Response
from pycodex.codex_client import TransportError
from pycodex.protocol import ModelInfo
from pycodex.protocol import ModelsResponse

from ..auth import SharedAuthProvider
from ..error import ApiError
from ..provider import Provider


@dataclass(frozen=True)
class ModelsClient:
    transport: HttpTransport
    provider: Provider
    auth: SharedAuthProvider
    request_telemetry: object | None = None

    def with_telemetry(self, request: object | None) -> "ModelsClient":
        return ModelsClient(
            transport=self.transport,
            provider=self.provider,
            auth=self.auth,
            request_telemetry=request,
        )

    @staticmethod
    def path() -> str:
        return "models"

    @staticmethod
    def append_client_version_query(req: Request, client_version: str) -> Request:
        separator = "&" if "?" in req.url else "?"
        return Request(
            method=req.method,
            url=f"{req.url}{separator}client_version={client_version}",
            headers=req.headers,
            body=req.body,
            compression=req.compression,
            timeout=req.timeout,
        )

    async def list_models(
        self,
        client_version: str,
        extra_headers: Mapping[str, str] | None = None,
    ) -> tuple[tuple[ModelInfo, ...], str | None]:
        req = self.provider.build_request("GET", self.path()).with_headers(
            _merged_headers(self.provider.headers, extra_headers)
        )
        req = self.append_client_version_query(req, client_version)
        req = await _apply_auth(self.auth, req)

        try:
            resp = self.transport.execute(req)
        except TransportError as exc:
            raise ApiError.transport_error(exc) from exc

        etag = _header_value(resp.headers, "etag")
        response = _decode_models_response(resp)
        return response.models, etag


async def _apply_auth(auth: SharedAuthProvider, request: Request) -> Request:
    apply_auth = getattr(auth, "apply_auth", None)
    if callable(apply_auth):
        result = apply_auth(request)
        if inspect.isawaitable(result):
            return await result
        return result

    headers = dict(request.headers or {})
    auth.add_auth_headers(headers)
    return request.with_headers(headers)


def _merged_headers(
    provider_headers: Mapping[str, str] | None,
    extra_headers: Mapping[str, str] | None,
) -> dict[str, str]:
    headers = dict(provider_headers or {})
    headers.update(dict(extra_headers or {}))
    return headers


def _decode_models_response(resp: Response) -> ModelsResponse:
    try:
        payload = json.loads(resp.body.decode("utf-8"))
        return ModelsResponse.from_mapping(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        body = resp.body.decode("utf-8", "replace")
        raise ApiError.stream(f"failed to decode models response: {exc}; body: {body}") from exc


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value)
    return None

