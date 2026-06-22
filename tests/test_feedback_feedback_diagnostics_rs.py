"""Parity tests for Rust ``codex-feedback/src/feedback_diagnostics.rs``."""

from pycodex.feedback.feedback_diagnostics import (
    PROXY_DIAGNOSTIC_HEADLINE,
    FeedbackDiagnostic,
    FeedbackDiagnostics,
)


def test_collect_from_pairs_reports_raw_values_and_attachment() -> None:
    """Rust: collect_from_pairs_reports_raw_values_and_attachment."""

    diagnostics = FeedbackDiagnostics.collect_from_pairs(
        [
            (
                "HTTPS_PROXY",
                "https://user:password@secure-proxy.example.com:443?secret=1",
            ),
            ("http_proxy", "proxy.example.com:8080"),
            ("all_proxy", "socks5h://all-proxy.example.com:1080"),
        ]
    )

    assert diagnostics == FeedbackDiagnostics(
        [
            FeedbackDiagnostic(
                headline=PROXY_DIAGNOSTIC_HEADLINE,
                details=[
                    "http_proxy = proxy.example.com:8080",
                    "HTTPS_PROXY = https://user:password@secure-proxy.example.com:443?secret=1",
                    "all_proxy = socks5h://all-proxy.example.com:1080",
                ],
            )
        ]
    )
    assert (
        diagnostics.attachment_text()
        == "Connectivity diagnostics\n"
        "\n"
        "- Proxy environment variables are set and may affect connectivity.\n"
        "  - http_proxy = proxy.example.com:8080\n"
        "  - HTTPS_PROXY = https://user:password@secure-proxy.example.com:443?secret=1\n"
        "  - all_proxy = socks5h://all-proxy.example.com:1080"
    )


def test_collect_from_pairs_ignores_absent_values() -> None:
    """Rust: collect_from_pairs_ignores_absent_values."""

    diagnostics = FeedbackDiagnostics.collect_from_pairs([])
    assert diagnostics == FeedbackDiagnostics()
    assert diagnostics.is_empty()
    assert diagnostics.attachment_text() is None


def test_collect_from_pairs_preserves_whitespace_and_empty_values() -> None:
    """Rust: collect_from_pairs_preserves_whitespace_and_empty_values."""

    diagnostics = FeedbackDiagnostics.collect_from_pairs([("HTTP_PROXY", "  proxy with spaces  ")])

    assert diagnostics == FeedbackDiagnostics(
        [
            FeedbackDiagnostic(
                headline=PROXY_DIAGNOSTIC_HEADLINE,
                details=["HTTP_PROXY =   proxy with spaces  "],
            )
        ]
    )


def test_collect_from_pairs_reports_values_verbatim() -> None:
    """Rust: collect_from_pairs_reports_values_verbatim."""

    diagnostics = FeedbackDiagnostics.collect_from_pairs([("HTTP_PROXY", "not a valid proxy")])

    assert diagnostics == FeedbackDiagnostics(
        [
            FeedbackDiagnostic(
                headline=PROXY_DIAGNOSTIC_HEADLINE,
                details=["HTTP_PROXY = not a valid proxy"],
            )
        ]
    )

