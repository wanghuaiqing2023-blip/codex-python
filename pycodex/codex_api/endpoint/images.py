"""Images endpoint client for the Rust ``codex-api/src/endpoint/images.rs`` contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from typing import Mapping

from pycodex.codex_client import HttpTransport
from pycodex.codex_client import TransportError

from ..auth import SharedAuthProvider
from ..error import ApiError
from ..images import ImageEditRequest
from ..images import ImageGenerationRequest
from ..images import ImageResponse
from ..provider import Provider
from .models import _apply_auth
from .models import _merged_headers


@dataclass(frozen=True)
class ImagesClient:
    transport: HttpTransport
    provider: Provider
    auth: SharedAuthProvider
    request_telemetry: object | None = None

    def with_telemetry(self, request: object | None) -> "ImagesClient":
        return ImagesClient(
            transport=self.transport,
            provider=self.provider,
            auth=self.auth,
            request_telemetry=request,
        )

    async def generate(
        self,
        request: ImageGenerationRequest,
        extra_headers: Mapping[str, str] | None = None,
    ) -> ImageResponse:
        return await self._post_image_request(
            "images/generations",
            request.to_json_dict(),
            extra_headers,
            "image generation",
        )

    async def edit(
        self,
        request: ImageEditRequest,
        extra_headers: Mapping[str, str] | None = None,
    ) -> ImageResponse:
        return await self._post_image_request(
            "images/edits",
            request.to_json_dict(),
            extra_headers,
            "image edit",
        )

    async def _post_image_request(
        self,
        path: str,
        body: Mapping[str, Any],
        extra_headers: Mapping[str, str] | None,
        operation: str,
    ) -> ImageResponse:
        req = self.provider.build_request("POST", path).with_headers(
            _merged_headers(self.provider.headers, extra_headers)
        )
        req = req.with_json(dict(body))
        req = await _apply_auth(self.auth, req)

        try:
            resp = self.transport.execute(req)
        except TransportError as exc:
            raise ApiError.transport_error(exc) from exc

        try:
            payload = json.loads(resp.body.decode("utf-8"))
            return ImageResponse.from_json_dict(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ApiError.stream(f"failed to decode {operation} response: {exc}") from exc

