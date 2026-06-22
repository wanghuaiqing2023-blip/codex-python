from pycodex.app_server.filters import (
    SourceFiltersProjection,
    compute_source_filters,
    source_kind_matches,
)
from pycodex.app_server_protocol import ThreadSourceKind
from pycodex.core.rollout import INTERACTIVE_SESSION_SOURCES
from pycodex.protocol import SessionSource, SubAgentSource, ThreadId


def test_compute_source_filters_defaults_to_interactive_sources() -> None:
    # Rust: filters.rs::tests::compute_source_filters_defaults_to_interactive_sources.
    projection = compute_source_filters(None)

    assert projection == SourceFiltersProjection(tuple(INTERACTIVE_SESSION_SOURCES), None)


def test_compute_source_filters_empty_means_interactive_sources() -> None:
    # Rust: filters.rs::tests::compute_source_filters_empty_means_interactive_sources.
    projection = compute_source_filters(())

    assert projection == SourceFiltersProjection(tuple(INTERACTIVE_SESSION_SOURCES), None)


def test_compute_source_filters_interactive_only_skips_post_filtering() -> None:
    # Rust: filters.rs::tests::compute_source_filters_interactive_only_skips_post_filtering.
    source_kinds = (ThreadSourceKind.CLI, ThreadSourceKind.VSCODE)
    projection = compute_source_filters(source_kinds)

    assert projection == SourceFiltersProjection(
        (SessionSource.cli(), SessionSource.vscode()),
        source_kinds,
    )


def test_compute_source_filters_subagent_variant_requires_post_filtering() -> None:
    # Rust: filters.rs::tests::compute_source_filters_subagent_variant_requires_post_filtering.
    source_kinds = (ThreadSourceKind.SUB_AGENT_REVIEW,)
    projection = compute_source_filters(source_kinds)

    assert projection == SourceFiltersProjection((), source_kinds)


def test_source_kind_matches_distinguishes_subagent_variants() -> None:
    # Rust: filters.rs::tests::source_kind_matches_distinguishes_subagent_variants.
    parent_thread_id = ThreadId.from_string("00000000-0000-4000-8000-000000000001")
    review = SessionSource.subagent(SubAgentSource.review())
    spawn = SessionSource.subagent(SubAgentSource.thread_spawn(parent_thread_id, depth=1))

    assert source_kind_matches(review, (ThreadSourceKind.SUB_AGENT_REVIEW,))
    assert not source_kind_matches(review, (ThreadSourceKind.SUB_AGENT_THREAD_SPAWN,))
    assert source_kind_matches(spawn, (ThreadSourceKind.SUB_AGENT_THREAD_SPAWN,))
    assert not source_kind_matches(spawn, (ThreadSourceKind.SUB_AGENT_REVIEW,))


def test_source_kind_matches_app_server_unknown_and_generic_subagent() -> None:
    assert source_kind_matches(SessionSource.mcp(), (ThreadSourceKind.APP_SERVER,))
    assert source_kind_matches(SessionSource.unknown(), (ThreadSourceKind.UNKNOWN,))
    assert source_kind_matches(
        SessionSource.subagent(SubAgentSource.other_source("custom")),
        (ThreadSourceKind.SUB_AGENT, ThreadSourceKind.SUB_AGENT_OTHER),
    )
