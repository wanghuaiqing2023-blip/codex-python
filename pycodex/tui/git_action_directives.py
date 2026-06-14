"""Codex App git action directives embedded in assistant markdown.

Rust source: ``codex/codex-rs/tui/src/git_action_directives.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="git_action_directives",
    source="codex/codex-rs/tui/src/git_action_directives.rs",
)


@dataclass(frozen=True)
class GitActionDirective:
    kind: str
    cwd: str
    branch: str | None = None
    url: str | None = None
    is_draft: bool = False

    @classmethod
    def Stage(cls, cwd: str) -> "GitActionDirective":
        return cls("Stage", cwd=cwd)

    @classmethod
    def Commit(cls, cwd: str) -> "GitActionDirective":
        return cls("Commit", cwd=cwd)

    @classmethod
    def CreateBranch(cls, cwd: str, branch: str) -> "GitActionDirective":
        return cls("CreateBranch", cwd=cwd, branch=branch)

    @classmethod
    def Push(cls, cwd: str, branch: str) -> "GitActionDirective":
        return cls("Push", cwd=cwd, branch=branch)

    @classmethod
    def CreatePr(cls, cwd: str, branch: str, url: str | None, is_draft: bool) -> "GitActionDirective":
        return cls("CreatePr", cwd=cwd, branch=branch, url=url, is_draft=is_draft)

    def created_branch_cwd(self) -> str | None:
        return self.cwd if self.kind == "CreateBranch" else None


@dataclass(eq=True)
class ParsedAssistantMarkdown:
    visible_markdown: str
    git_actions: list[GitActionDirective]

    def last_created_branch_cwd(self) -> str | None:
        for action in reversed(self.git_actions):
            cwd = action.created_branch_cwd()
            if cwd is not None:
                return cwd
        return None


def parse_assistant_markdown(markdown: str) -> ParsedAssistantMarkdown:
    git_actions: list[GitActionDirective] = []
    seen: set[GitActionDirective] = set()
    visible_lines: list[str] = []

    for line in markdown.splitlines():
        visible_line, line_actions = strip_line_directives(line)
        for action in line_actions:
            if action not in seen:
                seen.add(action)
                git_actions.append(action)
        visible_lines.append(visible_line.rstrip())

    while visible_lines and visible_lines[-1] == "":
        visible_lines.pop()

    return ParsedAssistantMarkdown("\n".join(visible_lines), git_actions)


def strip_line_directives(line: str) -> tuple[str, list[GitActionDirective]]:
    visible = ""
    actions: list[GitActionDirective] = []
    remaining = line

    while True:
        start = remaining.find("::git-")
        if start < 0:
            visible += remaining
            return visible, actions
        visible += remaining[:start]
        directive = remaining[start + 2 :]
        open_brace = directive.find("{")
        if open_brace < 0:
            visible += remaining[start:]
            return visible, actions
        close_offset = directive[open_brace + 1 :].find("}")
        if close_offset < 0:
            visible += remaining[start:]
            return visible, actions
        close_brace = open_brace + 1 + close_offset
        name = directive[:open_brace]
        attributes = directive[open_brace + 1 : close_brace]
        action = parse_git_action(name, attributes)
        if action is not None:
            actions.append(action)
        remaining = directive[close_brace + 1 :]


def parse_git_action(name: str, attributes: str) -> GitActionDirective | None:
    attrs = parse_attributes(attributes)
    if attrs is None:
        return None
    cwd = attrs.get("cwd")
    if cwd is None:
        return None
    if name == "git-stage":
        return GitActionDirective.Stage(cwd)
    if name == "git-commit":
        return GitActionDirective.Commit(cwd)
    if name == "git-create-branch":
        branch = attrs.get("branch")
        return GitActionDirective.CreateBranch(cwd, branch) if branch is not None else None
    if name == "git-push":
        branch = attrs.get("branch")
        return GitActionDirective.Push(cwd, branch) if branch is not None else None
    if name == "git-create-pr":
        branch = attrs.get("branch")
        if branch is None:
            return None
        return GitActionDirective.CreatePr(
            cwd=cwd,
            branch=branch,
            url=attrs.get("url"),
            is_draft=attrs.get("isDraft") == "true",
        )
    return None


def parse_attributes(input_text: str) -> dict[str, str] | None:
    attrs: dict[str, str] = {}
    rest = input_text.strip()
    while rest:
        eq = rest.find("=")
        if eq < 0:
            return None
        key = rest[:eq].strip()
        if not key:
            return None
        rest = rest[eq + 1 :].lstrip()
        if rest.startswith('"'):
            quoted = rest[1:]
            end = quoted.find('"')
            if end < 0:
                return None
            value = quoted[:end]
            next_rest = quoted[end + 1 :]
        else:
            whitespace_positions = [idx for idx, ch in enumerate(rest) if ch.isspace()]
            end = whitespace_positions[0] if whitespace_positions else len(rest)
            value = rest[:end]
            next_rest = rest[end:]
        attrs[key] = value
        rest = next_rest.lstrip()
    return attrs


__all__ = [
    "GitActionDirective",
    "ParsedAssistantMarkdown",
    "RUST_MODULE",
    "parse_assistant_markdown",
    "parse_attributes",
    "parse_git_action",
    "strip_line_directives",
]
