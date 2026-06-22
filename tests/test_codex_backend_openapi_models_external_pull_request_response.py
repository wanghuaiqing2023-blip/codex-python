from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import (
    ExternalPullRequestResponse,
    GitPullRequest,
)


def test_new_matches_rust_constructor_defaults() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/external_pull_request_response.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/external_pull_request_response.rs
    # Contract: ExternalPullRequestResponse::new assigns required fields and leaves codex_updated_sha unset.
    pr = GitPullRequest.new(12, "https://example.test/pulls/12", "open", False, True)
    response = ExternalPullRequestResponse.new("response-id", "turn-id", pr)

    assert response.id == "response-id"
    assert response.assistant_turn_id == "turn-id"
    assert response.pull_request == pr
    assert response.codex_updated_sha is None
    assert response.to_json_dict() == {
        "id": "response-id",
        "assistant_turn_id": "turn-id",
        "pull_request": {
            "number": 12,
            "url": "https://example.test/pulls/12",
            "state": "open",
            "merged": False,
            "mergeable": True,
        },
    }


def test_default_matches_derived_default() -> None:
    # Rust contract: derived Default initializes strings empty, pull_request default, and optional SHA to None.
    assert ExternalPullRequestResponse() == ExternalPullRequestResponse(
        "",
        "",
        GitPullRequest(),
        None,
    )


def test_from_mapping_uses_rust_serde_field_names() -> None:
    # Rust contract: serde names are id, assistant_turn_id, pull_request, and codex_updated_sha.
    response = ExternalPullRequestResponse.from_mapping(
        {
            "id": "response-id",
            "assistant_turn_id": "turn-id",
            "pull_request": {
                "number": 7,
                "url": "url",
                "state": "closed",
                "merged": True,
                "mergeable": False,
            },
            "codex_updated_sha": "updated-sha",
        }
    )

    assert response.to_json_dict() == {
        "id": "response-id",
        "assistant_turn_id": "turn-id",
        "pull_request": {
            "number": 7,
            "url": "url",
            "state": "closed",
            "merged": True,
            "mergeable": False,
        },
        "codex_updated_sha": "updated-sha",
    }


def test_from_mapping_rejects_wrong_field_types() -> None:
    # Rust serde contract: typed string fields and nested pull_request must deserialize from matching JSON types.
    with pytest.raises(TypeError, match="expected string"):
        ExternalPullRequestResponse.from_mapping({"id": 123})
    with pytest.raises(TypeError, match="expected string"):
        ExternalPullRequestResponse.from_mapping({"codex_updated_sha": 123})
    with pytest.raises(TypeError, match="expected pull_request mapping"):
        ExternalPullRequestResponse.from_mapping({"pull_request": "not-a-mapping"})
