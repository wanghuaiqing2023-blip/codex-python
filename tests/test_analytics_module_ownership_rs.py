import importlib


def test_analytics_items_are_owned_by_rust_aligned_modules() -> None:
    """Rust source: codex-analytics/src/lib.rs and its five child modules."""
    accepted_lines = importlib.import_module("pycodex.analytics.accepted_lines")
    client = importlib.import_module("pycodex.analytics.client")
    events = importlib.import_module("pycodex.analytics.events")
    facts = importlib.import_module("pycodex.analytics.facts")
    reducer = importlib.import_module("pycodex.analytics.reducer")

    assert accepted_lines.accepted_line_fingerprints_from_unified_diff.__module__ == (
        "pycodex.analytics.accepted_lines"
    )
    assert client.AnalyticsEventsClient.__module__ == "pycodex.analytics.client"
    assert events.AppServerRpcTransport.__module__ == "pycodex.analytics.events"
    assert facts.AcceptedLineFingerprint.__module__ == "pycodex.analytics.facts"
    assert reducer.AnalyticsReducer.__module__ == "pycodex.analytics.reducer"


def test_analytics_crate_root_reexports_rust_public_items() -> None:
    """Rust source: codex-analytics/src/lib.rs public use declarations."""
    analytics = importlib.import_module("pycodex.analytics")
    accepted_lines = importlib.import_module("pycodex.analytics.accepted_lines")
    client = importlib.import_module("pycodex.analytics.client")
    events = importlib.import_module("pycodex.analytics.events")
    facts = importlib.import_module("pycodex.analytics.facts")

    assert (
        analytics.accepted_line_fingerprints_from_unified_diff
        is accepted_lines.accepted_line_fingerprints_from_unified_diff
    )
    assert analytics.AnalyticsEventsClient is client.AnalyticsEventsClient
    assert analytics.AppServerRpcTransport is events.AppServerRpcTransport
    assert analytics.AcceptedLineFingerprint is facts.AcceptedLineFingerprint
