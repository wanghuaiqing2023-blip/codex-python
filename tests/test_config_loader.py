from __future__ import annotations

import base64
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from pycodex.config.config_requirements import (
    ConfigRequirementsToml,
    ConfigRequirementsWithSources,
    SandboxModeRequirement,
)
from pycodex.config.constraint import RequirementSource
from pycodex.config.loader import (
    LegacyManagedConfigToml,
    LoadedConfigLayers,
    ManagedConfigFromFile,
    ManagedConfigFromMdm,
    append_legacy_managed_config_layers,
    build_cli_overrides_layer_for_loader,
    find_project_root,
    insert_layer_by_precedence,
    legacy_managed_config_to_requirements,
    load_config_layers_internal,
    load_config_layers_state,
    load_config_toml_for_required_layer,
    load_requirements_from_legacy_scheme,
    load_requirements_toml,
    load_project_layers,
    load_user_config_layer,
    managed_config_default_path,
    managed_config_from_mdm_base64,
    managed_config_from_mdm_raw_toml,
    merge_root_checkout_project_hooks,
    merge_requirements_with_remote_sandbox_config,
    normalized_project_trust_keys,
    project_ignored_config_keys_warning,
    project_trust_context,
    project_trust_for_lookup_key,
    read_managed_config_from_path,
    read_config_from_path,
    resolve_relative_paths_in_config_toml,
    sanitize_project_config,
    system_config_toml_file,
    system_requirements_toml_file,
    validate_cli_overrides_strictly,
)
from pycodex.config.state import ConfigLayerEntry, ConfigLoadOptions, LoaderOverrides
from pycodex.network_proxy import ConfigLayerSource
from pycodex.protocol.config_types import ApprovalsReviewer, AskForApproval, TrustLevel


def test_loader_well_known_paths_match_platform_contract() -> None:
    # Rust: codex-config::loader managed/system path helpers.
    assert managed_config_default_path(Path("/home/me/.codex"), platform="linux") == PurePosixPath(
        "/etc/codex/managed_config.toml"
    )
    assert managed_config_default_path(PureWindowsPath("C:/Users/me/.codex"), platform="win32") == PureWindowsPath(
        "C:/Users/me/.codex/managed_config.toml"
    )

    assert system_config_toml_file(platform="linux") == PurePosixPath("/etc/codex/config.toml")
    assert system_requirements_toml_file(platform="linux") == PurePosixPath("/etc/codex/requirements.toml")
    assert system_config_toml_file(platform="win32", program_data_dir=PureWindowsPath("D:/ProgramData")) == PureWindowsPath(
        "D:/ProgramData/OpenAI/Codex/config.toml"
    )
    assert system_requirements_toml_file(
        platform="win32", program_data_dir=PureWindowsPath("D:/ProgramData")
    ) == PureWindowsPath("D:/ProgramData/OpenAI/Codex/requirements.toml")


def test_insert_layer_by_precedence_matches_rust_ordering() -> None:
    # Rust: insert_layer_by_precedence keeps lower precedence first.
    layers = [
        ConfigLayerEntry.new(ConfigLayerSource.user(Path("/tmp/config.toml")), {"model": "user"}),
        ConfigLayerEntry.new(ConfigLayerSource.session_flags(), {"model": "session"}),
    ]

    insert_layer_by_precedence(layers, ConfigLayerEntry.new(ConfigLayerSource.system(Path("/etc/codex/config.toml")), {}))
    insert_layer_by_precedence(layers, ConfigLayerEntry.new(ConfigLayerSource.project(Path("/work/.codex")), {}))

    assert [layer.name.type for layer in layers] == ["system", "user", "project", "session_flags"]


def test_sanitize_project_config_removes_denylist_and_formats_warning(tmp_path: Path) -> None:
    # Rust: sanitize_project_config removes unsupported project-local keys in denylist order.
    config = {
        "model_provider": "openai",
        "notify": ["say done"],
        "model": "gpt-5",
        "otel": {"enabled": True},
        "profiles": {"default": {}},
    }

    ignored = sanitize_project_config(config)

    assert ignored == ["model_provider", "notify", "profiles", "otel"]
    assert config == {"model": "gpt-5"}
    assert project_ignored_config_keys_warning(tmp_path / ".codex", ignored) == (
        f"Ignored unsupported project-local config keys in {tmp_path / '.codex' / 'config.toml'}: "
        "model_provider, notify, profiles, otel. If you want these settings to apply, "
        "manually set them in your user-level config.toml."
    )


def test_legacy_managed_config_backfills_read_only_sandbox_mode() -> None:
    # Rust: legacy_managed_config_backfill_includes_read_only_sandbox_mode.
    requirements = legacy_managed_config_to_requirements({"sandbox_mode": "workspace-write"})

    assert requirements.allowed_sandbox_modes == (
        SandboxModeRequirement.READ_ONLY,
        SandboxModeRequirement.WORKSPACE_WRITE,
    )


def test_legacy_managed_config_backfills_user_when_auto_review_is_required() -> None:
    # Rust: legacy_managed_config_backfill_allows_user_when_guardian_is_required.
    requirements = legacy_managed_config_to_requirements({"approvals_reviewer": "guardian_subagent"})

    assert requirements.allowed_approvals_reviewers == (
        ApprovalsReviewer.AUTO_REVIEW,
        ApprovalsReviewer.USER,
    )


def test_legacy_managed_config_preserves_user_only_reviewer_and_policy() -> None:
    # Rust: legacy_managed_config_backfill_preserves_user_only_approvals_reviewer.
    requirements = LegacyManagedConfigToml.from_mapping(
        {"approval_policy": "never", "approvals_reviewer": "user"}
    ).to_requirements_toml()

    assert requirements.allowed_approval_policies == (AskForApproval.NEVER,)
    assert requirements.allowed_approvals_reviewers == (ApprovalsReviewer.USER,)


def test_resolve_relative_paths_preserves_unknown_fields(tmp_path: Path) -> None:
    # Rust: ensure_resolve_relative_paths_in_config_toml_preserves_all_fields.
    config = {
        "model_instructions_file": "./some_file.md",
        "model": "gpt-1000",
        "foo": "xyzzy",
        "profiles": {
            "work": {
                "experimental_compact_prompt_file": "compact.md",
                "bar": "kept",
            }
        },
    }

    resolved = resolve_relative_paths_in_config_toml(config, tmp_path)

    assert resolved["model_instructions_file"] == str((tmp_path / "some_file.md").resolve(strict=False))
    assert resolved["foo"] == "xyzzy"
    assert resolved["profiles"]["work"]["experimental_compact_prompt_file"] == str(
        (tmp_path / "compact.md").resolve(strict=False)
    )
    assert resolved["profiles"]["work"]["bar"] == "kept"


def test_read_config_from_path_and_required_layer_resolution(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('model = "gpt-5"\nmodel_instructions_file = "instructions.md"\n', encoding="utf-8")

    assert read_config_from_path(tmp_path / "missing.toml") is None
    assert read_config_from_path(config_path) == {
        "model": "gpt-5",
        "model_instructions_file": "instructions.md",
    }

    entry = load_config_toml_for_required_layer(
        config_path,
        lambda config: ConfigLayerEntry.new(ConfigLayerSource.system(config_path), config),
    )
    assert entry.config["model_instructions_file"] == str((tmp_path / "instructions.md").resolve(strict=False))

    bad_path = tmp_path / "bad.toml"
    bad_path.write_text("unknown_loader_field = true\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_config_from_path(bad_path, strict_config=True)


def test_load_user_config_layer_missing_and_ignored_are_empty_user_layers(tmp_path: Path) -> None:
    # Rust: load_user_config_layer returns an empty user layer for missing files or ignored user config.
    missing = tmp_path / "missing.toml"

    missing_layer = load_user_config_layer(missing, profile="work")
    ignored_layer = load_user_config_layer(missing, profile="work", ignore_user_config=True)

    assert missing_layer.name == ConfigLayerSource.user(missing, "work")
    assert missing_layer.config == {}
    assert ignored_layer.name == ConfigLayerSource.user(missing, "work")
    assert ignored_layer.config == {}


def test_load_requirements_toml_merges_unset_fields_without_overwriting(tmp_path: Path) -> None:
    # Rust: load_requirements_toml fills only unset requirement fields and ignores a missing file.
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        RequirementSource.cloud_requirements(),
        ConfigRequirementsToml(allowed_approval_policies=(AskForApproval.NEVER,)),
    )
    requirements_path = tmp_path / "requirements.toml"
    requirements_path.write_text(
        'allowed_approval_policies = ["on-request"]\nallowed_sandbox_modes = ["workspace-write"]\n',
        encoding="utf-8",
    )

    load_requirements_toml(target, requirements_path)
    load_requirements_toml(target, tmp_path / "missing.toml")

    assert target.allowed_approval_policies is not None
    assert target.allowed_approval_policies.value == (AskForApproval.NEVER,)
    assert target.allowed_approval_policies.source == RequirementSource.cloud_requirements()
    assert target.allowed_sandbox_modes is not None
    assert target.allowed_sandbox_modes.value == (SandboxModeRequirement.WORKSPACE_WRITE,)
    assert target.allowed_sandbox_modes.source == RequirementSource.system_requirements_toml(str(requirements_path))


def test_load_requirements_from_legacy_scheme_mdm_precedes_file() -> None:
    # Rust: load_requirements_from_legacy_scheme lists MDM before file because earlier sources win.
    target = ConfigRequirementsWithSources()
    loaded = LoadedConfigLayers(
        managed_config=ManagedConfigFromFile({"sandbox_mode": "workspace-write"}, Path("/etc/codex/managed_config.toml")),
        managed_config_from_mdm=ManagedConfigFromMdm({"sandbox_mode": "danger-full-access"}, "sandbox_mode = \"danger-full-access\""),
    )

    load_requirements_from_legacy_scheme(target, loaded)

    assert target.allowed_sandbox_modes is not None
    assert target.allowed_sandbox_modes.value == (
        SandboxModeRequirement.READ_ONLY,
        SandboxModeRequirement.DANGER_FULL_ACCESS,
    )
    assert target.allowed_sandbox_modes.source == RequirementSource.legacy_managed_config_toml_from_mdm()


def test_append_legacy_managed_config_layers_resolves_paths_and_preserves_raw_toml(tmp_path: Path) -> None:
    # Rust: legacy managed config layers are appended after normal layers and path-resolved by source.
    managed_file = tmp_path / "managed" / "managed_config.toml"
    managed_file.parent.mkdir()
    layers: list[ConfigLayerEntry] = []
    loaded = LoadedConfigLayers(
        managed_config=ManagedConfigFromFile(
            {"model_instructions_file": "managed.md"},
            managed_file,
        ),
        managed_config_from_mdm=ManagedConfigFromMdm(
            {"model_instructions_file": "mdm.md"},
            'model_instructions_file = "mdm.md"',
        ),
    )

    append_legacy_managed_config_layers(layers, loaded, tmp_path / "home")

    assert [layer.name.type for layer in layers] == [
        "legacy_managed_config_toml_from_file",
        "legacy_managed_config_toml_from_mdm",
    ]
    assert layers[0].config["model_instructions_file"] == str(
        (managed_file.parent / "managed.md").resolve(strict=False)
    )
    assert layers[1].config["model_instructions_file"] == str((tmp_path / "home" / "mdm.md").resolve(strict=False))
    assert layers[1].raw_toml_text() == 'model_instructions_file = "mdm.md"'


def test_managed_layer_io_reads_file_and_validates_strict_config(tmp_path: Path) -> None:
    # Rust: loader::layer_io read_config_from_path returns None for missing and strict-validates ConfigToml.
    managed = tmp_path / "managed_config.toml"
    managed.write_text('model = "managed"\nmodel_instructions_file = "managed.md"\n', encoding="utf-8")

    assert read_managed_config_from_path(tmp_path / "missing.toml") is None
    assert read_managed_config_from_path(managed, strict_config=True) == {
        "model": "managed",
        "model_instructions_file": "managed.md",
    }
    bad = tmp_path / "bad_managed_config.toml"
    bad.write_text("unknown_loader_field = true\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_managed_config_from_path(bad, strict_config=True)


def test_managed_layer_io_parses_mdm_raw_and_base64_toml() -> None:
    # Rust macOS layer_io keeps both parsed config and the raw managed TOML.
    raw = 'model = "mdm"\n'
    encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")

    from_raw = managed_config_from_mdm_raw_toml(raw, strict_config=True)
    from_base64 = managed_config_from_mdm_base64(encoded, strict_config=True)

    assert from_raw is not None
    assert from_raw.managed_config == {"model": "mdm"}
    assert from_raw.raw_toml == raw
    assert from_base64 is not None
    assert from_base64.managed_config == {"model": "mdm"}
    assert managed_config_from_mdm_raw_toml("") is None
    with pytest.raises(ValueError):
        managed_config_from_mdm_base64("not base64")


def test_load_config_layers_internal_uses_override_path_and_mdm_base64(tmp_path: Path) -> None:
    # Rust: layer_io load_config_layers_internal reads the managed config file and optional MDM layer.
    codex_home = tmp_path / "home"
    codex_home.mkdir()
    managed = tmp_path / "managed_config.toml"
    managed.write_text('model = "file"\n', encoding="utf-8")
    raw_mdm = 'model = "mdm"\n'

    loaded = load_config_layers_internal(
        codex_home,
        overrides=LoaderOverrides(managed_config_path=managed),
        strict_config=True,
        managed_config_mdm_base64=base64.b64encode(raw_mdm.encode("utf-8")).decode("ascii"),
    )

    assert loaded.managed_config is not None
    assert loaded.managed_config.file == managed
    assert loaded.managed_config.managed_config == {"model": "file"}
    assert loaded.managed_config_from_mdm is not None
    assert loaded.managed_config_from_mdm.managed_config == {"model": "mdm"}
    assert load_config_layers_internal(codex_home).managed_config is None


def test_project_trust_lookup_normalizes_windows_case(tmp_path: Path) -> None:
    key = str(tmp_path.resolve(strict=False)).upper()
    projects = {key: TrustLevel.TRUSTED}

    assert normalized_project_trust_keys(tmp_path, platform="win32")[0] == str(tmp_path.resolve(strict=False)).lower()
    assert project_trust_for_lookup_key(projects, key.lower(), platform="win32") == (key, TrustLevel.TRUSTED)


def test_find_project_root_uses_first_marker_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    (root / ".codex-root").write_text("", encoding="utf-8")

    assert find_project_root(nested, [".codex-root"]) == root
    assert find_project_root(nested, []) == nested
    assert find_project_root(nested, [".missing"]) == nested


def test_load_project_layers_trusted_sanitizes_and_warns_in_root_to_cwd_order(tmp_path: Path) -> None:
    # Rust: project layers are ordered from project root to cwd and project-local denylisted keys warn only when enabled.
    codex_home = tmp_path / "home"
    codex_home.mkdir()
    root = tmp_path / "repo"
    child = root / "child"
    (root / ".git").mkdir(parents=True)
    (root / ".codex").mkdir()
    (child / ".codex").mkdir(parents=True)
    (root / ".codex" / "config.toml").write_text(
        'model = "gpt-5"\nmodel_provider = "openai"\nmodel_instructions_file = "root.md"\n',
        encoding="utf-8",
    )
    (child / ".codex" / "config.toml").write_text('approval_policy = "never"\n', encoding="utf-8")
    trust_key = str(root.resolve(strict=False))
    context = project_trust_context(
        {"projects": {trust_key: {"trust_level": "trusted"}}},
        child,
        [".git"],
        codex_home,
        codex_home / "config.toml",
    )

    loaded = load_project_layers(child, root, context, codex_home)

    assert [layer.name.dot_codex_folder for layer in loaded.layers] == [root / ".codex", child / ".codex"]
    assert loaded.layers[0].config == {
        "model": "gpt-5",
        "model_instructions_file": str((root / ".codex" / "root.md").resolve(strict=False)),
    }
    assert loaded.layers[0].disabled_reason is None
    assert loaded.startup_warnings == (
        project_ignored_config_keys_warning(root / ".codex", ["model_provider"]),
    )


def test_load_project_layers_untrusted_keeps_disabled_empty_layer_for_bad_toml(tmp_path: Path) -> None:
    # Rust: bad untrusted project config records a disabled empty layer instead of failing.
    codex_home = tmp_path / "home"
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / ".codex").mkdir()
    (root / ".codex" / "config.toml").write_text("not = [valid\n", encoding="utf-8")
    context = project_trust_context(
        {"projects": {str(root.resolve(strict=False)): {"trust_level": "untrusted"}}},
        root,
        [".git"],
        codex_home,
        codex_home / "config.toml",
    )

    loaded = load_project_layers(root, root, context, codex_home)

    assert len(loaded.layers) == 1
    assert loaded.layers[0].config == {}
    assert loaded.layers[0].disabled_reason is not None
    assert "marked as untrusted" in loaded.layers[0].disabled_reason
    assert loaded.startup_warnings == ()


def test_load_project_layers_missing_config_still_records_project_layer(tmp_path: Path) -> None:
    # Rust: a .codex directory without config.toml still contributes a project layer.
    codex_home = tmp_path / "home"
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / ".codex").mkdir()
    context = project_trust_context(
        {"projects": {str(root.resolve(strict=False)): {"trust_level": "trusted"}}},
        root,
        [".git"],
        codex_home,
        codex_home / "config.toml",
    )

    loaded = load_project_layers(root, root, context, codex_home)

    assert len(loaded.layers) == 1
    assert loaded.layers[0].config == {}
    assert loaded.layers[0].disabled_reason is None


def test_merge_root_checkout_project_hooks_replaces_only_hooks(tmp_path: Path) -> None:
    root_hooks = tmp_path / "root" / ".codex"
    root_hooks.mkdir(parents=True)
    (root_hooks / "config.toml").write_text(
        """
[hooks]
on_turn_start = [{ command = "root-hook" }]
""",
        encoding="utf-8",
    )

    merged = merge_root_checkout_project_hooks(
        {"model": "gpt-5", "hooks": {"on_turn_start": [{"command": "local-hook"}]}},
        root_hooks,
        True,
    )

    assert merged["model"] == "gpt-5"
    assert merged["hooks"] == {"on_turn_start": [{"command": "root-hook"}]}


def test_merge_requirements_with_remote_sandbox_config_applies_before_source_merge() -> None:
    target = ConfigRequirementsWithSources()
    requirements = ConfigRequirementsToml.from_mapping(
        {
            "remote_sandbox_config": [
                {
                    "hostname_patterns": ["*.corp.example"],
                    "allowed_sandbox_modes": ["external-sandbox"],
                }
            ],
            "allowed_sandbox_modes": ["read-only"],
        }
    )

    merge_requirements_with_remote_sandbox_config(
        target,
        RequirementSource.system_requirements_toml("/etc/codex/requirements.toml"),
        requirements,
        hostname="build.corp.example",
    )

    assert target.allowed_sandbox_modes is not None
    assert target.allowed_sandbox_modes.value == (SandboxModeRequirement.EXTERNAL_SANDBOX,)


def test_cli_overrides_layer_validates_and_resolves_relative_paths(tmp_path: Path) -> None:
    # Rust: validate_cli_overrides_strictly rejects unknown -c fields and loader resolves path fields against cwd.
    layer = build_cli_overrides_layer_for_loader(
        ["model_instructions_file = \"notes.md\""],
        tmp_path,
        strict_config=True,
    )

    assert layer == {"model_instructions_file": str((tmp_path / "notes.md").resolve(strict=False))}
    with pytest.raises(ValueError, match="unknown configuration field `unknown_field`"):
        validate_cli_overrides_strictly({"unknown_field": True})


def test_load_config_layers_state_assembles_layers_requirements_and_warnings(tmp_path: Path) -> None:
    # Rust: load_config_layers_state composes system, user, project, session, thread, and legacy layers.
    codex_home = tmp_path / "home"
    codex_home.mkdir()
    system_config = tmp_path / "system.toml"
    requirements = tmp_path / "requirements.toml"
    user_config = codex_home / "config.toml"
    project = tmp_path / "repo"
    (project / ".git").mkdir(parents=True)
    (project / ".codex").mkdir()
    system_config.write_text('model = "system"\n', encoding="utf-8")
    requirements.write_text('allowed_sandbox_modes = ["read-only", "workspace-write"]\n', encoding="utf-8")
    project_key = str(project.resolve(strict=False)).replace("\\", "\\\\")
    user_config.write_text(
        f"""
model = "user"
[projects."{project_key}"]
trust_level = "trusted"
""",
        encoding="utf-8",
    )
    (project / ".codex" / "config.toml").write_text(
        'model_provider = "openai"\nmodel_instructions_file = "project.md"\n',
        encoding="utf-8",
    )
    loaded_managed = LoadedConfigLayers(
        managed_config=ManagedConfigFromFile(
            {"model": "managed"},
            tmp_path / "managed_config.toml",
        )
    )
    options = ConfigLoadOptions(
        loader_overrides=LoaderOverrides(
            system_config_path=system_config,
            system_requirements_path=requirements,
        ),
        strict_config=True,
    )
    thread_layer = ConfigLayerEntry.new(ConfigLayerSource.session_flags(), {"profile": "thread"})

    stack = load_config_layers_state(
        codex_home,
        cwd=project,
        cli_overrides=["model = \"cli\""],
        config_load_options=options,
        loaded_config_layers=loaded_managed,
        thread_config_layers=[thread_layer],
    )

    assert [layer.name.type for layer in stack.layers] == [
        "system",
        "user",
        "project",
        "session_flags",
        "session_flags",
        "legacy_managed_config_toml_from_file",
    ]
    assert stack.layers[2].config == {
        "model_instructions_file": str((project / ".codex" / "project.md").resolve(strict=False))
    }
    assert stack.layers[3].config == {"model": "cli"}
    assert stack.layers[4].config == {"profile": "thread"}
    assert stack.layers[5].config == {"model": "managed"}
    assert stack.startup_warnings() == (
        project_ignored_config_keys_warning(project / ".codex", ["model_provider"]),
    )
    assert stack.requirements_toml.allowed_sandbox_modes == (
        SandboxModeRequirement.READ_ONLY,
        SandboxModeRequirement.WORKSPACE_WRITE,
    )


def test_load_config_layers_state_autoloads_managed_config_layer(tmp_path: Path) -> None:
    codex_home = tmp_path / "home"
    codex_home.mkdir()
    system_config = tmp_path / "system.toml"
    managed = tmp_path / "managed_config.toml"
    system_config.write_text("", encoding="utf-8")
    managed.write_text('model = "managed"\n', encoding="utf-8")

    stack = load_config_layers_state(
        codex_home,
        config_load_options=ConfigLoadOptions(
            loader_overrides=LoaderOverrides(system_config_path=system_config, managed_config_path=managed),
            strict_config=True,
        ),
    )

    assert [layer.name.type for layer in stack.layers] == [
        "system",
        "user",
        "legacy_managed_config_toml_from_file",
    ]
    assert stack.layers[-1].config == {"model": "managed"}
