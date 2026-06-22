"""Rust-derived tests for codex-execpolicy/src/main.rs CLI dispatch surface."""

from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.execpolicy import ExecPolicyCheckCommand, ExecPolicyCli, parse_execpolicy_cli, run_execpolicy_cli


def test_parse_execpolicy_cli_builds_check_command():
    """Rust main.rs: Cli::Check wraps ExecPolicyCheckCommand parsed by clap."""
    cli = parse_execpolicy_cli(
        [
            "check",
            "--rules",
            "policy.rules",
            "--pretty",
            "--resolve-host-executables",
            "git",
            "status",
        ]
    )

    assert cli == ExecPolicyCli(
        ExecPolicyCheckCommand(
            rules=[Path("policy.rules")],
            command=["git", "status"],
            pretty=True,
            resolve_host_executables=True,
        )
    )


def test_parse_execpolicy_cli_supports_repeat_rules_and_trailing_command_dashdash():
    """Rust execpolicycheck.rs clap args: --rules repeat and trailing command tokens allowed."""
    cli = parse_execpolicy_cli(
        ["check", "-r", "one.rules", "--rules", "two.rules", "--", "-h"]
    )

    assert cli.command.rules == (Path("one.rules"), Path("two.rules"))
    assert cli.command.command == ("-h",)


def test_parse_execpolicy_cli_rejects_missing_or_unknown_subcommands():
    """Rust main.rs has only the Check subcommand."""
    with pytest.raises(ValueError, match="requires a subcommand"):
        parse_execpolicy_cli([])

    with pytest.raises(ValueError, match="Unknown codex-execpolicy subcommand"):
        parse_execpolicy_cli(["unknown"])


def test_parse_execpolicy_cli_requires_rules_and_command():
    """Rust ExecPolicyCheckCommand requires rules and command args."""
    with pytest.raises(ValueError, match="requires --rules"):
        parse_execpolicy_cli(["check", "git", "status"])

    with pytest.raises(ValueError, match="requires COMMAND"):
        parse_execpolicy_cli(["check", "--rules", "policy.rules"])


def test_run_execpolicy_cli_dispatches_to_check_command_and_reports_missing_policy():
    """Rust main.rs dispatches Check(cmd) to cmd.run; load_policies reports missing files."""
    with pytest.raises(OSError, match="failed to read policy at"):
        run_execpolicy_cli(["check", "--rules", "policy.rules", "git", "status"])
