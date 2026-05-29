"""Configuration planning helpers for ``codex exec``.

Ported from the pre-``ConfigBuilder`` slice of
``codex/codex-rs/exec/src/lib.rs``.  The full config loader is still being
ported elsewhere; this module keeps the CLI-to-harness override projection
explicit and testable so the eventual runner can feed the same values into the
Python app-server path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.config import ConfigOverride
from pycodex.core.agents_md import (
    DEFAULT_PROJECT_DOC_MAX_BYTES,
    AgentsMdConfig,
    AgentsMdManager,
)
from pycodex.core.paths import find_codex_home
from pycodex.protocol import AskForApproval, SandboxMode

from .cli import ExecCli

JsonValue = Any

UPSTREAM_EXEC_RUN_MAIN = "codex/codex-rs/exec/src/lib.rs"
LMSTUDIO_OSS_PROVIDER_ID = "lmstudio"
OLLAMA_OSS_PROVIDER_ID = "ollama"
LMSTUDIO_DEFAULT_OSS_MODEL = "openai/gpt-oss-20b"
OLLAMA_DEFAULT_OSS_MODEL = "gpt-oss:20b"
NO_DEFAULT_OSS_PROVIDER_MESSAGE = (
    "No default OSS provider configured. Use --local-provider=provider or set oss_provider "
    f"to one of: {LMSTUDIO_OSS_PROVIDER_ID}, {OLLAMA_OSS_PROVIDER_ID} in config.toml"
)


class ExecConfigPlanError(ValueError):
    """Raised when ``codex exec`` config planning cannot continue."""


@dataclass(frozen=True)
class ExecHarnessOverrides:
    """Subset of upstream ``ConfigOverrides`` supplied by ``codex exec``."""

    model: str | None = None
    approval_policy: AskForApproval | None = AskForApproval.NEVER
    sandbox_mode: SandboxMode | None = None
    cwd: Path | None = None
    model_provider: str | None = None
    show_raw_agent_reasoning: bool | None = None
    ephemeral: bool | None = None
    bypass_hook_trust: bool | None = None
    additional_writable_roots: tuple[Path, ...] = ()
    upstream_source: str = UPSTREAM_EXEC_RUN_MAIN

    def __post_init__(self) -> None:
        if self.cwd is not None and not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        object.__setattr__(
            self,
            "additional_writable_roots",
            tuple(Path(root) for root in self.additional_writable_roots),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "model": self.model,
            "approvalPolicy": _enum_value(self.approval_policy),
            "sandboxMode": _enum_value(self.sandbox_mode),
            "cwd": str(self.cwd) if self.cwd is not None else None,
            "modelProvider": self.model_provider,
            "showRawAgentReasoning": self.show_raw_agent_reasoning,
            "ephemeral": self.ephemeral,
            "bypassHookTrust": self.bypass_hook_trust,
            "additionalWritableRoots": [str(root) for root in self.additional_writable_roots],
        }
        return {key: value for key, value in data.items() if value is not None and value != []}


@dataclass(frozen=True)
class ExecConfigBootstrapPlan:
    """Values resolved before upstream builds the full runtime ``Config``."""

    config_cwd: Path
    strict_config: bool = False
    ignore_user_config: bool = False
    ignore_rules: bool = False
    cli_overrides: tuple[ConfigOverride, ...] = ()
    harness_overrides: ExecHarnessOverrides = ExecHarnessOverrides()
    user_instructions: str | None = None
    instruction_sources: tuple[Path, ...] = ()
    startup_warnings: tuple[str, ...] = ()
    upstream_source: str = UPSTREAM_EXEC_RUN_MAIN

    def __post_init__(self) -> None:
        if not isinstance(self.config_cwd, Path):
            object.__setattr__(self, "config_cwd", Path(self.config_cwd))
        object.__setattr__(self, "cli_overrides", tuple(self.cli_overrides))
        object.__setattr__(self, "instruction_sources", tuple(Path(path) for path in self.instruction_sources))
        object.__setattr__(self, "startup_warnings", tuple(str(warning) for warning in self.startup_warnings))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "configCwd": str(self.config_cwd),
            "strictConfig": self.strict_config,
            "ignoreUserConfig": self.ignore_user_config,
            "ignoreRules": self.ignore_rules,
            "cliOverrides": [
                {"path": override.path, "value": override.value} for override in self.cli_overrides
            ],
            "harnessOverrides": self.harness_overrides.to_mapping(),
            "userInstructions": self.user_instructions,
            "instructionSources": [str(path) for path in self.instruction_sources],
            "startupWarnings": list(self.startup_warnings),
        }


def exec_sandbox_mode_from_cli(cli: ExecCli) -> SandboxMode | None:
    """Resolve the upstream sandbox-mode precedence for ``codex exec``."""

    if cli.removed_full_auto:
        return SandboxMode.WORKSPACE_WRITE
    if cli.dangerously_bypass_approvals_and_sandbox:
        return SandboxMode.DANGER_FULL_ACCESS
    return cli.sandbox


def resolve_oss_provider(explicit_provider: str | None, config_toml: Mapping[str, JsonValue] | None) -> str | None:
    """Return the explicit OSS provider or the global ``oss_provider`` value."""

    if explicit_provider is not None:
        return explicit_provider
    if config_toml is None:
        return None
    provider = config_toml.get("oss_provider")
    return provider if isinstance(provider, str) and provider else None


def get_default_model_for_oss_provider(provider_id: str) -> str | None:
    """Mirror upstream OSS default model lookup."""

    if provider_id == LMSTUDIO_OSS_PROVIDER_ID:
        return LMSTUDIO_DEFAULT_OSS_MODEL
    if provider_id == OLLAMA_OSS_PROVIDER_ID:
        return OLLAMA_DEFAULT_OSS_MODEL
    return None


def exec_model_provider_override(cli: ExecCli, config_toml: Mapping[str, JsonValue] | None = None) -> str | None:
    if cli.local_provider is not None:
        return cli.local_provider
    if cli.oss:
        provider = resolve_oss_provider(cli.local_provider, config_toml)
        if provider is None:
            raise ExecConfigPlanError(NO_DEFAULT_OSS_PROVIDER_MESSAGE)
        return provider
    if config_toml is None:
        return None
    provider = config_toml.get("model_provider")
    return provider if isinstance(provider, str) and provider else None


def exec_model_override(
    cli: ExecCli,
    model_provider: str | None = None,
    config_toml: Mapping[str, JsonValue] | None = None,
) -> str | None:
    if cli.model is not None:
        return cli.model
    if cli.oss and model_provider is not None:
        return get_default_model_for_oss_provider(model_provider)
    if config_toml is not None:
        model = config_toml.get("model")
        if isinstance(model, str) and model:
            return model
    return None


def exec_harness_overrides_from_cli(
    cli: ExecCli,
    config_toml: Mapping[str, JsonValue] | None = None,
) -> ExecHarnessOverrides:
    """Build the harness override slice that upstream passes to ``ConfigBuilder``."""

    model_provider = exec_model_provider_override(cli, config_toml)
    return ExecHarnessOverrides(
        model=exec_model_override(cli, model_provider, config_toml),
        approval_policy=AskForApproval.NEVER,
        sandbox_mode=exec_sandbox_mode_from_cli(cli),
        cwd=Path(cli.cwd) if cli.cwd is not None else None,
        model_provider=model_provider,
        show_raw_agent_reasoning=True if cli.oss else None,
        ephemeral=True if cli.ephemeral else None,
        bypass_hook_trust=True if cli.dangerously_bypass_hook_trust else None,
        additional_writable_roots=tuple(Path(path) for path in cli.add_dir),
    )


def resolve_exec_config_cwd(cli: ExecCli, current_dir: str | Path | None = None) -> Path:
    """Resolve the cwd used to load config, matching upstream's existing path check."""

    if cli.cwd is None:
        return Path.cwd() if current_dir is None else Path(current_dir)
    candidate = Path(cli.cwd)
    if not candidate.is_absolute() and current_dir is not None:
        candidate = Path(current_dir) / candidate
    try:
        return candidate.resolve(strict=True)
    except OSError as exc:
        raise ExecConfigPlanError(f"Failed to resolve -C/--cd path {cli.cwd}: {exc}") from exc


def build_exec_config_bootstrap_plan(
    cli: ExecCli,
    *,
    config_toml: Mapping[str, JsonValue] | None = None,
    current_dir: str | Path | None = None,
) -> ExecConfigBootstrapPlan:
    """Plan the config inputs that precede full app-server startup."""

    config_cwd = resolve_exec_config_cwd(cli, current_dir)
    warnings: list[str] = []
    user_instructions, instruction_sources = _resolve_exec_user_instructions(
        config_cwd,
        config_toml,
        warnings,
    )
    return ExecConfigBootstrapPlan(
        config_cwd=config_cwd,
        strict_config=cli.strict_config,
        ignore_user_config=cli.ignore_user_config,
        ignore_rules=cli.ignore_rules,
        cli_overrides=tuple(cli.cli_config_overrides().parse_overrides()),
        harness_overrides=exec_harness_overrides_from_cli(cli, config_toml),
        user_instructions=user_instructions,
        instruction_sources=instruction_sources,
        startup_warnings=tuple(warnings),
    )


def _enum_value(value: Enum | None) -> str | None:
    return value.value if isinstance(value, Enum) else None


def _resolve_exec_user_instructions(
    cwd: Path,
    config_toml: Mapping[str, JsonValue] | None,
    warnings: list[str],
) -> tuple[str | None, tuple[Path, ...]]:
    config = config_toml or {}
    codex_home = _maybe_codex_home()
    manager = AgentsMdManager(
        AgentsMdConfig(
            cwd=cwd,
            codex_home=codex_home,
            user_instructions=_optional_str(config.get("user_instructions")),
            project_doc_max_bytes=_project_doc_max_bytes(config.get("project_doc_max_bytes")),
            project_doc_fallback_filenames=_string_tuple(config.get("project_doc_fallback_filenames")),
            project_root_markers=_optional_string_tuple(config.get("project_root_markers")),
            child_agents_md=_bool_value(config.get("child_agents_md"), False),
        )
    )
    return manager.user_instructions(warnings), tuple(manager.instruction_sources())


def _maybe_codex_home() -> Path | None:
    try:
        return find_codex_home()
    except (FileNotFoundError, NotADirectoryError, OSError):
        return None


def _optional_str(value: JsonValue) -> str | None:
    return value if isinstance(value, str) and value else None


def _project_doc_max_bytes(value: JsonValue) -> int:
    if isinstance(value, bool):
        return DEFAULT_PROJECT_DOC_MAX_BYTES
    if isinstance(value, int) and value >= 0:
        return value
    return DEFAULT_PROJECT_DOC_MAX_BYTES


def _string_tuple(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _optional_string_tuple(value: JsonValue) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _string_tuple(value)


def _bool_value(value: JsonValue, default: bool) -> bool:
    return value if isinstance(value, bool) else default


__all__ = [
    "ExecConfigBootstrapPlan",
    "ExecConfigPlanError",
    "ExecHarnessOverrides",
    "LMSTUDIO_DEFAULT_OSS_MODEL",
    "LMSTUDIO_OSS_PROVIDER_ID",
    "NO_DEFAULT_OSS_PROVIDER_MESSAGE",
    "OLLAMA_DEFAULT_OSS_MODEL",
    "OLLAMA_OSS_PROVIDER_ID",
    "UPSTREAM_EXEC_RUN_MAIN",
    "build_exec_config_bootstrap_plan",
    "exec_harness_overrides_from_cli",
    "exec_model_override",
    "exec_model_provider_override",
    "exec_sandbox_mode_from_cli",
    "get_default_model_for_oss_provider",
    "resolve_exec_config_cwd",
    "resolve_oss_provider",
]
