"""Network proxy specification owned by ``core::config::network_proxy_spec``."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pycodex.config.config_requirements import NetworkConstraints
from pycodex.network_proxy.config import (
    NetworkDomainPermission,
    NetworkProxyConfig,
    _host_and_port_from_url,
    _string_tuple,
)
from pycodex.network_proxy.network_policy import ask_not_allowed_policy_decider
from pycodex.network_proxy.policy import normalize_host
from pycodex.network_proxy.runtime import (
    ConfigState,
    NetworkProxyAuditMetadata,
    NetworkProxyState,
)
from pycodex.network_proxy.state import (
    NetworkProxyConstraints,
    _clone_network_proxy_config,
    _clone_network_proxy_constraints,
)

JsonValue = Any
@dataclass(frozen=True)
class StartedNetworkProxy:
    proxy_value: Any
    handle: Any

    def proxy(self) -> Any:
        return self.proxy_value

@dataclass(frozen=True)
class StaticNetworkProxyReloader:
    state: ConfigState

    async def maybe_reload(self) -> None:
        return None

    async def reload_now(self) -> ConfigState:
        return self.state

    def source_label(self) -> str:
        return "StaticNetworkProxyReloader"

NetworkProxyBuilderCallback = Callable[
    [NetworkProxyState, object, object | None, object | None, bool, NetworkProxyAuditMetadata],
    StartedNetworkProxy | Awaitable[StartedNetworkProxy],
]

@dataclass(frozen=True)
class NetworkProxySpec:
    base_config: NetworkProxyConfig
    requirements: NetworkConstraints | None
    config: NetworkProxyConfig
    constraints: NetworkProxyConstraints
    hard_deny_allowlist_misses: bool = False

    @classmethod
    def from_config_and_constraints(
        cls,
        config: NetworkProxyConfig,
        requirements: NetworkConstraints | None,
        permission_profile: object,
    ) -> "NetworkProxySpec":
        if not isinstance(config, NetworkProxyConfig):
            raise TypeError("config must be NetworkProxyConfig")
        if requirements is not None and not isinstance(requirements, NetworkConstraints):
            raise TypeError("requirements must be NetworkConstraints")
        base_config = _clone_network_proxy_config(config)
        if requirements is None:
            return cls(base_config, None, _clone_network_proxy_config(config), NetworkProxyConstraints())
        hard_deny = cls.managed_allowed_domains_only(requirements)
        effective, constraints = cls.apply_requirements(
            _clone_network_proxy_config(config),
            requirements,
            permission_profile,
            hard_deny,
        )
        return cls(base_config, requirements, effective, constraints, hard_deny)

    def enabled(self) -> bool:
        return self.config.network.enabled

    def proxy_host_and_port(self) -> str:
        return _host_and_port_from_url(self.config.network.proxy_url, 3128)

    def socks_enabled(self) -> bool:
        return self.config.network.enable_socks5

    async def start_proxy(
        self,
        permission_profile: object,
        policy_decider: object | None,
        blocked_request_observer: object | None,
        enable_network_approval_flow: bool,
        audit_metadata: NetworkProxyAuditMetadata | Mapping[str, JsonValue] | None,
        *,
        network_proxy_builder: NetworkProxyBuilderCallback,
    ) -> StartedNetworkProxy:
        if not isinstance(enable_network_approval_flow, bool):
            raise TypeError("enable_network_approval_flow must be a bool")
        if audit_metadata is None:
            audit_metadata = NetworkProxyAuditMetadata()
        elif isinstance(audit_metadata, Mapping):
            audit_metadata = NetworkProxyAuditMetadata(dict(audit_metadata))
        elif not isinstance(audit_metadata, NetworkProxyAuditMetadata):
            raise TypeError("audit_metadata must be NetworkProxyAuditMetadata, mapping, or None")
        if not callable(network_proxy_builder):
            raise TypeError("network_proxy_builder must be callable")
        effective_policy_decider = policy_decider
        if (
            enable_network_approval_flow
            and not self.hard_deny_allowlist_misses
            and effective_policy_decider is None
            and self.managed_sandbox_active(permission_profile)
        ):
            effective_policy_decider = ask_not_allowed_policy_decider
        state = self.build_state_with_audit_metadata(audit_metadata)
        started = network_proxy_builder(
            state,
            permission_profile,
            effective_policy_decider,
            blocked_request_observer,
            enable_network_approval_flow,
            audit_metadata,
        )
        if inspect.isawaitable(started):
            started = await started
        if not isinstance(started, StartedNetworkProxy):
            raise TypeError("network_proxy_builder must return StartedNetworkProxy")
        return started

    def recompute_for_permission_profile(self, permission_profile: object) -> "NetworkProxySpec":
        return type(self).from_config_and_constraints(self.base_config, self.requirements, permission_profile)

    def with_exec_policy_network_rules(self, exec_policy: object) -> "NetworkProxySpec":
        config = _clone_network_proxy_config(self.config)
        apply_exec_policy_network_rules(config, exec_policy)
        return type(self)(
            _clone_network_proxy_config(self.base_config),
            self.requirements,
            config,
            _clone_network_proxy_constraints(self.constraints),
            self.hard_deny_allowlist_misses,
        )

    async def apply_to_started_proxy(self, started_proxy: StartedNetworkProxy) -> None:
        if not isinstance(started_proxy, StartedNetworkProxy):
            raise TypeError("started_proxy must be StartedNetworkProxy")
        proxy = started_proxy.proxy()
        replacer = getattr(proxy, "replace_config_state", None)
        if not callable(replacer):
            raise AttributeError("started proxy must provide replace_config_state")
        result = replacer(self.build_config_state_for_spec())
        if inspect.isawaitable(result):
            await result

    def build_state_with_audit_metadata(
        self,
        audit_metadata: NetworkProxyAuditMetadata | Mapping[str, JsonValue] | None,
    ) -> NetworkProxyState:
        if audit_metadata is None:
            audit_metadata = NetworkProxyAuditMetadata()
        elif isinstance(audit_metadata, Mapping):
            audit_metadata = NetworkProxyAuditMetadata(dict(audit_metadata))
        elif not isinstance(audit_metadata, NetworkProxyAuditMetadata):
            raise TypeError("audit_metadata must be NetworkProxyAuditMetadata, mapping, or None")
        state = self.build_config_state_for_spec()
        return NetworkProxyState(
            state,
            reloader=StaticNetworkProxyReloader(state),
            audit_metadata=audit_metadata,
        )

    def build_config_state_for_spec(self) -> ConfigState:
        return ConfigState(
            _clone_network_proxy_config(self.config),
            _clone_network_proxy_constraints(self.constraints),
        )

    @staticmethod
    def apply_requirements(
        config: NetworkProxyConfig,
        requirements: NetworkConstraints,
        permission_profile: object,
        hard_deny_allowlist_misses: bool,
    ) -> tuple[NetworkProxyConfig, NetworkProxyConstraints]:
        constraints = NetworkProxyConstraints()
        allowlist_expansion_enabled = NetworkProxySpec.allowlist_expansion_enabled(
            permission_profile,
            hard_deny_allowlist_misses,
        )
        denylist_expansion_enabled = NetworkProxySpec.denylist_expansion_enabled(permission_profile)

        if requirements.enabled is not None:
            config.network.enabled = requirements.enabled
            constraints.enabled = requirements.enabled
        if requirements.http_port is not None:
            config.network.proxy_url = f"http://127.0.0.1:{requirements.http_port}"
        if requirements.socks_port is not None:
            config.network.socks_url = f"http://127.0.0.1:{requirements.socks_port}"
        if requirements.allow_upstream_proxy is not None:
            config.network.allow_upstream_proxy = requirements.allow_upstream_proxy
            constraints.allow_upstream_proxy = requirements.allow_upstream_proxy
        if requirements.dangerously_allow_non_loopback_proxy is not None:
            config.network.dangerously_allow_non_loopback_proxy = requirements.dangerously_allow_non_loopback_proxy
            constraints.dangerously_allow_non_loopback_proxy = requirements.dangerously_allow_non_loopback_proxy
        if requirements.dangerously_allow_all_unix_sockets is not None:
            config.network.dangerously_allow_all_unix_sockets = requirements.dangerously_allow_all_unix_sockets
            constraints.dangerously_allow_all_unix_sockets = requirements.dangerously_allow_all_unix_sockets

        managed_allowed_domains = _allowed_domains(requirements.domains)
        if hard_deny_allowlist_misses:
            managed_allowed_domains = managed_allowed_domains or []
        if managed_allowed_domains is not None:
            user_allowed = config.network.allowed_domains() or []
            effective_allowed = (
                NetworkProxySpec.merge_domain_lists(managed_allowed_domains, user_allowed)
                if allowlist_expansion_enabled
                else list(managed_allowed_domains)
            )
            user_denied = set(config.network.denied_domains() or [])
            config.network.set_allowed_domains([domain for domain in effective_allowed if normalize_host(domain) not in user_denied])
            constraints.allowed_domains = list(managed_allowed_domains)
            constraints.allowlist_expansion_enabled = allowlist_expansion_enabled

        managed_denied_domains = _denied_domains(requirements.domains)
        if managed_denied_domains is not None:
            user_denied = config.network.denied_domains() or []
            effective_denied = (
                NetworkProxySpec.merge_domain_lists(managed_denied_domains, user_denied)
                if denylist_expansion_enabled
                else list(managed_denied_domains)
            )
            config.network.set_denied_domains(effective_denied)
            constraints.denied_domains = list(managed_denied_domains)
            constraints.denylist_expansion_enabled = denylist_expansion_enabled

        if requirements.unix_sockets is not None:
            sockets = list(_string_tuple(requirements.unix_sockets, "network unix sockets"))
            config.network.set_allow_unix_sockets(sockets)
            constraints.allow_unix_sockets = sockets
        if requirements.allow_local_binding is not None:
            config.network.allow_local_binding = requirements.allow_local_binding
            constraints.allow_local_binding = requirements.allow_local_binding
        return config, constraints

    @staticmethod
    def allowlist_expansion_enabled(permission_profile: object, hard_deny_allowlist_misses: bool) -> bool:
        return NetworkProxySpec.managed_sandbox_active(permission_profile) and not hard_deny_allowlist_misses

    @staticmethod
    def managed_allowed_domains_only(requirements: NetworkConstraints) -> bool:
        return bool(requirements.managed_allowed_domains_only)

    @staticmethod
    def denylist_expansion_enabled(permission_profile: object) -> bool:
        return NetworkProxySpec.managed_sandbox_active(permission_profile)

    @staticmethod
    def managed_sandbox_active(permission_profile: object) -> bool:
        return getattr(permission_profile, "type", None) == "managed"

    @staticmethod
    def merge_domain_lists(managed: Sequence[str], user_entries: Sequence[str]) -> list[str]:
        merged = list(_string_tuple(managed, "managed domains"))
        for entry in _string_tuple(user_entries, "user domains"):
            if not any(existing.lower() == entry.lower() for existing in merged):
                merged.append(entry)
        return merged

def apply_exec_policy_network_rules(config: NetworkProxyConfig, exec_policy: object) -> None:
    allowed_domains, denied_domains = _compiled_network_domains(exec_policy)
    for host in allowed_domains:
        upsert_network_domain(config, host, NetworkDomainPermission.ALLOW)
    for host in denied_domains:
        upsert_network_domain(config, host, NetworkDomainPermission.DENY)


def upsert_network_domain(
    config: NetworkProxyConfig,
    host: str,
    permission: NetworkDomainPermission,
) -> None:
    config.network.upsert_domain_permission(host, permission)


def _compiled_network_domains(exec_policy: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    compiled = getattr(exec_policy, "compiled_network_domains", None)
    if callable(compiled):
        allowed, denied = compiled()
        return _string_tuple(allowed, "allowed domains"), _string_tuple(denied, "denied domains")
    return (
        _string_tuple(getattr(exec_policy, "allowed_domains", ()), "allowed domains"),
        _string_tuple(getattr(exec_policy, "denied_domains", ()), "denied domains"),
    )


def _allowed_domains(
    domains: Mapping[str, str | NetworkDomainPermission] | None,
) -> list[str] | None:
    if domains is None:
        return None
    allowed = [
        normalize_host(host)
        for host, permission in domains.items()
        if NetworkDomainPermission(permission) is NetworkDomainPermission.ALLOW
    ]
    return allowed or None


def _denied_domains(
    domains: Mapping[str, str | NetworkDomainPermission] | None,
) -> list[str] | None:
    if domains is None:
        return None
    denied = [
        normalize_host(host)
        for host, permission in domains.items()
        if NetworkDomainPermission(permission) is NetworkDomainPermission.DENY
    ]
    return denied or None


__all__ = ["NetworkProxySpec", "StartedNetworkProxy"]
