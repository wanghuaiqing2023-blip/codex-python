from pycodex.tui.update_action import (
    InstallContext,
    InstallMethod,
    StandalonePlatform,
    UpdateAction,
    get_update_action,
)
from pycodex.install_context import InstallContext as RealInstallContext
from pycodex.install_context import InstallMethod as RealInstallMethod
from pycodex.install_context import StandalonePlatform as RealStandalonePlatform


def test_maps_install_context_to_update_action():
    # Rust: codex-tui, update_action.rs, maps_install_context_to_update_action.
    assert UpdateAction.from_install_context(InstallContext(InstallMethod.OTHER)) is None
    assert UpdateAction.from_install_context(InstallContext(InstallMethod.NPM)) is UpdateAction.NPM_GLOBAL_LATEST
    assert UpdateAction.from_install_context(InstallContext(InstallMethod.BUN)) is UpdateAction.BUN_GLOBAL_LATEST
    assert UpdateAction.from_install_context(InstallContext(InstallMethod.BREW)) is UpdateAction.BREW_UPGRADE
    assert (
        UpdateAction.from_install_context(InstallContext(InstallMethod.STANDALONE, StandalonePlatform.UNIX))
        is UpdateAction.STANDALONE_UNIX
    )
    assert (
        UpdateAction.from_install_context(InstallContext(InstallMethod.STANDALONE, StandalonePlatform.WINDOWS))
        is UpdateAction.STANDALONE_WINDOWS
    )


def test_update_action_command_args_match_rust_table():
    assert UpdateAction.NPM_GLOBAL_LATEST.command_args() == ("npm", ("install", "-g", "@openai/codex"))
    assert UpdateAction.BUN_GLOBAL_LATEST.command_args() == ("bun", ("install", "-g", "@openai/codex"))
    assert UpdateAction.BREW_UPGRADE.command_args() == ("brew", ("upgrade", "--cask", "codex"))


def test_standalone_update_commands_rerun_latest_installer():
    # Rust: codex-tui, update_action.rs, standalone_update_commands_rerun_latest_installer.
    assert UpdateAction.STANDALONE_UNIX.command_args() == (
        "sh",
        ("-c", "curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh"),
    )
    assert UpdateAction.STANDALONE_WINDOWS.command_args() == (
        "powershell",
        (
            "-ExecutionPolicy",
            "Bypass",
            "-c",
            "$env:CODEX_NON_INTERACTIVE=1; irm https://chatgpt.com/codex/install.ps1 | iex",
        ),
    )


def test_command_str_uses_shell_join_semantics():
    assert UpdateAction.NPM_GLOBAL_LATEST.command_str() == "npm install -g @openai/codex"
    assert UpdateAction.BREW_UPGRADE.command_str() == "brew upgrade --cask codex"
    assert UpdateAction.STANDALONE_UNIX.command_str() == (
        "sh -c 'curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh'"
    )


def test_get_update_action_uses_injected_or_ported_install_context_detector():
    assert get_update_action(InstallContext("npm")) is UpdateAction.NPM_GLOBAL_LATEST
    assert get_update_action(current_context=lambda: InstallContext("bun")) is UpdateAction.BUN_GLOBAL_LATEST
    assert get_update_action(current_context=lambda: None) is None


def test_get_update_action_accepts_real_install_context_shapes():
    assert get_update_action(RealInstallContext(RealInstallMethod.Npm())) is UpdateAction.NPM_GLOBAL_LATEST
    assert get_update_action(RealInstallContext(RealInstallMethod.Bun())) is UpdateAction.BUN_GLOBAL_LATEST
    assert get_update_action(RealInstallContext(RealInstallMethod.Brew())) is UpdateAction.BREW_UPGRADE
    assert (
        get_update_action(
            RealInstallContext(
                RealInstallMethod(
                    kind="standalone",
                    platform=RealStandalonePlatform.WINDOWS,
                )
            )
        )
        is UpdateAction.STANDALONE_WINDOWS
    )
