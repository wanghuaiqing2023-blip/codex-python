"""Port of Rust ``codex-backend-openapi-models::models::external_pull_request_response``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/external_pull_request_response.rs``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .git_pull_request import GitPullRequest


@dataclass(frozen=True)
class ExternalPullRequestResponse:
    id: str = ""
    assistant_turn_id: str = ""
    pull_request: GitPullRequest = field(default_factory=GitPullRequest)
    codex_updated_sha: str | None = None

    @classmethod
    def new(
        cls,
        id: str,
        assistant_turn_id: str,
        pull_request: GitPullRequest,
    ) -> "ExternalPullRequestResponse":
        return cls(
            id=id,
            assistant_turn_id=assistant_turn_id,
            pull_request=pull_request,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExternalPullRequestResponse":
        return cls(
            id=_expect_str(value.get("id", "")),
            assistant_turn_id=_expect_str(value.get("assistant_turn_id", "")),
            pull_request=_decode_pull_request(value.get("pull_request", {})),
            codex_updated_sha=_optional_str(value.get("codex_updated_sha")),
        )

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "assistant_turn_id": self.assistant_turn_id,
            "pull_request": self.pull_request.to_json_dict(),
        }
        if self.codex_updated_sha is not None:
            result["codex_updated_sha"] = self.codex_updated_sha
        return result


def _decode_pull_request(value: Any) -> GitPullRequest:
    if isinstance(value, GitPullRequest):
        return value
    if isinstance(value, Mapping):
        return GitPullRequest.from_mapping(value)
    raise TypeError("expected pull_request mapping")


def _expect_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return _expect_str(value)


__all__ = ["ExternalPullRequestResponse"]
