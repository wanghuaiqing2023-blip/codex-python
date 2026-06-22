from __future__ import annotations

from pycodex.codex_backend_openapi_models import models


def test_models_namespace_matches_rust_curated_exports() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/mod.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/mod.rs
    # Contract: models::mod exposes the curated public model list used by the workspace.
    expected_exports = [
        "ConfigFileResponse",
        "CodeTaskDetailsResponse",
        "TaskResponse",
        "ExternalPullRequestResponse",
        "GitPullRequest",
        "TaskListItem",
        "PaginatedListTaskListItem",
        "AdditionalRateLimitDetails",
        "PlanType",
        "RateLimitReachedKind",
        "RateLimitReachedType",
        "RateLimitStatusPayload",
        "RateLimitStatusDetails",
        "RateLimitWindowSnapshot",
        "CreditStatusDetails",
    ]

    for export in expected_exports:
        assert export in models.__all__
        assert getattr(models, export) is not None


def test_models_namespace_keeps_python_helpers_private_to_python() -> None:
    # Python-only helper exports support local double-option modeling and are
    # documented as package implementation details rather than Rust model types.
    assert "UNSET" in models.__all__
    assert "Unset" in models.__all__
