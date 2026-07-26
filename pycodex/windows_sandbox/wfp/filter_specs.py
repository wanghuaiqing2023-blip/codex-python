"""Fixed Windows Filtering Platform filter definitions.

Rust owner: ``codex-windows-sandbox::wfp::filter_specs``.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import (
    GUID,
    LAYER_ASSIGN_V4,
    LAYER_ASSIGN_V6,
    LAYER_CONNECT_V4,
    LAYER_CONNECT_V6,
)


@dataclass(frozen=True)
class ConditionSpec:
    kind: str
    value: int | None = None


@dataclass(frozen=True)
class FilterSpec:
    key: str
    name: str
    description: str
    layer: GUID
    protocol: int | None = None
    remote_port: int | None = None

    @property
    def conditions(self) -> tuple[ConditionSpec, ...]:
        conditions = [ConditionSpec("user")]
        if self.protocol is not None:
            conditions.append(ConditionSpec("protocol", self.protocol))
        if self.remote_port is not None:
            conditions.append(ConditionSpec("remote_port", self.remote_port))
        return tuple(conditions)


FILTER_SPECS = (
    FilterSpec("9f5f3812-79f0-4fe9-9615-4c2c92d2f0ff", "codex_wfp_icmp_connect_v4", "Block sandbox-account ICMP connect v4", LAYER_CONNECT_V4, protocol=1),
    FilterSpec("87498484-45ab-4510-845e-ece8b791b3bc", "codex_wfp_icmp_connect_v6", "Block sandbox-account ICMP connect v6", LAYER_CONNECT_V6, protocol=58),
    FilterSpec("af4751de-f874-4a7b-a34d-f0d0f22d1d9b", "codex_wfp_icmp_assign_v4", "Block sandbox-account ICMP resource assignment v4", LAYER_ASSIGN_V4, protocol=1),
    FilterSpec("ea10db66-a928-4b2e-a82e-a376a54f93ba", "codex_wfp_icmp_assign_v6", "Block sandbox-account ICMP resource assignment v6", LAYER_ASSIGN_V6, protocol=58),
    FilterSpec("83172805-f6be-4ae1-9dc6-6847aef04e7f", "codex_wfp_dns_53_v4", "Block sandbox-account DNS TCP or UDP port 53 v4", LAYER_CONNECT_V4, remote_port=53),
    FilterSpec("d23b2efb-1efb-46b2-96f3-b0ccda5690c8", "codex_wfp_dns_53_v6", "Block sandbox-account DNS TCP or UDP port 53 v6", LAYER_CONNECT_V6, remote_port=53),
    FilterSpec("420b026f-9dc9-4aea-88f4-0f2b9feab39a", "codex_wfp_dns_853_v4", "Block sandbox-account DNS-over-TLS port 853 v4", LAYER_CONNECT_V4, remote_port=853),
    FilterSpec("8d917c81-99cc-45e7-84d6-824df860cfb8", "codex_wfp_dns_853_v6", "Block sandbox-account DNS-over-TLS port 853 v6", LAYER_CONNECT_V6, remote_port=853),
    FilterSpec("e1d6e0af-ce5f-471b-b2d3-15ca00e966f3", "codex_wfp_smb_445_v4", "Block sandbox-account SMB port 445 v4", LAYER_CONNECT_V4, remote_port=445),
    FilterSpec("c2bceca4-66ef-4a0f-ba80-f4f761b8c6f0", "codex_wfp_smb_445_v6", "Block sandbox-account SMB port 445 v6", LAYER_CONNECT_V6, remote_port=445),
    FilterSpec("ba10c618-84e7-4b83-8f74-36e22b2fa1ff", "codex_wfp_smb_139_v4", "Block sandbox-account SMB port 139 v4", LAYER_CONNECT_V4, remote_port=139),
    FilterSpec("fe7f22b8-5cf5-4adb-b2aa-71fc0a8f5d44", "codex_wfp_smb_139_v6", "Block sandbox-account SMB port 139 v6", LAYER_CONNECT_V6, remote_port=139),
)


__all__ = ["ConditionSpec", "FILTER_SPECS", "FilterSpec"]
