from __future__ import annotations

from pathlib import Path

import pycodex.utils.sandbox_summary as sandbox_summary
from pycodex.utils.sandbox_summary import (
    create_config_summary_entries,
    summarize_permission_profile,
    summarize_sandbox_policy,
)


class WorkspaceWriteProfile:
    def to_legacy_sandbox_policy(self, cwd: Path) -> dict[str, object]:
        return {
            "kind": "workspace-write",
            "network_access": False,
            "exclude_tmpdir_env_var": False,
            "exclude_slash_tmp": False,
            "writable_roots": [Path("/hidden/internal")],
        }


class ApprovalPolicy:
    def __init__(self, value: str) -> None:
        self._value = value

    def value(self) -> str:
        return self._value


class Permissions:
    def __init__(self, approval_policy: ApprovalPolicy, sandbox_policy: dict[str, object]) -> None:
        self.approval_policy = approval_policy
        self._sandbox_policy = sandbox_policy

    def legacy_sandbox_policy(self, cwd: Path) -> dict[str, object]:
        return self._sandbox_policy


class ModelProvider:
    def __init__(self, wire_api: str) -> None:
        self.wire_api = wire_api


class Config:
    def __init__(
        self,
        *,
        wire_api: str = "chat",
        reasoning_effort: str | None = None,
        reasoning_summary: str | None = None,
    ) -> None:
        self.cwd = Path("/repo")
        self.model_provider_id = "openai"
        self.permissions = Permissions(ApprovalPolicy("on-request"), {"kind": "read-only", "network_access": False})
        self.model_provider = ModelProvider(wire_api)
        self.model_reasoning_effort = reasoning_effort
        self.model_reasoning_summary = reasoning_summary


def test_lib_rs_public_reexports_match_python_public_surface() -> None:
    # Source: codex/codex-rs/utils/sandbox-summary/src/lib.rs
    # Contract: crate root publicly re-exports the two sandbox helpers and config summary helper.
    assert set(sandbox_summary.__all__) == {
        "create_config_summary_entries",
        "summarize_permission_profile",
        "summarize_sandbox_policy",
    }


def test_config_summary_entries_include_base_effective_config_values() -> None:
    # Source: codex/codex-rs/utils/sandbox-summary/src/config_summary.rs
    # Contract: base entries are workdir, model, provider, approval, and sandbox.
    assert create_config_summary_entries(Config(), "gpt-5") == [
        ("workdir", str(Path("/repo"))),
        ("model", "gpt-5"),
        ("provider", "openai"),
        ("approval", "on-request"),
        ("sandbox", "read-only"),
    ]


def test_config_summary_entries_add_reasoning_values_for_responses_api() -> None:
    # Source: codex/codex-rs/utils/sandbox-summary/src/config_summary.rs
    # Contract: Responses API configs append reasoning effort and summaries, defaulting to none.
    assert create_config_summary_entries(Config(wire_api="responses"), "gpt-5")[-2:] == [
        ("reasoning effort", "none"),
        ("reasoning summaries", "none"),
    ]
    assert create_config_summary_entries(
        Config(wire_api="responses", reasoning_effort="high", reasoning_summary="detailed"),
        "gpt-5",
    )[-2:] == [
        ("reasoning effort", "high"),
        ("reasoning summaries", "detailed"),
    ]


def test_summarizes_external_sandbox_without_network_access_suffix() -> None:
    # Source: codex/codex-rs/utils/sandbox-summary/src/sandbox_summary.rs
    # Rust test: tests::summarizes_external_sandbox_without_network_access_suffix
    assert summarize_sandbox_policy({"kind": "external-sandbox", "network_access": "restricted"}) == "external-sandbox"


def test_summarizes_external_sandbox_with_enabled_network() -> None:
    # Source: codex/codex-rs/utils/sandbox-summary/src/sandbox_summary.rs
    # Rust test: tests::summarizes_external_sandbox_with_enabled_network
    assert (
        summarize_sandbox_policy({"kind": "external-sandbox", "network_access": "enabled"})
        == "external-sandbox (network access enabled)"
    )


def test_summarizes_read_only_with_enabled_network() -> None:
    # Source: codex/codex-rs/utils/sandbox-summary/src/sandbox_summary.rs
    # Rust test: tests::summarizes_read_only_with_enabled_network
    assert (
        summarize_sandbox_policy({"kind": "read-only", "network_access": True})
        == "read-only (network access enabled)"
    )


def test_workspace_write_summary_still_includes_network_access() -> None:
    # Source: codex/codex-rs/utils/sandbox-summary/src/sandbox_summary.rs
    # Rust test: tests::workspace_write_summary_still_includes_network_access
    assert (
        summarize_sandbox_policy(
            {
                "kind": "workspace-write",
                "writable_roots": [Path("/repo")],
                "network_access": True,
                "exclude_tmpdir_env_var": True,
                "exclude_slash_tmp": True,
            }
        )
        == f"workspace-write [workdir, {Path('/repo')}] (network access enabled)"
    )


def test_permission_profile_summary_uses_runtime_workspace_roots_and_hides_internal_writes() -> None:
    # Source: codex/codex-rs/utils/sandbox-summary/src/sandbox_summary.rs
    # Rust test: tests::permission_profile_summary_uses_runtime_workspace_roots_and_hides_internal_writes
    assert (
        summarize_permission_profile(WorkspaceWriteProfile(), Path("/repo"), [Path("/repo"), Path("/repo-extra")])
        == f"workspace-write [workdir, /tmp, $TMPDIR, {Path('/repo-extra')}]"
    )
