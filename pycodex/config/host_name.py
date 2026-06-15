"""Best-effort host-name helpers ported from ``codex-config``."""

from __future__ import annotations

import socket
from functools import lru_cache


@lru_cache(maxsize=1)
def host_name() -> str | None:
    """Return a normalized local host name, preferring an FQDN when available."""

    return _compute_host_name()


def _compute_host_name() -> str | None:
    kernel_hostname = _normalize_host_name(socket.gethostname())
    if kernel_hostname is None:
        return None
    fqdn = _local_fqdn_for_hostname(kernel_hostname)
    if fqdn is not None:
        return fqdn
    return kernel_hostname


def _normalize_host_name(hostname: str) -> str | None:
    normalized = str(hostname).strip().rstrip(".")
    if not normalized:
        return None
    return normalized.lower()


def _local_fqdn_for_hostname(hostname: str) -> str | None:
    try:
        fqdn = socket.getfqdn(hostname)
    except OSError:
        return None
    return _normalize_fqdn_candidate(fqdn)


def _normalize_fqdn_candidate(hostname: str) -> str | None:
    normalized = _normalize_host_name(hostname)
    if normalized is None or "." not in normalized:
        return None
    return normalized


__all__ = [
    "host_name",
]
