"""Runtime preparation helpers for ``codex exec``.

Ported from the pre-client portion of ``codex/codex-rs/exec/src/lib.rs``.
This module prepares the initial operation that will later be sent through the
in-process app-server client.  It deliberately stops before starting the agent
loop, which depends on the larger app-server/core ports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import sys
from typing import Any, BinaryIO, TextIO

from pycodex.protocol import ReviewRequest, ReviewTarget, UserInput

from .cli import ExecCli, ReviewArgs

JsonValue = Any


class ExecRunError(RuntimeError):
    """Raised when ``codex exec`` runtime preparation must abort."""


class StdinPromptBehavior(str, Enum):
    REQUIRED_IF_PIPED = "required_if_piped"
    FORCED = "forced"
    OPTIONAL_APPEND = "optional_append"


class PromptDecodeError(ValueError):
    """Matches upstream prompt decoding failures with actionable messages."""

    def __init__(
        self,
        kind: str,
        *,
        valid_up_to: int | None = None,
        encoding: str | None = None,
    ) -> None:
        self.kind = kind
        self.valid_up_to = valid_up_to
        self.encoding = encoding
        super().__init__(str(self))

    def __str__(self) -> str:
        if self.kind == "invalid_utf8":
            valid_up_to = 0 if self.valid_up_to is None else self.valid_up_to
            return (
                "input is not valid UTF-8 (invalid byte at offset "
                f"{valid_up_to}). Convert it to UTF-8 and retry "
                "(e.g., `iconv -f <ENC> -t UTF-8 prompt.txt`)."
            )
        if self.kind == "invalid_utf16":
            return (
                f"input looked like {self.encoding} but could not be decoded. "
                "Convert it to UTF-8 and retry."
            )
        if self.kind == "unsupported_bom":
            return f"input appears to be {self.encoding}. Convert it to UTF-8 and retry."
        return "failed to decode prompt"


@dataclass(frozen=True)
class InitialOperation:
    """Initial work submitted by ``codex exec`` after thread start/resume."""

    kind: str
    items: tuple[UserInput, ...] = ()
    output_schema: JsonValue | None = None
    review_request: ReviewRequest | None = None

    @classmethod
    def user_turn(cls, items: tuple[UserInput, ...], output_schema: JsonValue | None = None) -> "InitialOperation":
        return cls(kind="user_turn", items=items, output_schema=output_schema)

    @classmethod
    def review(cls, review_request: ReviewRequest) -> "InitialOperation":
        return cls(kind="review", review_request=review_request)


@dataclass(frozen=True)
class ExecRunPlan:
    """Prepared ``codex exec`` work before app-server client startup."""

    initial_operation: InitialOperation
    prompt_summary: str


def decode_prompt_bytes(input_bytes: bytes) -> str:
    """Decode prompt bytes using upstream BOM and UTF validation rules."""

    if input_bytes.startswith(b"\xef\xbb\xbf"):
        input_bytes = input_bytes[3:]

    if input_bytes.startswith(b"\xff\xfe\x00\x00"):
        raise PromptDecodeError("unsupported_bom", encoding="UTF-32LE")
    if input_bytes.startswith(b"\x00\x00\xfe\xff"):
        raise PromptDecodeError("unsupported_bom", encoding="UTF-32BE")
    if input_bytes.startswith(b"\xff\xfe"):
        return _decode_utf16(input_bytes[2:], "UTF-16LE", "utf-16-le")
    if input_bytes.startswith(b"\xfe\xff"):
        return _decode_utf16(input_bytes[2:], "UTF-16BE", "utf-16-be")

    try:
        return input_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PromptDecodeError("invalid_utf8", valid_up_to=exc.start) from exc


def _decode_utf16(input_bytes: bytes, label: str, codec: str) -> str:
    if len(input_bytes) % 2:
        raise PromptDecodeError("invalid_utf16", encoding=label)
    try:
        return input_bytes.decode(codec)
    except UnicodeDecodeError as exc:
        raise PromptDecodeError("invalid_utf16", encoding=label) from exc


def read_prompt_from_stdin(
    behavior: StdinPromptBehavior,
    *,
    stdin: bytes | str | BinaryIO | TextIO | None = None,
    stdin_is_terminal: bool | None = None,
    stderr: TextIO | None = None,
) -> str | None:
    """Read stdin according to upstream ``codex exec`` prompt rules."""

    err = sys.stderr if stderr is None else stderr
    terminal = _stdin_is_terminal(stdin, stdin_is_terminal)

    if behavior is StdinPromptBehavior.REQUIRED_IF_PIPED and terminal:
        raise ExecRunError("No prompt provided. Either specify one as an argument or pipe the prompt into stdin.")
    if behavior is StdinPromptBehavior.REQUIRED_IF_PIPED:
        print("Reading prompt from stdin...", file=err)
    elif behavior is StdinPromptBehavior.OPTIONAL_APPEND and terminal:
        return None
    elif behavior is StdinPromptBehavior.OPTIONAL_APPEND:
        print("Reading additional input from stdin...", file=err)

    try:
        prompt_bytes = _read_stdin_bytes(stdin)
    except OSError as exc:
        raise ExecRunError(f"Failed to read prompt from stdin: {exc}") from exc

    try:
        buffer = decode_prompt_bytes(prompt_bytes)
    except PromptDecodeError as exc:
        raise ExecRunError(f"Failed to read prompt from stdin: {exc}") from exc

    if buffer.strip() == "":
        if behavior is StdinPromptBehavior.OPTIONAL_APPEND:
            return None
        raise ExecRunError("No prompt provided via stdin.")

    return buffer


def _stdin_is_terminal(stdin: bytes | str | BinaryIO | TextIO | None, explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    candidate = sys.stdin if stdin is None else stdin
    isatty = getattr(candidate, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


def _read_stdin_bytes(stdin: bytes | str | BinaryIO | TextIO | None) -> bytes:
    if stdin is None:
        source = getattr(sys.stdin, "buffer", sys.stdin)
        data = source.read()
    elif isinstance(stdin, bytes):
        return stdin
    elif isinstance(stdin, str):
        return stdin.encode("utf-8")
    else:
        data = stdin.read()

    if isinstance(data, bytes):
        return data
    return str(data).encode("utf-8")


def prompt_with_stdin_context(prompt: str, stdin_text: str) -> str:
    combined = f"{prompt}\n\n<stdin>\n{stdin_text}"
    if not stdin_text.endswith("\n"):
        combined += "\n"
    return combined + "</stdin>"


def resolve_prompt(
    prompt_arg: str | None,
    *,
    stdin: bytes | str | BinaryIO | TextIO | None = None,
    stdin_is_terminal: bool | None = None,
    stderr: TextIO | None = None,
) -> str:
    if prompt_arg is not None and prompt_arg != "-":
        return prompt_arg

    behavior = StdinPromptBehavior.FORCED if prompt_arg == "-" else StdinPromptBehavior.REQUIRED_IF_PIPED
    prompt = read_prompt_from_stdin(
        behavior,
        stdin=stdin,
        stdin_is_terminal=stdin_is_terminal,
        stderr=stderr,
    )
    if prompt is None:
        raise AssertionError("required stdin prompt should produce content")
    return prompt


def resolve_root_prompt(
    prompt_arg: str | None,
    *,
    stdin: bytes | str | BinaryIO | TextIO | None = None,
    stdin_is_terminal: bool | None = None,
    stderr: TextIO | None = None,
) -> str:
    if prompt_arg is not None and prompt_arg != "-":
        stdin_text = read_prompt_from_stdin(
            StdinPromptBehavior.OPTIONAL_APPEND,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
            stderr=stderr,
        )
        if stdin_text is not None:
            return prompt_with_stdin_context(prompt_arg, stdin_text)
        return prompt_arg
    return resolve_prompt(
        prompt_arg,
        stdin=stdin,
        stdin_is_terminal=stdin_is_terminal,
        stderr=stderr,
    )


def load_output_schema(path: str | Path | None) -> JsonValue | None:
    if path is None:
        return None
    schema_path = Path(path)
    try:
        schema_str = schema_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ExecRunError(f"Failed to read output schema file {schema_path}: {exc}") from exc
    try:
        return json.loads(schema_str)
    except json.JSONDecodeError as exc:
        raise ExecRunError(f"Output schema file {schema_path} is not valid JSON: {exc}") from exc


def build_review_request(
    args: ReviewArgs,
    *,
    stdin: bytes | str | BinaryIO | TextIO | None = None,
    stdin_is_terminal: bool | None = None,
    stderr: TextIO | None = None,
) -> ReviewRequest:
    if args.uncommitted:
        target = ReviewTarget.uncommitted_changes()
    elif args.base is not None:
        target = ReviewTarget.base_branch(args.base)
    elif args.commit is not None:
        target = ReviewTarget.commit(args.commit, args.commit_title)
    elif args.prompt is not None:
        prompt = resolve_prompt(
            args.prompt,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
            stderr=stderr,
        ).strip()
        if prompt == "":
            raise ExecRunError("Review prompt cannot be empty")
        target = ReviewTarget.custom(prompt)
    else:
        raise ExecRunError("Specify --uncommitted, --base, --commit, or provide custom review instructions")

    return ReviewRequest(target=target, user_facing_hint=None)


def review_user_facing_hint(target: ReviewTarget) -> str:
    if target.type == "uncommittedChanges":
        return "current changes"
    if target.type == "baseBranch":
        return f"changes against '{target.branch}'"
    if target.type == "commit":
        short_sha = (target.sha or "")[:7]
        return f"commit {short_sha}: {target.title}" if target.title is not None else f"commit {short_sha}"
    if target.type == "custom":
        return (target.instructions or "").strip()
    raise ValueError(f"unknown review target type: {target.type}")


def prepare_exec_run_plan(
    cli: ExecCli,
    *,
    stdin: bytes | str | BinaryIO | TextIO | None = None,
    stdin_is_terminal: bool | None = None,
    stderr: TextIO | None = None,
) -> ExecRunPlan:
    """Build the initial operation and prompt summary for ``codex exec``."""

    if cli.command == "review":
        if cli.review is None:
            raise ExecRunError("review command is missing review arguments")
        review_request = build_review_request(
            cli.review,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
            stderr=stderr,
        )
        return ExecRunPlan(
            initial_operation=InitialOperation.review(review_request),
            prompt_summary=review_user_facing_hint(review_request.target),
        )

    if cli.command == "resume":
        if cli.resume is None:
            raise ExecRunError("resume command is missing resume arguments")
        prompt_arg = cli.resume.prompt
        if prompt_arg is None and cli.resume.last:
            prompt_arg = cli.resume.session_id
        if prompt_arg is None:
            prompt_arg = cli.prompt
        prompt_text = resolve_prompt(
            prompt_arg,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
            stderr=stderr,
        )
        image_paths = (*cli.images, *cli.resume.images)
    else:
        prompt_text = resolve_root_prompt(
            cli.prompt,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
            stderr=stderr,
        )
        image_paths = cli.images

    items = tuple(UserInput.local_image(Path(path)) for path in image_paths) + (UserInput.text_input(prompt_text),)
    return ExecRunPlan(
        initial_operation=InitialOperation.user_turn(items, load_output_schema(cli.output_schema)),
        prompt_summary=prompt_text,
    )


__all__ = [
    "ExecRunError",
    "ExecRunPlan",
    "InitialOperation",
    "PromptDecodeError",
    "StdinPromptBehavior",
    "build_review_request",
    "decode_prompt_bytes",
    "load_output_schema",
    "prepare_exec_run_plan",
    "prompt_with_stdin_context",
    "read_prompt_from_stdin",
    "resolve_prompt",
    "resolve_root_prompt",
    "review_user_facing_hint",
]
