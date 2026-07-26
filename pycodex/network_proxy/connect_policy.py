"""Rust-aligned projection of ``codex-network-proxy::connect_policy``."""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import fnmatch
import json
import os
import re
import socket
import stat
import sys
import time
from datetime import UTC, datetime
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qsl, urlparse
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, Mapping, Sequence

JsonValue = Any

class TargetRejectedError(PermissionError):
    """Raised when connect_policy rejects a direct TCP target."""


@dataclass(frozen=True)
class TargetCheckedTcpConnector:
    policy: bool | NetworkProxyState

    @classmethod
    def new(cls, state: NetworkProxyState) -> "TargetCheckedTcpConnector":
        return cls(state)

    @classmethod
    def from_allow_local_binding(cls, allow_local_binding: bool) -> "TargetCheckedTcpConnector":
        return cls(bool(allow_local_binding))

    async def allow_local_binding(self) -> bool:
        if isinstance(self.policy, bool):
            return self.policy
        return await _network_proxy_state_allow_local_binding(self.policy)

    async def check_target(
        self,
        host: str,
        port: int,
        *,
        proxy_address: object | None = None,
    ) -> None:
        if proxy_address is not None:
            return
        if not await self.allow_local_binding():
            try:
                address = ipaddress.ip_address(_unscoped_ip_literal(normalize_host(host)) or normalize_host(host))
            except ValueError:
                return
            if is_non_public_ip(address):
                raise TargetRejectedError("network target rejected by policy")

    async def connect(
        self,
        host: str,
        port: int,
        *,
        timeout: float | None = None,
        proxy_address: object | None = None,
    ) -> socket.socket:
        await self.check_target(host, port, proxy_address=proxy_address)
        return socket.create_connection((host, port), timeout=timeout)

from .policy import (
    _unscoped_ip_literal,
    is_non_public_ip,
    normalize_host,
)
from .runtime import (
    NetworkProxyState,
    _network_proxy_state_allow_local_binding,
)

__all__ = [
    "TargetCheckedTcpConnector",
    "TargetRejectedError",
]
