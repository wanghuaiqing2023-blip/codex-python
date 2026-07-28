"""Rust-aligned codex-execpolicy module."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .execpolicycheck import ExecPolicyCheckCommand

@dataclass(frozen=True)
class Cli:
    command: ExecPolicyCheckCommand


def parse_execpolicy_cli(args: Sequence[str]) -> Cli:
    tokens = [str(arg) for arg in args]
    if not tokens:
        raise ValueError("codex-execpolicy requires a subcommand: check")
    subcommand, *rest = tokens
    if subcommand != "check":
        raise ValueError(f"Unknown codex-execpolicy subcommand: {subcommand}")

    rules: list[Path] = []
    command: list[str] = []
    pretty = False
    resolve_host_executables = False
    index = 0
    while index < len(rest):
        token = rest[index]
        if token in ("-r", "--rules"):
            index += 1
            if index >= len(rest):
                raise ValueError("codex-execpolicy check requires --rules PATH")
            rules.append(Path(rest[index]))
        elif token == "--pretty":
            pretty = True
        elif token == "--resolve-host-executables":
            resolve_host_executables = True
        elif token == "--":
            command.extend(rest[index + 1 :])
            break
        else:
            command.extend(rest[index:])
            break
        index += 1

    if not rules:
        raise ValueError("codex-execpolicy check requires --rules")
    if not command:
        raise ValueError("codex-execpolicy check requires COMMAND")
    return Cli(
        ExecPolicyCheckCommand(
            rules=rules,
            command=command,
            pretty=pretty,
            resolve_host_executables=resolve_host_executables,
        )
    )


def main(args: Sequence[str]) -> str:
    cli = parse_execpolicy_cli(args)
    return cli.command.run()

__all__ = ['Cli', 'main', 'parse_execpolicy_cli']
