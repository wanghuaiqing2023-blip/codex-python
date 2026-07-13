"""Per-account Windows Firewall rules for the offline sandbox identity.

Rust owner: ``setup_main::win::firewall`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.

The fixed Rust helper uses Firewall COM directly.  Python invokes the same COM
objects through an elevated, non-interactive PowerShell process so setup stays
stdlib-only while preserving the account-scoped rule contract.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from .setup_error import SetupErrorCode, SetupFailure


OFFLINE_BLOCK_RULE_NAME = "codex_sandbox_offline_block_outbound"
OFFLINE_BLOCK_LOOPBACK_TCP_RULE_NAME = "codex_sandbox_offline_block_loopback_tcp"
OFFLINE_BLOCK_LOOPBACK_UDP_RULE_NAME = "codex_sandbox_offline_block_loopback_udp"
OFFLINE_PROXY_ALLOW_RULE_NAME = "codex_sandbox_offline_allow_loopback_proxy"
LOOPBACK_REMOTE_ADDRESSES = "127.0.0.0/8,::/127"
NON_LOOPBACK_REMOTE_ADDRESSES = (
    "0.0.0.0-126.255.255.255,128.0.0.0-255.255.255.255,"
    "::,::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"
)


@dataclass(frozen=True)
class FirewallRuleSpec:
    name: str
    description: str
    protocol: int
    remote_addresses: str
    remote_ports: str | None = None


def blocked_loopback_tcp_remote_ports(proxy_ports: list[int] | tuple[int, ...]) -> str | None:
    allowed = sorted({port for port in proxy_ports if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535})
    ranges: list[str] = []
    start = 1
    for port in allowed:
        if port > start:
            ranges.append(_range_text(start, port - 1))
        start = max(start, port + 1)
    if start <= 65535:
        ranges.append(_range_text(start, 65535))
    return ",".join(ranges) or None


def offline_rule_specs(proxy_ports: list[int] | tuple[int, ...], allow_local_binding: bool) -> tuple[FirewallRuleSpec, ...]:
    specs = [FirewallRuleSpec(
        OFFLINE_BLOCK_RULE_NAME,
        "Codex Sandbox Offline - Block Non-Loopback Outbound",
        256,
        NON_LOOPBACK_REMOTE_ADDRESSES,
    )]
    if allow_local_binding:
        return tuple(specs)
    specs.append(FirewallRuleSpec(
        OFFLINE_BLOCK_LOOPBACK_UDP_RULE_NAME,
        "Codex Sandbox Offline - Block Loopback UDP",
        17,
        LOOPBACK_REMOTE_ADDRESSES,
    ))
    blocked_ports = blocked_loopback_tcp_remote_ports(proxy_ports)
    if blocked_ports is not None:
        specs.append(FirewallRuleSpec(
            OFFLINE_BLOCK_LOOPBACK_TCP_RULE_NAME,
            "Codex Sandbox Offline - Block Loopback TCP (Except Proxy)",
            6,
            LOOPBACK_REMOTE_ADDRESSES,
            blocked_ports,
        ))
    return tuple(specs)


def install_offline_firewall_rules(
    offline_sid: str,
    proxy_ports: list[int] | tuple[int, ...],
    allow_local_binding: bool,
) -> None:
    if not offline_sid.startswith("S-1-"):
        raise ValueError("offline_sid must be a SID string")
    specs = offline_rule_specs(proxy_ports, allow_local_binding) + wfp_defense_rule_specs()
    payload = json.dumps([spec.__dict__ for spec in specs], separators=(",", ":"))
    removals = json.dumps(
        sorted({
            OFFLINE_BLOCK_RULE_NAME,
            OFFLINE_BLOCK_LOOPBACK_TCP_RULE_NAME,
            OFFLINE_BLOCK_LOOPBACK_UDP_RULE_NAME,
            OFFLINE_PROXY_ALLOW_RULE_NAME,
            *(spec.name for spec in wfp_defense_rule_specs()),
        }),
        separators=(",", ":"),
    )
    script = _FIREWALL_SCRIPT.replace("__SID__", _ps_quote(offline_sid)).replace(
        "__SPECS__", _ps_quote(payload)
    ).replace("__REMOVALS__", _ps_quote(removals))
    completed = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown firewall error").strip()
        raise SetupFailure(
            SetupErrorCode.HELPER_FIREWALL_RULE_CREATE_OR_ADD_FAILED,
            detail,
        )


def wfp_defense_rule_specs() -> tuple[FirewallRuleSpec, ...]:
    """Project fixed WFP filter behavior onto account-scoped firewall rules.

    Windows Firewall rules are enforced by the Base Filtering Engine/WFP.  The
    names and blocked protocol/port surfaces mirror ``wfp/filter_specs.rs``;
    raw persistent-provider parity remains separately auditable.
    """

    any_address = "*"
    return (
        FirewallRuleSpec("codex_wfp_icmp_connect_v4", "Block sandbox-account ICMP connect v4", 1, any_address),
        FirewallRuleSpec("codex_wfp_icmp_connect_v6", "Block sandbox-account ICMP connect v6", 58, any_address),
        FirewallRuleSpec("codex_wfp_dns_53_tcp", "Block sandbox-account DNS TCP port 53", 6, any_address, "53"),
        FirewallRuleSpec("codex_wfp_dns_53_udp", "Block sandbox-account DNS UDP port 53", 17, any_address, "53"),
        FirewallRuleSpec("codex_wfp_dns_853_tcp", "Block sandbox-account DNS-over-TLS port 853", 6, any_address, "853"),
        FirewallRuleSpec("codex_wfp_smb_445_tcp", "Block sandbox-account SMB port 445", 6, any_address, "445"),
        FirewallRuleSpec("codex_wfp_smb_139_tcp", "Block sandbox-account SMB port 139", 6, any_address, "139"),
    )


def _range_text(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


_FIREWALL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$sid = __SID__
$specs = ConvertFrom-Json __SPECS__
$removeNames = ConvertFrom-Json __REMOVALS__
$policy = New-Object -ComObject HNetCfg.FwPolicy2
$rules = $policy.Rules
foreach ($name in $removeNames) { try { $rules.Remove([string]$name) } catch {} }
$localUser = "O:LSD:(A;;CC;;;$sid)"
foreach ($spec in $specs) {
  $rule = New-Object -ComObject HNetCfg.FWRule
  $rule.Name = [string]$spec.name
  $rule.Description = [string]$spec.description
  $rule.Direction = 2
  $rule.Action = 0
  $rule.Enabled = $true
  $rule.Profiles = 2147483647
  $rule.Protocol = [int]$spec.protocol
  $rule.RemoteAddresses = [string]$spec.remote_addresses
  if ($null -ne $spec.remote_ports) { $rule.RemotePorts = [string]$spec.remote_ports }
  $rule.LocalUserAuthorizedList = $localUser
  $rules.Add($rule)
  $stored = $rules.Item([string]$spec.name)
  if (-not ([string]$stored.LocalUserAuthorizedList).Contains($sid)) {
    throw "firewall rule user scope mismatch for $($spec.name)"
  }
}
"""


__all__ = [
    "FirewallRuleSpec",
    "blocked_loopback_tcp_remote_ports",
    "install_offline_firewall_rules",
    "offline_rule_specs",
    "wfp_defense_rule_specs",
]
