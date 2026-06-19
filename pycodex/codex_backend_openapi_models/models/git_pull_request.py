"""Port of Rust ``codex-backend-openapi-models::models::git_pull_request``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/git_pull_request.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class GitPullRequest:
    number: int = 0
    url: str = ""
    state: str = ""
    merged: bool = False
    mergeable: bool = False
    draft: bool | None = None
    title: str | None = None
    body: str | None = None
    base: str | None = None
    head: str | None = None
    base_sha: str | None = None
    head_sha: str | None = None
    merge_commit_sha: str | None = None
    comments: Any | None = None
    diff: Any | None = None
    user: Any | None = None

    @classmethod
    def new(
        cls,
        number: int,
        url: str,
        state: str,
        merged: bool,
        mergeable: bool,
    ) -> "GitPullRequest":
        return cls(
            number=number,
            url=url,
            state=state,
            merged=merged,
            mergeable=mergeable,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GitPullRequest":
        return cls(
            number=_expect_int(value.get("number", 0)),
            url=_expect_str(value.get("url", "")),
            state=_expect_str(value.get("state", "")),
            merged=_expect_bool(value.get("merged", False)),
            mergeable=_expect_bool(value.get("mergeable", False)),
            draft=_optional_bool(value.get("draft")),
            title=_optional_str(value.get("title")),
            body=_optional_str(value.get("body")),
            base=_optional_str(value.get("base")),
            head=_optional_str(value.get("head")),
            base_sha=_optional_str(value.get("base_sha")),
            head_sha=_optional_str(value.get("head_sha")),
            merge_commit_sha=_optional_str(value.get("merge_commit_sha")),
            comments=value.get("comments"),
            diff=value.get("diff"),
            user=value.get("user"),
        )

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "number": self.number,
            "url": self.url,
            "state": self.state,
            "merged": self.merged,
            "mergeable": self.mergeable,
        }
        _put_optional(result, "draft", self.draft)
        _put_optional(result, "title", self.title)
        _put_optional(result, "body", self.body)
        _put_optional(result, "base", self.base)
        _put_optional(result, "head", self.head)
        _put_optional(result, "base_sha", self.base_sha)
        _put_optional(result, "head_sha", self.head_sha)
        _put_optional(result, "merge_commit_sha", self.merge_commit_sha)
        _put_optional(result, "comments", self.comments)
        _put_optional(result, "diff", self.diff)
        _put_optional(result, "user", self.user)
        return result


def _put_optional(result: dict[str, Any], key: str, value: Any | None) -> None:
    if value is not None:
        result[key] = value


def _expect_int(value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError("expected integer")
    if isinstance(value, int):
        return value
    raise TypeError("expected integer")


def _expect_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise TypeError("expected bool")


def _expect_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string")


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return _expect_bool(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return _expect_str(value)


__all__ = ["GitPullRequest"]
