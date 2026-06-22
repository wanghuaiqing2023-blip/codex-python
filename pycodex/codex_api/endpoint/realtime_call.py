"""Realtime call endpoint client for Rust ``codex-api/src/endpoint/realtime_call.rs``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from pycodex.codex_client import HttpTransport
from pycodex.codex_client import TransportError

from ..auth import SharedAuthProvider
from ..error import ApiError
from ..provider import Provider
from .models import _apply_auth
from .models import _merged_headers
from .realtime_websocket import REALTIME_AUDIO_SAMPLE_RATE
from .realtime_websocket import RealtimeEventParser
from .realtime_websocket import RealtimeSessionConfig
from .realtime_websocket import RealtimeSessionMode
from .realtime_websocket import session_update_session_json
from .realtime_websocket.methods_v2 import REALTIME_V2_BACKGROUND_AGENT_TOOL_DESCRIPTION
from .realtime_websocket.methods_v2 import REALTIME_V2_BACKGROUND_AGENT_TOOL_NAME
from .realtime_websocket.methods_v2 import REALTIME_V2_INPUT_TRANSCRIPTION_MODEL
from .realtime_websocket.methods_v2 import REALTIME_V2_SILENCE_TOOL_DESCRIPTION
from .realtime_websocket.methods_v2 import REALTIME_V2_SILENCE_TOOL_NAME
from .realtime_websocket.methods_v2 import REALTIME_V2_TOOL_CHOICE


MULTIPART_BOUNDARY = "codex-realtime-call-boundary"
MULTIPART_CONTENT_TYPE = "multipart/form-data; boundary=codex-realtime-call-boundary"


@dataclass(frozen=True)
class RealtimeCallResponse:
    sdp: str
    call_id: str


@dataclass(frozen=True)
class RealtimeCallClient:
    transport: HttpTransport
    provider: Provider
    auth: SharedAuthProvider
    request_telemetry: object | None = None

    def with_telemetry(self, request: object | None) -> "RealtimeCallClient":
        return RealtimeCallClient(
            transport=self.transport,
            provider=self.provider,
            auth=self.auth,
            request_telemetry=request,
        )

    @staticmethod
    def path() -> str:
        return "realtime/calls"

    def uses_backend_request_shape(self) -> bool:
        return "/backend-api" in self.provider.base_url

    async def create(self, sdp: str) -> RealtimeCallResponse:
        return await self.create_with_headers(sdp, {})

    async def create_with_session(
        self,
        sdp: str,
        session_config: RealtimeSessionConfig,
    ) -> RealtimeCallResponse:
        return await self.create_with_session_and_headers(sdp, session_config, {})

    async def create_with_headers(
        self,
        sdp: str,
        extra_headers: Mapping[str, str] | None = None,
    ) -> RealtimeCallResponse:
        headers = _merged_headers(self.provider.headers, extra_headers)
        headers["content-type"] = "application/sdp"
        request = self.provider.build_request("POST", self.path()).with_headers(headers)
        request = request.with_raw_body(sdp)
        request = await _apply_auth(self.auth, request)
        response = self._execute(request)
        return RealtimeCallResponse(
            sdp=_decode_sdp_response(response.body),
            call_id=_decode_call_id_from_location(response.headers),
        )

    async def create_with_session_and_headers(
        self,
        sdp: str,
        session_config: RealtimeSessionConfig,
        extra_headers: Mapping[str, str] | None = None,
    ) -> RealtimeCallResponse:
        session = session_update_session_json(session_config)
        session.pop("id", None)

        if self.uses_backend_request_shape():
            body = {"sdp": sdp, "session": session}
            request = self.provider.build_request("POST", self.path()).with_headers(
                _merged_headers(self.provider.headers, extra_headers)
            )
            request = request.with_json(body)
            request = await _apply_auth(self.auth, request)
            response = self._execute(request)
            return RealtimeCallResponse(
                sdp=_decode_sdp_response(response.body),
                call_id=_decode_call_id_from_location(response.headers),
            )

        session_json = json.dumps(session, separators=(",", ":"), ensure_ascii=False)
        multipart = (
            f"--{MULTIPART_BOUNDARY}\r\n"
            'Content-Disposition: form-data; name="sdp"\r\n'
            "Content-Type: application/sdp\r\n"
            "\r\n"
            f"{sdp}"
            "\r\n"
            f"--{MULTIPART_BOUNDARY}\r\n"
            'Content-Disposition: form-data; name="session"\r\n'
            "Content-Type: application/json\r\n"
            "\r\n"
            f"{session_json}\r\n"
            f"--{MULTIPART_BOUNDARY}--\r\n"
        )
        headers = _merged_headers(self.provider.headers, extra_headers)
        headers["content-type"] = MULTIPART_CONTENT_TYPE
        request = self.provider.build_request("POST", self.path()).with_headers(headers)
        request = request.with_raw_body(multipart)
        request = await _apply_auth(self.auth, request)
        response = self._execute(request)
        return RealtimeCallResponse(
            sdp=_decode_sdp_response(response.body),
            call_id=_decode_call_id_from_location(response.headers),
        )

    def _execute(self, request: Any) -> Any:
        try:
            return self.transport.execute(request)
        except TransportError as exc:
            raise ApiError.transport_error(exc) from exc


def _decode_sdp_response(body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ApiError.stream(f"failed to decode realtime call SDP response: {exc}") from exc


def _decode_call_id_from_location(headers: Mapping[str, str]) -> str:
    location = _header_value(headers, "location")
    if location is None:
        raise ApiError.stream("realtime call response missing Location")
    location_without_query = location.split("?", 1)[0]
    for segment in reversed(location_without_query.split("/")):
        if segment.startswith("rtc_") and len(segment) > len("rtc_"):
            return segment
    raise ApiError.stream(f"realtime call Location does not contain a call id: {location}")


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    lower_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lower_name:
            return value
    return None
