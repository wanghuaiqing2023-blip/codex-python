"""Attestation helpers ported from ``codex-app-server/src/attestation.rs``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


ATTESTATION_GENERATE_TIMEOUT_MILLIS = 100


class AppServerAttestationStatus(Enum):
    """Rust ``AppServerAttestationStatus`` wire codes."""

    OK = 0
    TIMEOUT = 1
    REQUEST_FAILED = 2
    REQUEST_CANCELED = 3
    MALFORMED_RESPONSE = 4

    @property
    def code(self) -> int:
        return int(self.value)


@dataclass(frozen=True)
class AttestationRequestProjection:
    """Decision trace for Rust attestation header generation."""

    selected_connection_id: Any = None
    send_request: bool = False
    cancel_request: bool = False
    status: AppServerAttestationStatus | None = None
    header_value: str | None = None


def app_server_attestation_header_value(
    status: AppServerAttestationStatus | int | str,
    token: str | None = None,
) -> str:
    """Mirror Rust's compact JSON attestation envelope serialization."""

    status_value = _attestation_status(status)
    envelope: dict[str, Any] = {"v": 1, "s": status_value.code}
    if token is not None:
        envelope["t"] = token
    return json.dumps(envelope, separators=(",", ":"))


def attestation_request_projection(
    outcome: str,
    *,
    connection_id: Any = "connection-1",
    token: str | None = None,
) -> AttestationRequestProjection:
    """Project Rust's request result mapping without executing async transport."""

    if outcome == "no_connection":
        return AttestationRequestProjection()
    if outcome == "ok":
        return AttestationRequestProjection(
            selected_connection_id=connection_id,
            send_request=True,
            status=AppServerAttestationStatus.OK,
            header_value=app_server_attestation_header_value(AppServerAttestationStatus.OK, token or ""),
        )
    if outcome == "request_failed":
        return _failure_projection(connection_id, AppServerAttestationStatus.REQUEST_FAILED)
    if outcome == "request_canceled":
        return _failure_projection(connection_id, AppServerAttestationStatus.REQUEST_CANCELED)
    if outcome == "timeout":
        failure = _failure_projection(connection_id, AppServerAttestationStatus.TIMEOUT)
        return AttestationRequestProjection(
            selected_connection_id=failure.selected_connection_id,
            send_request=failure.send_request,
            cancel_request=True,
            status=failure.status,
            header_value=failure.header_value,
        )
    if outcome == "malformed_response":
        return _failure_projection(connection_id, AppServerAttestationStatus.MALFORMED_RESPONSE)
    raise ValueError(f"unknown attestation outcome: {outcome}")


def _failure_projection(
    connection_id: Any,
    status: AppServerAttestationStatus,
) -> AttestationRequestProjection:
    return AttestationRequestProjection(
        selected_connection_id=connection_id,
        send_request=True,
        status=status,
        header_value=app_server_attestation_header_value(status),
    )


def _attestation_status(status: AppServerAttestationStatus | int | str) -> AppServerAttestationStatus:
    if isinstance(status, AppServerAttestationStatus):
        return status
    if isinstance(status, int):
        return AppServerAttestationStatus(status)
    normalized = status.strip().lower().replace("-", "_")
    aliases = {
        "ok": AppServerAttestationStatus.OK,
        "timeout": AppServerAttestationStatus.TIMEOUT,
        "request_failed": AppServerAttestationStatus.REQUEST_FAILED,
        "request_canceled": AppServerAttestationStatus.REQUEST_CANCELED,
        "malformed_response": AppServerAttestationStatus.MALFORMED_RESPONSE,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(f"unknown attestation status: {status}") from exc


__all__ = [
    "ATTESTATION_GENERATE_TIMEOUT_MILLIS",
    "AppServerAttestationStatus",
    "AttestationRequestProjection",
    "app_server_attestation_header_value",
    "attestation_request_projection",
]
