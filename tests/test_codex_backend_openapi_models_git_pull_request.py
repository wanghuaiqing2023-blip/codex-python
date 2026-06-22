from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import GitPullRequest


def test_new_matches_rust_constructor_defaults() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/git_pull_request.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/git_pull_request.rs
    # Contract: GitPullRequest::new assigns required fields and omits optional fields.
    pr = GitPullRequest.new(12, "https://example.test/pulls/12", "open", False, True)

    assert pr.number == 12
    assert pr.url == "https://example.test/pulls/12"
    assert pr.state == "open"
    assert pr.merged is False
    assert pr.mergeable is True
    assert pr.draft is None
    assert pr.to_json_dict() == {
        "number": 12,
        "url": "https://example.test/pulls/12",
        "state": "open",
        "merged": False,
        "mergeable": True,
    }


def test_default_matches_derived_default() -> None:
    # Rust contract: derived Default zero/empty/false-initializes required fields.
    assert GitPullRequest() == GitPullRequest(0, "", "", False, False)


def test_from_mapping_uses_rust_serde_field_names_and_json_values() -> None:
    # Rust contract: serde names include base_sha/head_sha/merge_commit_sha and JSON value fields.
    pr = GitPullRequest.from_mapping(
        {
            "number": 7,
            "url": "url",
            "state": "closed",
            "merged": True,
            "mergeable": False,
            "draft": False,
            "title": "Title",
            "body": "Body",
            "base": "main",
            "head": "feature",
            "base_sha": "base-sha",
            "head_sha": "head-sha",
            "merge_commit_sha": "merge-sha",
            "comments": [{"body": "comment"}],
            "diff": {"patch": "..."},
            "user": {"login": "octo"},
        }
    )

    assert pr.to_json_dict() == {
        "number": 7,
        "url": "url",
        "state": "closed",
        "merged": True,
        "mergeable": False,
        "draft": False,
        "title": "Title",
        "body": "Body",
        "base": "main",
        "head": "feature",
        "base_sha": "base-sha",
        "head_sha": "head-sha",
        "merge_commit_sha": "merge-sha",
        "comments": [{"body": "comment"}],
        "diff": {"patch": "..."},
        "user": {"login": "octo"},
    }


def test_from_mapping_rejects_wrong_required_and_optional_types() -> None:
    # Rust serde contract: typed scalar fields must deserialize from matching JSON types.
    with pytest.raises(TypeError, match="expected integer"):
        GitPullRequest.from_mapping({"number": "7"})
    with pytest.raises(TypeError, match="expected bool"):
        GitPullRequest.from_mapping({"draft": "false"})
    with pytest.raises(TypeError, match="expected string"):
        GitPullRequest.from_mapping({"title": 123})
