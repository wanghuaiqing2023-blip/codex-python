"""TUI CLI option models for the Python port.

Rust counterpart: ``codex-rs/tui/src/cli.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping


@dataclass
class TuiSharedCliOptions:
    """Wrapper matching Rust ``TuiSharedCliOptions(SharedCliOptions)``."""

    value: Any = field(default_factory=dict)

    def into_inner(self) -> Any:
        return self.value

    def deref(self) -> Any:
        return self.value

    def deref_mut(self) -> Any:
        return self.value

    @classmethod
    def from_arg_matches(cls, matches: Mapping[str, Any]) -> "TuiSharedCliOptions":
        return cls(dict(matches))

    def update_from_arg_matches(self, matches: Mapping[str, Any]) -> None:
        if isinstance(self.value, MutableMapping):
            self.value.update(matches)
        else:
            for key, val in matches.items():
                setattr(self.value, key, val)


@dataclass
class Cli:
    prompt: str | None = None
    strict_config: bool = False
    resume_picker: bool = False
    resume_last: bool = False
    resume_session_id: str | None = None
    resume_show_all: bool = False
    resume_include_non_interactive: bool = False
    fork_picker: bool = False
    fork_last: bool = False
    fork_session_id: str | None = None
    fork_show_all: bool = False
    shared: TuiSharedCliOptions = field(default_factory=TuiSharedCliOptions)
    approval_policy: Any | None = None
    web_search: bool = False
    no_alt_screen: bool = False
    config_overrides: Any = field(default_factory=dict)

    def deref(self) -> Any:
        return self.shared.deref()

    def deref_mut(self) -> Any:
        return self.shared.deref_mut()


Target = Any


def deref(cli: Cli | TuiSharedCliOptions) -> Any:
    return cli.deref()


def deref_mut(cli: Cli | TuiSharedCliOptions) -> Any:
    return cli.deref_mut()


def mark_tui_args(cmd: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Mark shared CLI bypass flag as conflicting with TUI approval policy.

    Rust mutates the clap arg ``dangerously_bypass_approvals_and_sandbox`` with
    ``conflicts_with("approval_policy")``. Python accepts a lightweight command
    schema mapping and records the same semantic conflict.
    """

    args = cmd.setdefault("args", {})
    arg = args.setdefault("dangerously_bypass_approvals_and_sandbox", {})
    conflicts = arg.setdefault("conflicts_with", [])
    if "approval_policy" not in conflicts:
        conflicts.append("approval_policy")
    return cmd


def augment_args(cmd: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    return mark_tui_args(cmd)


def augment_args_for_update(cmd: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    return mark_tui_args(cmd)


def from_arg_matches(matches: Mapping[str, Any]) -> TuiSharedCliOptions:
    return TuiSharedCliOptions.from_arg_matches(matches)


def update_from_arg_matches(options: TuiSharedCliOptions, matches: Mapping[str, Any]) -> None:
    options.update_from_arg_matches(matches)


__all__ = [
    "Cli",
    "Target",
    "TuiSharedCliOptions",
    "augment_args",
    "augment_args_for_update",
    "deref",
    "deref_mut",
    "from_arg_matches",
    "mark_tui_args",
    "update_from_arg_matches",
]
