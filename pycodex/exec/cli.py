"""Parser for the ``codex exec`` command.

Ported from ``codex/codex-rs/exec/src/cli.rs`` and
``codex/codex-rs/exec/src/main.rs``. This module covers the command-line shape
only; running the non-interactive agent is intentionally future work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable

from pycodex.arg0 import Arg0DispatchPaths, CODEX_LINUX_SANDBOX_ARG0
from pycodex.config import CliConfigOverrides
from pycodex.protocol import AskForApproval, ProfileV2Name, ProfileV2NameParseError, SandboxMode
from pycodex.protocol.config_types import ConfigTypeParseError


UPSTREAM_EXEC_CLI = "codex/codex-rs/exec/src/cli.rs"
UPSTREAM_EXEC_MAIN = "codex/codex-rs/exec/src/main.rs"
FULL_AUTO_WARNING = "warning: `--full-auto` is deprecated; use `--sandbox workspace-write` instead."


class ExecCliParseError(ValueError):
    """Raised when ``codex exec`` arguments are invalid."""


class Color(str, Enum):
    ALWAYS = "always"
    NEVER = "never"
    AUTO = "auto"

    @classmethod
    def default(cls) -> "Color":
        return cls.AUTO

    @classmethod
    def parse(cls, raw: str) -> "Color":
        try:
            return cls(raw)
        except ValueError as exc:
            raise ExecCliParseError("invalid Color value `{}`; expected one of: always, never, auto".format(raw)) from exc


@dataclass(frozen=True)
class ResumeArgs:
    session_id: str | None = None
    last: bool = False
    all: bool = False
    images: tuple[str, ...] = ()
    prompt: str | None = None


@dataclass(frozen=True)
class ReviewArgs:
    uncommitted: bool = False
    base: str | None = None
    commit: str | None = None
    commit_title: str | None = None
    prompt: str | None = None


@dataclass(frozen=True)
class ExecCli:
    command: str | None = None
    resume: ResumeArgs | None = None
    review: ReviewArgs | None = None
    strict_config: bool = False
    skip_git_repo_check: bool = False
    ephemeral: bool = False
    ignore_user_config: bool = False
    ignore_rules: bool = False
    removed_full_auto: bool = False
    output_schema: str | None = None
    color: Color = Color.AUTO
    json: bool = False
    last_message_file: str | None = None
    prompt: str | None = None
    config_overrides: tuple[str, ...] = ()
    images: tuple[str, ...] = ()
    model: str | None = None
    oss: bool = False
    local_provider: str | None = None
    profile: ProfileV2Name | None = None
    approval_policy: AskForApproval | None = None
    sandbox: SandboxMode | None = None
    dangerously_bypass_approvals_and_sandbox: bool = False
    dangerously_bypass_hook_trust: bool = False
    cwd: str | None = None
    add_dir: tuple[str, ...] = ()
    upstream_source: str = UPSTREAM_EXEC_CLI

    def removed_full_auto_warning(self) -> str | None:
        if self.removed_full_auto:
            return FULL_AUTO_WARNING
        return None

    def effective_sandbox_mode(self) -> SandboxMode | None:
        """Resolve the sandbox mode precedence applied by upstream exec runtime."""

        if self.removed_full_auto:
            return SandboxMode.WORKSPACE_WRITE
        if self.dangerously_bypass_approvals_and_sandbox:
            return SandboxMode.DANGER_FULL_ACCESS
        return self.sandbox

    def cli_config_overrides(self) -> CliConfigOverrides:
        return CliConfigOverrides(list(self.config_overrides))


@dataclass(frozen=True)
class ExecMainDispatchPlan:
    """Pure startup decision for Rust ``codex-exec`` ``src/main.rs``.

    The Rust binary lets ``codex_arg0`` perform the process-level dispatch
    before parsing the normal ``TopCli`` wrapper.  Python keeps this as a pure
    plan so tests and callers can verify the selected branch without launching
    the linux sandbox helper.
    """

    kind: str
    argv: tuple[str, ...]
    cli: ExecCli | None = None
    arg0_paths: Arg0DispatchPaths = Arg0DispatchPaths()
    upstream_source: str = UPSTREAM_EXEC_MAIN

    @property
    def is_exec(self) -> bool:
        return self.kind == "exec"

    @property
    def is_linux_sandbox(self) -> bool:
        return self.kind == "linux_sandbox"


@dataclass
class _ExecState:
    strict_config: bool = False
    skip_git_repo_check: bool = False
    ephemeral: bool = False
    ignore_user_config: bool = False
    ignore_rules: bool = False
    removed_full_auto: bool = False
    output_schema: str | None = None
    color: Color = Color.AUTO
    json: bool = False
    last_message_file: str | None = None
    config_overrides: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    model: str | None = None
    oss: bool = False
    local_provider: str | None = None
    profile: ProfileV2Name | None = None
    approval_policy: AskForApproval | None = None
    sandbox: SandboxMode | None = None
    dangerously_bypass_approvals_and_sandbox: bool = False
    dangerously_bypass_hook_trust: bool = False
    cwd: str | None = None
    add_dir: list[str] = field(default_factory=list)


@dataclass
class _ResumeState:
    last: bool = False
    all: bool = False
    images: list[str] = field(default_factory=list)
    positionals: list[str] = field(default_factory=list)


@dataclass
class _ReviewState:
    uncommitted: bool = False
    base: str | None = None
    commit: str | None = None
    commit_title: str | None = None
    positionals: list[str] = field(default_factory=list)


_GLOBAL_VALUE_OPTIONS = {
    "-c": "config",
    "--config": "config",
    "-i": "image",
    "--image": "image",
    "--output-schema": "output_schema",
    "--color": "color",
    "-o": "last_message_file",
    "--output-last-message": "last_message_file",
    "-m": "model",
    "--model": "model",
    "--local-provider": "local_provider",
    "-p": "profile",
    "--profile": "profile",
    "-a": "approval_policy",
    "--ask-for-approval": "approval_policy",
    "-s": "sandbox",
    "--sandbox": "sandbox",
    "-C": "cwd",
    "--cd": "cwd",
    "--add-dir": "add_dir",
}

_GLOBAL_FLAG_OPTIONS = {
    "--strict-config": "strict_config",
    "--skip-git-repo-check": "skip_git_repo_check",
    "--ephemeral": "ephemeral",
    "--ignore-user-config": "ignore_user_config",
    "--ignore-rules": "ignore_rules",
    "--full-auto": "removed_full_auto",
    "--json": "json",
    "--experimental-json": "json",
    "--oss": "oss",
    "--dangerously-bypass-approvals-and-sandbox": "dangerously_bypass_approvals_and_sandbox",
    "--yolo": "dangerously_bypass_approvals_and_sandbox",
    "--dangerously-bypass-hook-trust": "dangerously_bypass_hook_trust",
}

_SUBCOMMAND_GLOBAL_VALUE_OPTIONS = {
    "-c",
    "--config",
    "--output-schema",
    "-o",
    "--output-last-message",
    "-m",
    "--model",
    "-a",
    "--ask-for-approval",
}

_SUBCOMMAND_GLOBAL_FLAG_OPTIONS = {
    "--strict-config",
    "--skip-git-repo-check",
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "--full-auto",
    "--json",
    "--experimental-json",
    "--dangerously-bypass-approvals-and-sandbox",
    "--yolo",
    "--dangerously-bypass-hook-trust",
}


def parse_exec_args(argv: Iterable[str] | None = None, root_config_overrides: Iterable[str] = ()) -> ExecCli:
    """Parse arguments after ``codex exec``."""

    tokens = list(argv or ())
    state = _ExecState(config_overrides=list(root_config_overrides))
    prompt: str | None = None
    index = 0

    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            remaining = tokens[index + 1 :]
            if len(remaining) > 1:
                raise ExecCliParseError("Unexpected extra argument(s): {}".format(" ".join(remaining[1:])))
            prompt = remaining[0] if remaining else prompt
            break

        if token == "resume":
            return _finish_exec(state, command="resume", resume=_parse_resume_args(tokens[index + 1 :], state))
        if token == "review":
            return _finish_exec(state, command="review", review=_parse_review_args(tokens[index + 1 :], state))

        consumed = _consume_global_option(tokens, index, state, allow_exec_only=True)
        if consumed:
            index += consumed
            continue

        if token != "-" and token.startswith("-"):
            raise ExecCliParseError(f"Unknown option: {token}")
        if prompt is not None:
            raise ExecCliParseError(f"Unexpected extra argument(s): {token}")
        prompt = token
        index += 1

    return _finish_exec(state, prompt=prompt)


def exec_main_dispatch_plan(
    argv: Iterable[str] | None = None,
    *,
    arg0_paths: Arg0DispatchPaths | None = None,
    root_config_overrides: Iterable[str] = (),
) -> ExecMainDispatchPlan:
    """Plan the Rust ``src/main.rs`` entrypoint branch for a full argv vector."""

    tokens = tuple(argv or ())
    argv0 = _argv0_name(tokens[0] if tokens else "")
    paths = arg0_paths if arg0_paths is not None else Arg0DispatchPaths()

    if argv0 == CODEX_LINUX_SANDBOX_ARG0:
        return ExecMainDispatchPlan(kind="linux_sandbox", argv=tokens[1:], arg0_paths=paths)

    return ExecMainDispatchPlan(
        kind="exec",
        argv=tokens[1:],
        cli=parse_exec_args(tokens[1:], root_config_overrides=root_config_overrides),
        arg0_paths=paths,
    )


def _argv0_name(argv0: str) -> str:
    name = Path(argv0).name
    return name[:-4] if name.lower().endswith(".exe") else name


def _parse_resume_args(tokens: list[str], state: _ExecState) -> ResumeArgs:
    resume = _ResumeState()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            resume.positionals.extend(tokens[index + 1 :])
            break
        if token == "--last":
            resume.last = True
            index += 1
            continue
        if token == "--all":
            resume.all = True
            index += 1
            continue
        if token in ("-i", "--image") or token.startswith("--image="):
            value, consumed = _read_option_value(tokens, index, token, "--image")
            resume.images.extend(part for part in value.split(",") if part)
            index += consumed
            continue

        consumed = _consume_global_option(tokens, index, state, allow_exec_only=False)
        if consumed:
            index += consumed
            continue

        if token != "-" and token.startswith("-"):
            raise ExecCliParseError(f"Unknown resume option: {token}")
        resume.positionals.append(token)
        index += 1

    if len(resume.positionals) > 2:
        raise ExecCliParseError("Unexpected extra argument(s): {}".format(" ".join(resume.positionals[2:])))

    session_id = resume.positionals[0] if resume.positionals else None
    prompt = resume.positionals[1] if len(resume.positionals) > 1 else None
    if resume.last and prompt is None:
        session_id, prompt = None, session_id
    return ResumeArgs(
        session_id=session_id,
        last=resume.last,
        all=resume.all,
        images=tuple(resume.images),
        prompt=prompt,
    )


def _parse_review_args(tokens: list[str], state: _ExecState) -> ReviewArgs:
    review = _ReviewState()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            review.positionals.extend(tokens[index + 1 :])
            break
        if token == "--uncommitted":
            review.uncommitted = True
            index += 1
            continue
        if token == "--base" or token.startswith("--base="):
            review.base, consumed = _read_option_value(tokens, index, token, "--base")
            index += consumed
            continue
        if token == "--commit" or token.startswith("--commit="):
            review.commit, consumed = _read_option_value(tokens, index, token, "--commit")
            index += consumed
            continue
        if token == "--title" or token.startswith("--title="):
            review.commit_title, consumed = _read_option_value(tokens, index, token, "--title")
            index += consumed
            continue

        consumed = _consume_global_option(tokens, index, state, allow_exec_only=False)
        if consumed:
            index += consumed
            continue

        if token != "-" and token.startswith("-"):
            raise ExecCliParseError(f"Unknown review option: {token}")
        review.positionals.append(token)
        index += 1

    if len(review.positionals) > 1:
        raise ExecCliParseError("Unexpected extra argument(s): {}".format(" ".join(review.positionals[1:])))

    prompt = review.positionals[0] if review.positionals else None
    selected_targets = sum(bool(value) for value in (review.uncommitted, review.base, review.commit, prompt))
    if selected_targets > 1:
        raise ExecCliParseError("--uncommitted, --base, --commit, and PROMPT are mutually exclusive")
    if review.commit_title is not None and review.commit is None:
        raise ExecCliParseError("--title requires --commit")
    return ReviewArgs(
        uncommitted=review.uncommitted,
        base=review.base,
        commit=review.commit,
        commit_title=review.commit_title,
        prompt=prompt,
    )


def _consume_global_option(
    tokens: list[str],
    index: int,
    state: _ExecState,
    *,
    allow_exec_only: bool,
) -> int:
    token = tokens[index]
    if token in _GLOBAL_FLAG_OPTIONS:
        if not allow_exec_only and token not in _SUBCOMMAND_GLOBAL_FLAG_OPTIONS:
            return 0
        attr = _GLOBAL_FLAG_OPTIONS[token]
        if attr == "dangerously_bypass_approvals_and_sandbox" and state.removed_full_auto:
            raise ExecCliParseError("--full-auto conflicts with --dangerously-bypass-approvals-and-sandbox")
        if attr == "removed_full_auto" and state.dangerously_bypass_approvals_and_sandbox:
            raise ExecCliParseError("--full-auto conflicts with --dangerously-bypass-approvals-and-sandbox")
        setattr(state, attr, True)
        return 1

    option, separator, _ = token.partition("=")
    if (separator and option in _GLOBAL_VALUE_OPTIONS) or token in _GLOBAL_VALUE_OPTIONS:
        key = option if separator else token
        if not allow_exec_only and key not in _SUBCOMMAND_GLOBAL_VALUE_OPTIONS:
            return 0
        value, consumed = _read_option_value(tokens, index, token, key)
        _store_global_value(_GLOBAL_VALUE_OPTIONS[key], value, state, key)
        return consumed

    return 0


def _read_option_value(tokens: list[str], index: int, token: str, option: str) -> tuple[str, int]:
    split_option, separator, inline_value = token.partition("=")
    if separator and split_option == option:
        return inline_value, 1
    if index + 1 >= len(tokens):
        raise ExecCliParseError(f"Missing value for option: {option}")
    return tokens[index + 1], 2


def _store_global_value(dest: str, value: str, state: _ExecState, option: str) -> None:
    if value == "" and dest != "config":
        raise ExecCliParseError(f"Missing value for option: {option}")
    if dest == "config":
        state.config_overrides.append(value)
    elif dest == "output_schema":
        state.output_schema = value
    elif dest == "color":
        state.color = Color.parse(value)
    elif dest == "last_message_file":
        state.last_message_file = value
    elif dest == "image":
        state.images.extend(part for part in value.split(",") if part)
    elif dest == "model":
        state.model = value
    elif dest == "local_provider":
        state.local_provider = value
    elif dest == "profile":
        try:
            state.profile = ProfileV2Name.parse(value)
        except ProfileV2NameParseError as exc:
            raise ExecCliParseError(str(exc)) from exc
    elif dest == "approval_policy":
        try:
            state.approval_policy = AskForApproval.parse_cli(value)
        except ConfigTypeParseError as exc:
            raise ExecCliParseError(str(exc)) from exc
    elif dest == "sandbox":
        try:
            state.sandbox = SandboxMode.parse(value)
        except ConfigTypeParseError as exc:
            raise ExecCliParseError(str(exc)) from exc
    elif dest == "cwd":
        state.cwd = value
    elif dest == "add_dir":
        state.add_dir.append(value)
    else:
        raise AssertionError(f"unhandled exec option destination: {dest}")


def _finish_exec(
    state: _ExecState,
    *,
    command: str | None = None,
    resume: ResumeArgs | None = None,
    review: ReviewArgs | None = None,
    prompt: str | None = None,
) -> ExecCli:
    return ExecCli(
        command=command,
        resume=resume,
        review=review,
        strict_config=state.strict_config,
        skip_git_repo_check=state.skip_git_repo_check,
        ephemeral=state.ephemeral,
        ignore_user_config=state.ignore_user_config,
        ignore_rules=state.ignore_rules,
        removed_full_auto=state.removed_full_auto,
        output_schema=state.output_schema,
        color=state.color,
        json=state.json,
        last_message_file=state.last_message_file,
        prompt=prompt,
        config_overrides=tuple(state.config_overrides),
        images=tuple(state.images),
        model=state.model,
        oss=state.oss,
        local_provider=state.local_provider,
        profile=state.profile,
        approval_policy=state.approval_policy,
        sandbox=state.sandbox,
        dangerously_bypass_approvals_and_sandbox=state.dangerously_bypass_approvals_and_sandbox,
        dangerously_bypass_hook_trust=state.dangerously_bypass_hook_trust,
        cwd=state.cwd,
        add_dir=tuple(state.add_dir),
    )
