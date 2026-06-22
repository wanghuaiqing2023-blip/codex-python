"""Config layer loading helpers ported from ``codex-config::loader``.

The full Rust module also owns asynchronous layer orchestration. This Python
module starts with the deterministic helpers that define loader-local behavior:
well-known paths, layer precedence insertion, project-local sanitizing, trust
lookup normalization, relative path resolution, and legacy managed-config
backfill.
"""

from __future__ import annotations

import base64
import binascii
import sys
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

from pycodex.network_proxy import ConfigLayerSource
from pycodex.protocol.config_types import ApprovalsReviewer, AskForApproval, SandboxMode, TrustLevel

from . import toml_compat as _toml
from .config_requirements import (
    ConfigRequirements,
    ConfigRequirementsToml,
    ConfigRequirementsWithSources,
    SandboxModeRequirement,
)
from .config_toml import ConfigToml, ProjectConfig
from .constraint import RequirementSource
from .merge import merge_toml_values
from .overrides import CliConfigOverrides, ConfigOverride, build_cli_overrides_layer
from .project_root_markers import default_project_root_markers, project_root_markers_from_config
from .state import ConfigLayerEntry, ConfigLayerStack, ConfigLoadOptions, LoaderOverrides
from .strict_config import unknown_feature_toml_value_field

JsonValue = Any

CONFIG_TOML_FILE = "config.toml"
REQUIREMENTS_TOML_FILE = "requirements.toml"
CODEX_MANAGED_CONFIG_SYSTEM_PATH = PurePosixPath("/etc/codex/managed_config.toml")
SYSTEM_CONFIG_TOML_FILE_UNIX = PurePosixPath("/etc/codex/config.toml")
SYSTEM_REQUIREMENTS_TOML_FILE_UNIX = PurePosixPath("/etc/codex/requirements.toml")
DEFAULT_PROGRAM_DATA_DIR_WINDOWS = PureWindowsPath("C:/ProgramData")
MANAGED_PREFERENCES_APPLICATION_ID = "com.openai.codex"
MANAGED_PREFERENCES_CONFIG_KEY = "config_toml_base64"
MANAGED_PREFERENCES_REQUIREMENTS_KEY = "requirements_toml_base64"

PROJECT_LOCAL_CONFIG_DENYLIST: tuple[str, ...] = (
    "openai_base_url",
    "chatgpt_base_url",
    "apps_mcp_product_sku",
    "model_provider",
    "model_providers",
    "notify",
    "profile",
    "profiles",
    "experimental_realtime_ws_base_url",
    "otel",
)

_ABSOLUTE_PATH_KEYS = {
    "model_instructions_file",
    "experimental_compact_prompt_file",
    "js_repl_node_path",
    "sqlite_home",
    "log_dir",
    "model_catalog_json",
    "config_file",
    "load_path",
    "export_dir",
    "cwd",
}
_ABSOLUTE_PATH_SEQUENCE_KEYS = {"js_repl_node_module_dirs", "writable_roots"}


@dataclass(frozen=True)
class ManagedConfigFromFile:
    managed_config: Mapping[str, JsonValue]
    file: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "managed_config", dict(self.managed_config))
        object.__setattr__(self, "file", Path(self.file))


@dataclass(frozen=True)
class ManagedConfigFromMdm:
    managed_config: Mapping[str, JsonValue]
    raw_toml: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "managed_config", dict(self.managed_config))


@dataclass(frozen=True)
class LoadedConfigLayers:
    managed_config: ManagedConfigFromFile | None = None
    managed_config_from_mdm: ManagedConfigFromMdm | None = None


@dataclass(frozen=True)
class ProjectTrustDecision:
    trust_level: TrustLevel | None
    trust_key: str

    def is_trusted(self) -> bool:
        return self.trust_level == TrustLevel.TRUSTED


@dataclass(frozen=True)
class ProjectTrustContext:
    projects_trust: Mapping[str, TrustLevel]
    cwd: Path
    project_root: Path | None = None
    user_config_file: Path | None = None
    checkout_root: Path | None = None
    repo_root: Path | None = None

    def __post_init__(self) -> None:
        normalized: dict[str, TrustLevel] = {}
        for key, value in self.projects_trust.items():
            normalized[str(key)] = TrustLevel(value)
        object.__setattr__(self, "projects_trust", normalized)
        object.__setattr__(self, "cwd", Path(self.cwd))
        if self.project_root is not None:
            object.__setattr__(self, "project_root", Path(self.project_root))
        if self.user_config_file is not None:
            object.__setattr__(self, "user_config_file", Path(self.user_config_file))
        if self.checkout_root is not None:
            object.__setattr__(self, "checkout_root", Path(self.checkout_root))
        if self.repo_root is not None:
            object.__setattr__(self, "repo_root", Path(self.repo_root))

    def decision_for_dir(self, path: Path | str) -> ProjectTrustDecision:
        path = Path(path)
        for key in normalized_project_trust_keys(path):
            lookup = project_trust_for_lookup_key(self.projects_trust, key)
            if lookup is not None:
                trust_key, trust_level = lookup
                return ProjectTrustDecision(trust_level=trust_level, trust_key=trust_key)
        if self.project_root is not None:
            for key in normalized_project_trust_keys(self.project_root):
                lookup = project_trust_for_lookup_key(self.projects_trust, key)
                if lookup is not None:
                    trust_key, trust_level = lookup
                    return ProjectTrustDecision(trust_level=trust_level, trust_key=trust_key)
        if self.repo_root is not None:
            for key in normalized_project_trust_keys(self.repo_root):
                lookup = project_trust_for_lookup_key(self.projects_trust, key)
                if lookup is not None:
                    trust_key, trust_level = lookup
                    return ProjectTrustDecision(trust_level=trust_level, trust_key=trust_key)
        fallback = self.repo_root or self.project_root or path
        return ProjectTrustDecision(trust_level=None, trust_key=project_trust_key(fallback))

    def trust_for_dir(self, path: Path | str) -> ProjectTrustDecision:
        for candidate in (Path(path), *Path(path).parents):
            lookup = project_trust_for_path(self.projects_trust, candidate)
            if lookup is not None:
                trust_key, trust_level = lookup
                return ProjectTrustDecision(trust_level=trust_level, trust_key=trust_key)
        return self.decision_for_dir(path)

    def disabled_reason_for_decision(self, decision: ProjectTrustDecision) -> str | None:
        if decision.is_trusted():
            return None
        gated = "project-local config, hooks, and exec policies"
        user_config_file = str(self.user_config_file or "config.toml")
        if decision.trust_level == TrustLevel.UNTRUSTED:
            return (
                f"{decision.trust_key} is marked as untrusted in {user_config_file}. "
                f"To load {gated}, mark it trusted."
            )
        return f"To load {gated}, add {decision.trust_key} as a trusted project in {user_config_file}."

    def root_checkout_hooks_folder_for_dir(self, path: Path | str) -> Path | None:
        path = Path(path)
        if self.checkout_root is None or self.repo_root is None:
            return None
        try:
            relative = path.relative_to(self.checkout_root)
        except ValueError:
            return None
        if self.checkout_root == self.repo_root:
            return None
        return self.repo_root / relative / ".codex"


@dataclass(frozen=True)
class LoadedProjectLayers:
    layers: tuple[ConfigLayerEntry, ...]
    startup_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class LegacyManagedConfigToml:
    approval_policy: AskForApproval | None = None
    approvals_reviewer: ApprovalsReviewer | None = None
    sandbox_mode: SandboxMode | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "LegacyManagedConfigToml":
        value = _mapping_or_empty(value)
        approval_policy = value.get("approval_policy")
        approvals_reviewer = value.get("approvals_reviewer")
        sandbox_mode = value.get("sandbox_mode")
        return cls(
            approval_policy=AskForApproval.parse(str(approval_policy)) if approval_policy is not None else None,
            approvals_reviewer=ApprovalsReviewer.parse(str(approvals_reviewer))
            if approvals_reviewer is not None
            else None,
            sandbox_mode=SandboxMode.parse(str(sandbox_mode)) if sandbox_mode is not None else None,
        )

    def to_requirements_toml(self) -> ConfigRequirementsToml:
        reviewers: tuple[ApprovalsReviewer, ...] | None = None
        if self.approvals_reviewer is not None:
            values = [self.approvals_reviewer]
            if self.approvals_reviewer == ApprovalsReviewer.AUTO_REVIEW:
                values.append(ApprovalsReviewer.USER)
            reviewers = tuple(values)

        sandbox_modes: tuple[SandboxModeRequirement, ...] | None = None
        if self.sandbox_mode is not None:
            modes = [SandboxModeRequirement.READ_ONLY]
            mapped = sandbox_mode_requirement_from_sandbox_mode(self.sandbox_mode)
            if mapped != SandboxModeRequirement.READ_ONLY:
                modes.append(mapped)
            sandbox_modes = tuple(modes)

        return ConfigRequirementsToml(
            allowed_approval_policies=(self.approval_policy,) if self.approval_policy is not None else None,
            allowed_approvals_reviewers=reviewers,
            allowed_sandbox_modes=sandbox_modes,
        )


def is_unix_platform(platform: str | None = None) -> bool:
    platform = sys.platform if platform is None else platform
    return platform != "win32"


def managed_config_default_path(codex_home: Path | str, platform: str | None = None) -> PurePath:
    if is_unix_platform(platform):
        return CODEX_MANAGED_CONFIG_SYSTEM_PATH
    return Path(codex_home) / "managed_config.toml"


def system_config_toml_file(
    platform: str | None = None,
    program_data_dir: PurePath | str | None = None,
) -> PurePath:
    if is_unix_platform(platform):
        return SYSTEM_CONFIG_TOML_FILE_UNIX
    base = PureWindowsPath(program_data_dir) if program_data_dir is not None else DEFAULT_PROGRAM_DATA_DIR_WINDOWS
    return base / "OpenAI" / "Codex" / CONFIG_TOML_FILE


def system_requirements_toml_file(
    platform: str | None = None,
    program_data_dir: PurePath | str | None = None,
) -> PurePath:
    if is_unix_platform(platform):
        return SYSTEM_REQUIREMENTS_TOML_FILE_UNIX
    base = PureWindowsPath(program_data_dir) if program_data_dir is not None else DEFAULT_PROGRAM_DATA_DIR_WINDOWS
    return base / "OpenAI" / "Codex" / REQUIREMENTS_TOML_FILE


def system_config_toml_file_with_overrides(overrides: LoaderOverrides) -> PurePath:
    return overrides.system_config_path or system_config_toml_file()


def system_requirements_toml_file_with_overrides(overrides: LoaderOverrides) -> PurePath:
    return overrides.system_requirements_path or system_requirements_toml_file()


def insert_layer_by_precedence(layers: list[ConfigLayerEntry], layer: ConfigLayerEntry) -> None:
    precedence = source_precedence(layer.name)
    for index, current in enumerate(layers):
        if source_precedence(current.name) > precedence:
            layers.insert(index, layer)
            return
    layers.append(layer)


def source_precedence(source: ConfigLayerSource) -> int:
    return {
        "mdm": 0,
        "legacy_managed_config_toml_from_file": 5,
        "legacy_managed_config_toml_from_mdm": 5,
        "system": 1,
        "user": 2,
        "project": 3,
        "session_flags": 4,
    }.get(source.type, 5)


def sanitize_project_config(config: MutableMapping[str, JsonValue]) -> list[str]:
    ignored: list[str] = []
    for key in PROJECT_LOCAL_CONFIG_DENYLIST:
        if key in config:
            ignored.append(key)
            del config[key]
    return ignored


def project_ignored_config_keys_warning(dot_codex_folder: Path | str, ignored_keys: Sequence[str]) -> str:
    config_path = Path(dot_codex_folder) / CONFIG_TOML_FILE
    return (
        f"Ignored unsupported project-local config keys in {config_path}: "
        f"{', '.join(ignored_keys)}. If you want these settings to apply, "
        "manually set them in your user-level config.toml."
    )


def project_layer_entry(
    dot_codex_folder: Path | str,
    config: Mapping[str, JsonValue],
    disabled_reason: str | None = None,
    hooks_config_folder_override: Path | str | None = None,
) -> ConfigLayerEntry:
    entry = (
        ConfigLayerEntry.new_disabled(ConfigLayerSource.project(dot_codex_folder), config, disabled_reason)
        if disabled_reason is not None
        else ConfigLayerEntry.new(ConfigLayerSource.project(dot_codex_folder), config)
    )
    return entry.with_hooks_config_folder_override(hooks_config_folder_override)


def project_trust_context(
    merged_config: Mapping[str, JsonValue],
    cwd: Path | str,
    project_root_markers: Sequence[str],
    codex_home: Path | str,
    user_config_file: Path | str,
) -> ProjectTrustContext:
    cwd = Path(cwd)
    project_root = find_project_root(cwd, project_root_markers)
    projects_trust: dict[str, TrustLevel] = {}
    projects = merged_config.get("projects")
    if isinstance(projects, Mapping):
        for key, value in projects.items():
            if isinstance(value, ProjectConfig):
                project = value
            elif isinstance(value, Mapping):
                project = ProjectConfig.from_mapping(value)
            else:
                continue
            if project.trust_level is not None:
                projects_trust[str(key)] = project.trust_level
    return ProjectTrustContext(
        projects_trust=projects_trust,
        cwd=cwd,
        project_root=project_root,
        user_config_file=Path(user_config_file),
        checkout_root=find_git_checkout_root(cwd),
        repo_root=find_git_checkout_root(cwd),
    )


def find_project_root(cwd: Path | str, project_root_markers: Sequence[str]) -> Path:
    cwd = Path(cwd)
    if not project_root_markers:
        return cwd
    start = cwd if cwd.is_dir() else cwd.parent
    for ancestor in (start, *start.parents):
        for marker in project_root_markers:
            if (ancestor / marker).exists():
                return ancestor
    return cwd


def find_git_checkout_root(cwd: Path | str) -> Path | None:
    cwd = Path(cwd)
    start = cwd if cwd.is_dir() else cwd.parent
    for ancestor in (start, *start.parents):
        if (ancestor / ".git").exists():
            return ancestor
    return None


def load_project_layers(
    cwd: Path | str,
    project_root: Path | str,
    trust_context: ProjectTrustContext,
    codex_home: Path | str,
    *,
    strict_config: bool = False,
) -> LoadedProjectLayers:
    cwd = Path(cwd)
    project_root = Path(project_root)
    codex_home = Path(codex_home)
    codex_home_normalized = codex_home.resolve(strict=False)
    dirs: list[Path] = []
    for ancestor in (cwd, *cwd.parents):
        dirs.append(ancestor)
        if ancestor == project_root:
            break
    dirs.reverse()

    layers: list[ConfigLayerEntry] = []
    startup_warnings: list[str] = []
    for directory in dirs:
        dot_codex_folder = directory / ".codex"
        if not dot_codex_folder.is_dir():
            continue
        if dot_codex_folder == codex_home or dot_codex_folder.resolve(strict=False) == codex_home_normalized:
            continue

        decision = trust_context.decision_for_dir(directory)
        disabled_reason = trust_context.disabled_reason_for_decision(decision)
        hooks_override = trust_context.root_checkout_hooks_folder_for_dir(directory)
        config_file = dot_codex_folder / CONFIG_TOML_FILE
        try:
            contents = config_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            config = merge_root_checkout_project_hooks({}, hooks_override, decision.is_trusted())
            layers.append(project_layer_entry(dot_codex_folder, config, disabled_reason, hooks_override))
            continue

        try:
            parsed = _toml.loads(contents)
        except Exception:
            if decision.is_trusted():
                raise
            layers.append(project_layer_entry(dot_codex_folder, {}, disabled_reason, hooks_override))
            continue
        if not isinstance(parsed, Mapping):
            parsed = {}
        if disabled_reason is None and strict_config:
            ConfigToml.from_mapping(parsed)

        config = dict(parsed)
        ignored = sanitize_project_config(config)
        config = resolve_relative_paths_in_config_toml(config, dot_codex_folder)
        config = merge_root_checkout_project_hooks(config, hooks_override, decision.is_trusted())
        if disabled_reason is None and ignored:
            startup_warnings.append(project_ignored_config_keys_warning(dot_codex_folder, ignored))
        layers.append(project_layer_entry(dot_codex_folder, config, disabled_reason, hooks_override))
    return LoadedProjectLayers(tuple(layers), tuple(startup_warnings))


def merge_root_checkout_project_hooks(
    config: Mapping[str, JsonValue],
    hooks_config_folder_override: Path | str | None,
    is_trusted: bool,
) -> dict[str, JsonValue]:
    merged = dict(config)
    if hooks_config_folder_override is None:
        return merged
    hooks_config_file = Path(hooks_config_folder_override) / CONFIG_TOML_FILE
    try:
        contents = hooks_config_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        root_config: dict[str, JsonValue] = {}
    else:
        try:
            parsed = _toml.loads(contents)
        except Exception:
            if is_trusted:
                raise
            parsed = {}
        root_config = (
            resolve_relative_paths_in_config_toml(parsed, Path(hooks_config_folder_override))
            if isinstance(parsed, Mapping)
            else {}
        )
    merged.pop("hooks", None)
    if "hooks" in root_config:
        merged["hooks"] = root_config["hooks"]
    return merged


def project_trust_key(path: Path | str, platform: str | None = None) -> str:
    return normalized_project_trust_keys(path, platform=platform)[0]


def normalized_project_trust_keys(path: Path | str, platform: str | None = None) -> list[str]:
    path = Path(path)
    candidates = [path.resolve(strict=False), path.absolute()]
    keys: list[str] = []
    for candidate in candidates:
        key = str(candidate)
        if not is_unix_platform(platform):
            key = key.lower()
        if key not in keys:
            keys.append(key)
    return keys


def project_trust_for_path(
    projects_trust: Mapping[str, TrustLevel],
    path: Path | str,
    platform: str | None = None,
) -> tuple[str, TrustLevel] | None:
    for key in normalized_project_trust_keys(path, platform=platform):
        direct = projects_trust.get(key)
        if direct is not None:
            return key, TrustLevel(direct)
    return project_trust_for_lookup_key(projects_trust, project_trust_key(path, platform=platform), platform=platform)


def project_trust_for_lookup_key(
    projects_trust: Mapping[str, TrustLevel],
    lookup_key: str,
    platform: str | None = None,
) -> tuple[str, TrustLevel] | None:
    if lookup_key in projects_trust:
        return lookup_key, TrustLevel(projects_trust[lookup_key])
    normalized_lookup = lookup_key.lower() if not is_unix_platform(platform) else lookup_key
    for key in sorted(projects_trust):
        normalized_key = key.lower() if not is_unix_platform(platform) else key
        if normalized_key == normalized_lookup:
            return key, TrustLevel(projects_trust[key])
    return None


def resolve_relative_paths_in_config_toml(config: Mapping[str, JsonValue], base_dir: Path | str) -> dict[str, JsonValue]:
    resolved = _resolve_relative_paths_in_value(dict(config), Path(base_dir), current_key=None)
    assert isinstance(resolved, dict)
    return resolved


def copy_shape_from_original(original: JsonValue, resolved: JsonValue) -> JsonValue:
    if isinstance(original, Mapping) and isinstance(resolved, Mapping):
        copied: dict[str, JsonValue] = {}
        for key, original_value in original.items():
            copied[key] = copy_shape_from_original(original_value, resolved.get(key, original_value))
        for key, resolved_value in resolved.items():
            copied.setdefault(key, resolved_value)
        return copied
    if isinstance(original, list) and isinstance(resolved, list):
        return [
            copy_shape_from_original(original_item, resolved_item)
            for original_item, resolved_item in zip(original, resolved, strict=False)
        ]
    return resolved


def read_config_from_path(path: Path | str, *, strict_config: bool = False) -> dict[str, JsonValue] | None:
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    parsed = _toml.loads(raw)
    if not isinstance(parsed, Mapping):
        raise TypeError(f"{path} must contain a TOML table")
    if strict_config:
        ConfigToml.from_mapping(parsed)
    return dict(parsed)


def load_config_toml_for_required_layer(
    toml_file: Path | str,
    create_entry: Any,
    *,
    strict_config: bool = False,
) -> ConfigLayerEntry:
    toml_file = Path(toml_file)
    if toml_file.parent == Path(""):
        raise ValueError(f"{toml_file} has no parent directory")
    parsed = read_config_from_path(toml_file, strict_config=strict_config)
    if parsed is None:
        parsed = {}
    resolved = resolve_relative_paths_in_config_toml(parsed, toml_file.parent)
    return create_entry(resolved)


def load_user_config_layer(
    user_file: Path | str,
    profile: str | None = None,
    *,
    ignore_user_config: bool = False,
    strict_config: bool = False,
) -> ConfigLayerEntry:
    user_file = Path(user_file)
    if ignore_user_config:
        return ConfigLayerEntry.new(ConfigLayerSource.user(user_file, profile), {})
    return load_config_toml_for_required_layer(
        user_file,
        lambda config: ConfigLayerEntry.new(ConfigLayerSource.user(user_file, profile), config),
        strict_config=strict_config,
    )


def load_requirements_toml(
    target: ConfigRequirementsWithSources,
    requirements_toml_file: Path | str,
    *,
    hostname: str | None = None,
) -> None:
    requirements_toml_file = Path(requirements_toml_file)
    try:
        contents = requirements_toml_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    parsed = ConfigRequirementsToml.from_toml(contents)
    merge_requirements_with_remote_sandbox_config(
        target,
        RequirementSource.system_requirements_toml(str(requirements_toml_file)),
        parsed,
        hostname=hostname,
    )


def load_requirements_from_legacy_scheme(
    target: ConfigRequirementsWithSources,
    loaded_config_layers: LoadedConfigLayers,
    *,
    hostname: str | None = None,
) -> None:
    # Rust merges MDM first because earlier requirement sources win.
    if loaded_config_layers.managed_config_from_mdm is not None:
        merge_requirements_with_remote_sandbox_config(
            target,
            RequirementSource.legacy_managed_config_toml_from_mdm(),
            legacy_managed_config_to_requirements(loaded_config_layers.managed_config_from_mdm.managed_config),
            hostname=hostname,
        )
    if loaded_config_layers.managed_config is not None:
        merge_requirements_with_remote_sandbox_config(
            target,
            RequirementSource.legacy_managed_config_toml_from_file(str(loaded_config_layers.managed_config.file)),
            legacy_managed_config_to_requirements(loaded_config_layers.managed_config.managed_config),
            hostname=hostname,
        )


def validate_cli_overrides_strictly(cli_overrides_layer: Mapping[str, JsonValue]) -> None:
    try:
        ConfigToml.from_mapping(cli_overrides_layer)
    except Exception as exc:
        path = _first_mapping_path(cli_overrides_layer) or "<unknown>"
        raise ValueError(f"unknown configuration field `{path}` in -c/--config override") from exc
    feature_path = unknown_feature_toml_value_field(cli_overrides_layer)
    if feature_path is not None:
        raise ValueError(f"unknown configuration field `{feature_path}` in -c/--config override")


def build_cli_overrides_layer_for_loader(
    cli_overrides: Mapping[str, JsonValue] | Sequence[str] | Sequence[ConfigOverride] | None,
    cwd: Path | str,
    *,
    strict_config: bool = False,
) -> dict[str, JsonValue] | None:
    if cli_overrides is None:
        return None
    if isinstance(cli_overrides, Mapping):
        layer = dict(cli_overrides)
    elif all(isinstance(item, str) for item in cli_overrides):
        layer = CliConfigOverrides(list(cli_overrides)).build_layer()
    else:
        layer = build_cli_overrides_layer(cli_overrides)  # type: ignore[arg-type]
    if not layer:
        return None
    if strict_config:
        validate_cli_overrides_strictly(layer)
    return resolve_relative_paths_in_config_toml(layer, cwd)


def load_config_layers_state(
    codex_home: Path | str,
    *,
    cwd: Path | str | None = None,
    cli_overrides: Mapping[str, JsonValue] | Sequence[str] | Sequence[ConfigOverride] | None = None,
    config_load_options: ConfigLoadOptions | None = None,
    loaded_config_layers: LoadedConfigLayers | None = None,
    thread_config_layers: Sequence[ConfigLayerEntry] = (),
    hostname: str | None = None,
) -> ConfigLayerStack:
    codex_home = Path(codex_home)
    options = config_load_options or ConfigLoadOptions()
    overrides = options.loader_overrides
    loaded_config_layers = loaded_config_layers or load_config_layers_internal(
        codex_home,
        overrides=overrides,
        strict_config=options.strict_config,
    )
    requirements = ConfigRequirementsWithSources()

    if not overrides.ignore_managed_requirements:
        load_requirements_toml(
            requirements,
            system_requirements_toml_file_with_overrides(overrides),
            hostname=hostname,
        )
        load_requirements_from_legacy_scheme(requirements, loaded_config_layers, hostname=hostname)

    layers: list[ConfigLayerEntry] = []
    system_file = Path(system_config_toml_file_with_overrides(overrides))
    layers.append(
        load_config_toml_for_required_layer(
            system_file,
            lambda config: ConfigLayerEntry.new(ConfigLayerSource.system(system_file), config),
            strict_config=options.strict_config,
        )
    )

    user_file = overrides.user_config_file(codex_home)
    layers.append(
        load_user_config_layer(
            user_file,
            overrides.user_config_profile,
            ignore_user_config=overrides.ignore_user_config,
            strict_config=options.strict_config,
        )
    )

    cli_overrides_layer = build_cli_overrides_layer_for_loader(
        cli_overrides,
        cwd or codex_home,
        strict_config=options.strict_config,
    )

    startup_warnings: tuple[str, ...] = ()
    if cwd is not None:
        merged_so_far: dict[str, JsonValue] = {}
        for layer in layers:
            merge_toml_values(merged_so_far, layer.config)
        if cli_overrides_layer is not None:
            merge_toml_values(merged_so_far, cli_overrides_layer)
        markers = project_root_markers_from_config(merged_so_far) or default_project_root_markers()
        trust_context = project_trust_context(merged_so_far, cwd, markers, codex_home, user_file)
        project_layers = load_project_layers(
            cwd,
            trust_context.project_root or Path(cwd),
            trust_context,
            codex_home,
            strict_config=options.strict_config,
        )
        layers.extend(project_layers.layers)
        startup_warnings = project_layers.startup_warnings

    if cli_overrides_layer is not None:
        layers.append(ConfigLayerEntry.new(ConfigLayerSource.session_flags(), cli_overrides_layer))

    for thread_layer in thread_config_layers:
        insert_layer_by_precedence(layers, thread_layer)

    append_legacy_managed_config_layers(layers, loaded_config_layers, codex_home)

    stack = ConfigLayerStack.new(
        layers,
        ConfigRequirements.from_sources(requirements),
        requirements.into_toml(),
    ).with_user_and_project_exec_policy_rules_ignored(
        overrides.ignore_user_and_project_exec_policy_rules
    )
    return stack.with_startup_warnings(startup_warnings) if startup_warnings else stack


def append_legacy_managed_config_layers(
    layers: list[ConfigLayerEntry],
    loaded_config_layers: LoadedConfigLayers,
    codex_home: Path | str,
) -> None:
    if loaded_config_layers.managed_config is not None:
        managed = loaded_config_layers.managed_config
        parent = managed.file.parent
        if not str(parent):
            raise ValueError(f"Managed config file {managed.file} has no parent directory")
        resolved = resolve_relative_paths_in_config_toml(managed.managed_config, parent)
        layers.append(
            ConfigLayerEntry.new(
                ConfigLayerSource.legacy_managed_config_toml_from_file(managed.file),
                resolved,
            )
        )
    if loaded_config_layers.managed_config_from_mdm is not None:
        managed_mdm = loaded_config_layers.managed_config_from_mdm
        resolved = resolve_relative_paths_in_config_toml(managed_mdm.managed_config, codex_home)
        layers.append(
            ConfigLayerEntry.new_with_raw_toml(
                ConfigLayerSource("legacy_managed_config_toml_from_mdm"),
                resolved,
                managed_mdm.raw_toml,
            )
        )


def read_managed_config_from_path(path: Path | str, *, strict_config: bool = False) -> dict[str, JsonValue] | None:
    return read_config_from_path(path, strict_config=strict_config)


def managed_config_from_mdm_raw_toml(
    raw_toml: str | None,
    *,
    strict_config: bool = False,
) -> ManagedConfigFromMdm | None:
    if raw_toml is None or not raw_toml.strip():
        return None
    parsed = _toml.loads(raw_toml)
    if not isinstance(parsed, Mapping):
        raise TypeError("managed preferences config must contain a TOML table")
    if strict_config:
        ConfigToml.from_mapping(parsed)
    return ManagedConfigFromMdm(parsed, raw_toml)


def managed_config_from_mdm_base64(
    encoded: str | None,
    *,
    strict_config: bool = False,
) -> ManagedConfigFromMdm | None:
    if encoded is None or not encoded.strip():
        return None
    try:
        raw_toml = base64.b64decode(encoded.encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("managed preferences config must be base64-encoded UTF-8 TOML") from exc
    return managed_config_from_mdm_raw_toml(raw_toml, strict_config=strict_config)


def managed_preferences_requirements_source() -> RequirementSource:
    return RequirementSource.mdm_managed_preferences(
        MANAGED_PREFERENCES_APPLICATION_ID,
        MANAGED_PREFERENCES_REQUIREMENTS_KEY,
    )


def managed_requirements_from_mdm_base64(encoded: str | None) -> ConfigRequirementsToml | None:
    if encoded is None or not encoded.strip():
        return None
    try:
        raw_toml = base64.b64decode(encoded.strip().encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("managed requirements must be base64-encoded UTF-8 TOML") from exc
    return ConfigRequirementsToml.from_toml(raw_toml)


def load_managed_admin_requirements_toml(
    target: ConfigRequirementsWithSources,
    override_base64: str | None = None,
    *,
    hostname: str | None = None,
) -> None:
    requirements = managed_requirements_from_mdm_base64(override_base64)
    if requirements is None:
        return
    merge_requirements_with_remote_sandbox_config(
        target,
        managed_preferences_requirements_source(),
        requirements,
        hostname=hostname,
    )


def load_config_layers_internal(
    codex_home: Path | str,
    *,
    overrides: LoaderOverrides | None = None,
    strict_config: bool = False,
    managed_config_mdm_raw_toml: str | None = None,
    managed_config_mdm_base64: str | None = None,
) -> LoadedConfigLayers:
    codex_home = Path(codex_home)
    overrides = overrides or LoaderOverrides()
    managed_path = overrides.managed_config_path or managed_config_default_path(codex_home)
    managed_config = read_managed_config_from_path(managed_path, strict_config=strict_config)
    if managed_config_mdm_raw_toml is not None and managed_config_mdm_base64 is not None:
        raise ValueError("managed config MDM raw TOML and base64 inputs are mutually exclusive")
    mdm = (
        managed_config_from_mdm_raw_toml(managed_config_mdm_raw_toml, strict_config=strict_config)
        if managed_config_mdm_raw_toml is not None
        else managed_config_from_mdm_base64(managed_config_mdm_base64, strict_config=strict_config)
    )
    return LoadedConfigLayers(
        managed_config=ManagedConfigFromFile(managed_config, Path(managed_path)) if managed_config is not None else None,
        managed_config_from_mdm=mdm,
    )


def legacy_managed_config_to_requirements(
    config: LegacyManagedConfigToml | Mapping[str, JsonValue] | None,
) -> ConfigRequirementsToml:
    legacy = config if isinstance(config, LegacyManagedConfigToml) else LegacyManagedConfigToml.from_mapping(config)
    return legacy.to_requirements_toml()


def merge_requirements_with_remote_sandbox_config(
    target: ConfigRequirementsWithSources,
    source: RequirementSource,
    requirements: ConfigRequirementsToml,
    hostname: str | None = None,
) -> None:
    requirements.apply_remote_sandbox_config(hostname)
    target.merge_unset_fields(source, requirements)


def sandbox_mode_requirement_from_sandbox_mode(mode: SandboxMode) -> SandboxModeRequirement:
    mode = SandboxMode(mode)
    return {
        SandboxMode.READ_ONLY: SandboxModeRequirement.READ_ONLY,
        SandboxMode.WORKSPACE_WRITE: SandboxModeRequirement.WORKSPACE_WRITE,
        SandboxMode.DANGER_FULL_ACCESS: SandboxModeRequirement.DANGER_FULL_ACCESS,
    }[mode]


def _resolve_relative_paths_in_value(value: JsonValue, base_dir: Path, current_key: str | None) -> JsonValue:
    if isinstance(value, Mapping):
        return {
            str(key): _resolve_relative_paths_in_value(item, base_dir, current_key=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        if current_key in _ABSOLUTE_PATH_SEQUENCE_KEYS:
            return [_absolute_path(item, base_dir) if isinstance(item, str) else item for item in value]
        return [_resolve_relative_paths_in_value(item, base_dir, current_key=current_key) for item in value]
    if isinstance(value, str) and current_key in _ABSOLUTE_PATH_KEYS:
        return _absolute_path(value, base_dir)
    return value


def _absolute_path(value: str, base_dir: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve(strict=False))


def _mapping_or_empty(value: Mapping[str, JsonValue] | None) -> Mapping[str, JsonValue]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("expected a TOML table")
    return value


def _first_mapping_path(value: Mapping[str, JsonValue], prefix: str = "") -> str | None:
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, Mapping):
            nested = _first_mapping_path(item, path)
            if nested is not None:
                return nested
        return path
    return None


__all__ = [
    "CODEX_MANAGED_CONFIG_SYSTEM_PATH",
    "CONFIG_TOML_FILE",
    "DEFAULT_PROGRAM_DATA_DIR_WINDOWS",
    "MANAGED_PREFERENCES_APPLICATION_ID",
    "MANAGED_PREFERENCES_CONFIG_KEY",
    "MANAGED_PREFERENCES_REQUIREMENTS_KEY",
    "LoadedConfigLayers",
    "LoadedProjectLayers",
    "ManagedConfigFromFile",
    "ManagedConfigFromMdm",
    "LegacyManagedConfigToml",
    "PROJECT_LOCAL_CONFIG_DENYLIST",
    "ProjectTrustContext",
    "ProjectTrustDecision",
    "REQUIREMENTS_TOML_FILE",
    "SYSTEM_CONFIG_TOML_FILE_UNIX",
    "SYSTEM_REQUIREMENTS_TOML_FILE_UNIX",
    "copy_shape_from_original",
    "append_legacy_managed_config_layers",
    "build_cli_overrides_layer_for_loader",
    "find_git_checkout_root",
    "find_project_root",
    "insert_layer_by_precedence",
    "legacy_managed_config_to_requirements",
    "load_config_layers_internal",
    "load_config_toml_for_required_layer",
    "load_config_layers_state",
    "load_managed_admin_requirements_toml",
    "load_requirements_from_legacy_scheme",
    "load_requirements_toml",
    "load_project_layers",
    "load_user_config_layer",
    "merge_root_checkout_project_hooks",
    "managed_config_default_path",
    "managed_config_from_mdm_base64",
    "managed_config_from_mdm_raw_toml",
    "managed_preferences_requirements_source",
    "managed_requirements_from_mdm_base64",
    "merge_requirements_with_remote_sandbox_config",
    "normalized_project_trust_keys",
    "project_ignored_config_keys_warning",
    "project_layer_entry",
    "project_trust_context",
    "project_trust_for_lookup_key",
    "project_trust_for_path",
    "project_trust_key",
    "read_managed_config_from_path",
    "read_config_from_path",
    "resolve_relative_paths_in_config_toml",
    "sanitize_project_config",
    "sandbox_mode_requirement_from_sandbox_mode",
    "source_precedence",
    "system_config_toml_file",
    "system_config_toml_file_with_overrides",
    "system_requirements_toml_file",
    "system_requirements_toml_file_with_overrides",
    "validate_cli_overrides_strictly",
]
