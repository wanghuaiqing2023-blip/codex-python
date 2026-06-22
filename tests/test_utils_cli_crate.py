from pathlib import Path

import pytest

from pycodex.utils.cli import (
    ApprovalModeCliArg,
    CliConfigOverrides,
    SandboxModeCliArg,
    SharedCliOptions,
    apply_single_override,
    canonicalize_override_key,
    format_env_display,
)


def test_approval_mode_cli_arg_maps_to_protocol_approval_values() -> None:
    # Rust crate: codex-utils-cli
    # Rust module: approval_mode_cli_arg.rs
    # Rust contract: ApprovalModeCliArg -> AskForApproval mapping.
    assert ApprovalModeCliArg.UNTRUSTED.to_ask_for_approval() == "unless-trusted"
    assert ApprovalModeCliArg.ON_FAILURE.to_ask_for_approval() == "on-failure"
    assert ApprovalModeCliArg.ON_REQUEST.to_ask_for_approval() == "on-request"
    assert ApprovalModeCliArg.NEVER.to_ask_for_approval() == "never"


def test_sandbox_mode_cli_arg_maps_to_protocol_modes() -> None:
    # Rust crate: codex-utils-cli
    # Rust module: sandbox_mode_cli_arg.rs
    # Rust test: maps_cli_args_to_protocol_modes
    assert SandboxModeCliArg.READ_ONLY.to_sandbox_mode() == "read-only"
    assert SandboxModeCliArg.WORKSPACE_WRITE.to_sandbox_mode() == "workspace-write"
    assert SandboxModeCliArg.DANGER_FULL_ACCESS.to_sandbox_mode() == "danger-full-access"


def test_format_env_display_matches_rust_redaction_and_ordering() -> None:
    # Rust crate: codex-utils-cli
    # Rust module: format_env_display.rs
    # Rust tests: returns_dash_when_empty, formats_sorted_env_pairs,
    # formats_env_vars_with_dollar_prefix, combines_env_pairs_and_vars.
    assert format_env_display(None, []) == "-"
    assert format_env_display({}, []) == "-"
    assert format_env_display({"B": "two", "A": "one"}, []) == "A=*****, B=*****"
    assert format_env_display(None, ["TOKEN", "PATH"]) == "TOKEN=*****, PATH=*****"
    assert format_env_display({"HOME": "/tmp"}, ["TOKEN"]) == "HOME=*****, TOKEN=*****"


def test_cli_config_overrides_parse_and_apply_like_rust() -> None:
    # Rust crate: codex-utils-cli
    # Rust module: config_override.rs
    # Rust tests: parses_basic_scalar, parses_bool, fails_on_unquoted_string,
    # parses_array, parses_inline_table, canonicalizes_use_legacy_landlock_alias.
    overrides = CliConfigOverrides(
        [
            "count=42",
            "enabled=true",
            "name=hello",
            "values=[1, 2, 3]",
            "inline={a = 1, b = 2}",
            "use_legacy_landlock=false",
        ]
    )

    assert overrides.parse_overrides() == [
        ("count", 42),
        ("enabled", True),
        ("name", "hello"),
        ("values", [1, 2, 3]),
        ("inline", {"a": 1, "b": 2}),
        ("features.use_legacy_landlock", False),
    ]

    target = {"features": True}
    overrides.apply_on_value(target)
    assert target == {
        "count": 42,
        "enabled": True,
        "name": "hello",
        "values": [1, 2, 3],
        "inline": {"a": 1, "b": 2},
        "features": {"use_legacy_landlock": False},
    }


def test_cli_config_overrides_errors_and_precedence() -> None:
    # Rust crate: codex-utils-cli
    # Rust module: config_override.rs
    # Rust tests: prepends_root_overrides plus parse error boundaries.
    with pytest.raises(ValueError, match="missing '='"):
        CliConfigOverrides(["model"]).parse_overrides()
    with pytest.raises(ValueError, match="Empty key"):
        CliConfigOverrides([" = true"]).parse_overrides()

    subcommand_overrides = CliConfigOverrides(['model="gpt-5.2"'])
    subcommand_overrides.prepend_root_overrides(CliConfigOverrides(['model="gpt-5.1"']))
    assert subcommand_overrides.raw_overrides == ['model="gpt-5.1"', 'model="gpt-5.2"']
    assert canonicalize_override_key("model") == "model"

    target = {"features": False}
    apply_single_override(target, "features.use_legacy_landlock", True)
    assert target == {"features": {"use_legacy_landlock": True}}


def test_shared_cli_options_inherit_exec_root_options() -> None:
    # Rust crate: codex-utils-cli
    # Rust module: shared_options.rs
    # Rust contract: root options are inherited as lower-precedence defaults;
    # image/add-dir vectors are prepended.
    root = SharedCliOptions(
        images=[Path("root.png")],
        model="gpt-5.1",
        oss=True,
        oss_provider="ollama",
        config_profile_v2="profile-a",
        sandbox_mode=SandboxModeCliArg.READ_ONLY,
        dangerously_bypass_approvals_and_sandbox=True,
        bypass_hook_trust=True,
        cwd=Path("/root"),
        add_dir=[Path("/root-extra")],
    )
    child = SharedCliOptions(
        images=[Path("child.png")],
        model=None,
        sandbox_mode=None,
        dangerously_bypass_approvals_and_sandbox=False,
        cwd=None,
        add_dir=[Path("/child-extra")],
    )

    child.inherit_exec_root_options(root)

    assert child.images == [Path("root.png"), Path("child.png")]
    assert child.model == "gpt-5.1"
    assert child.oss is True
    assert child.oss_provider == "ollama"
    assert child.config_profile_v2 == "profile-a"
    assert child.sandbox_mode is SandboxModeCliArg.READ_ONLY
    assert child.dangerously_bypass_approvals_and_sandbox is True
    assert child.bypass_hook_trust is True
    assert child.cwd == Path("/root")
    assert child.add_dir == [Path("/root-extra"), Path("/child-extra")]


def test_shared_cli_options_respects_child_sandbox_selection() -> None:
    # Rust crate: codex-utils-cli
    # Rust module: shared_options.rs
    # Rust contract: child sandbox selection prevents root yolo inheritance.
    root = SharedCliOptions(
        sandbox_mode=SandboxModeCliArg.READ_ONLY,
        dangerously_bypass_approvals_and_sandbox=True,
    )
    child = SharedCliOptions(sandbox_mode=SandboxModeCliArg.WORKSPACE_WRITE)

    child.inherit_exec_root_options(root)

    assert child.sandbox_mode is SandboxModeCliArg.WORKSPACE_WRITE
    assert child.dangerously_bypass_approvals_and_sandbox is False


def test_shared_cli_options_apply_subcommand_overrides() -> None:
    # Rust crate: codex-utils-cli
    # Rust module: shared_options.rs
    # Rust contract: subcommand options replace selected scalar fields, images
    # replace when non-empty, and add-dir values append.
    root = SharedCliOptions(
        images=[Path("root.png")],
        model="gpt-5.1",
        oss_provider="ollama",
        sandbox_mode=SandboxModeCliArg.READ_ONLY,
        add_dir=[Path("/root-extra")],
    )
    subcommand = SharedCliOptions(
        images=[Path("sub.png")],
        model="gpt-5.2",
        oss=True,
        oss_provider="lmstudio",
        sandbox_mode=SandboxModeCliArg.DANGER_FULL_ACCESS,
        dangerously_bypass_approvals_and_sandbox=False,
        bypass_hook_trust=True,
        cwd=Path("/sub"),
        add_dir=[Path("/sub-extra")],
    )

    root.apply_subcommand_overrides(subcommand)

    assert root.images == [Path("sub.png")]
    assert root.model == "gpt-5.2"
    assert root.oss is True
    assert root.oss_provider == "lmstudio"
    assert root.sandbox_mode is SandboxModeCliArg.DANGER_FULL_ACCESS
    assert root.dangerously_bypass_approvals_and_sandbox is False
    assert root.bypass_hook_trust is True
    assert root.cwd == Path("/sub")
    assert root.add_dir == [Path("/root-extra"), Path("/sub-extra")]
