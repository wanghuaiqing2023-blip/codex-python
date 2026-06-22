from pathlib import Path

from pycodex.linux_sandbox import landlock
from pycodex.protocol import NetworkSandboxPolicy, PermissionProfile


def test_managed_network_enforces_seccomp_even_for_full_network_policy() -> None:
    # Rust source: linux-sandbox/src/landlock.rs
    # managed_network_enforces_seccomp_even_for_full_network_policy.
    assert landlock.should_install_network_seccomp(
        NetworkSandboxPolicy.ENABLED,
        allow_network_for_proxy=True,
    )


def test_full_network_policy_without_managed_network_skips_seccomp() -> None:
    # Rust source: full_network_policy_without_managed_network_skips_seccomp.
    assert not landlock.should_install_network_seccomp(
        NetworkSandboxPolicy.ENABLED,
        allow_network_for_proxy=False,
    )


def test_restricted_network_policy_always_installs_seccomp() -> None:
    # Rust source: restricted_network_policy_always_installs_seccomp.
    assert landlock.should_install_network_seccomp(
        NetworkSandboxPolicy.RESTRICTED,
        allow_network_for_proxy=False,
    )
    assert landlock.should_install_network_seccomp(
        NetworkSandboxPolicy.RESTRICTED,
        allow_network_for_proxy=True,
    )


def test_managed_proxy_routes_use_proxy_routed_seccomp_mode() -> None:
    # Rust source: managed_proxy_routes_use_proxy_routed_seccomp_mode.
    assert (
        landlock.network_seccomp_mode(
            NetworkSandboxPolicy.ENABLED,
            allow_network_for_proxy=True,
            proxy_routed_network=True,
        )
        is landlock.NetworkSeccompMode.PROXY_ROUTED
    )


def test_restricted_network_without_proxy_routing_uses_restricted_mode() -> None:
    # Rust source: restricted_network_without_proxy_routing_uses_restricted_mode.
    assert (
        landlock.network_seccomp_mode(
            NetworkSandboxPolicy.RESTRICTED,
            allow_network_for_proxy=False,
            proxy_routed_network=False,
        )
        is landlock.NetworkSeccompMode.RESTRICTED
    )


def test_full_network_without_managed_proxy_skips_network_seccomp_mode() -> None:
    # Rust source: full_network_without_managed_proxy_skips_network_seccomp_mode.
    assert (
        landlock.network_seccomp_mode(
            NetworkSandboxPolicy.ENABLED,
            allow_network_for_proxy=False,
            proxy_routed_network=False,
        )
        is None
    )


def test_apply_permission_profile_invokes_hooks_from_plan() -> None:
    calls: list[object] = []

    plan = landlock.apply_permission_profile_to_current_thread(
        PermissionProfile.external(NetworkSandboxPolicy.ENABLED),
        Path("/workspace"),
        apply_landlock_fs=False,
        allow_network_for_proxy=True,
        proxy_routed_network=True,
        set_no_new_privs_hook=lambda: calls.append("no_new_privs"),
        install_network_seccomp_hook=lambda mode: calls.append(mode),
    )

    assert plan.set_no_new_privs is True
    assert plan.network_seccomp_mode is landlock.NetworkSeccompMode.PROXY_ROUTED
    assert calls == ["no_new_privs", landlock.NetworkSeccompMode.PROXY_ROUTED]
