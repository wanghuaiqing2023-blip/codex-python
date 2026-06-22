from pycodex.analytics import (
    AcceptedLineFingerprint,
    AcceptedLineFingerprintEventInput,
    AcceptedLineFingerprintSummary,
    accepted_line_fingerprint_event_requests,
    accepted_line_fingerprints_from_unified_diff,
    fingerprint_hash,
)


def test_parses_counts_and_effective_added_fingerprints() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/accepted_lines.rs
    # Rust test: parses_counts_and_effective_added_fingerprints
    # Contract: unified diff counts added/deleted lines and fingerprints effective added lines.
    diff = """\
diff --git a/src/lib.rs b/src/lib.rs
index 1111111..2222222
--- a/src/lib.rs
+++ b/src/lib.rs
@@ -1,3 +1,5 @@
-old line
+fn useful() {
+}
+    return user.id;
 context
"""

    summary = accepted_line_fingerprints_from_unified_diff(diff)

    assert summary == AcceptedLineFingerprintSummary(
        accepted_added_lines=3,
        accepted_deleted_lines=1,
        line_fingerprints=[
            AcceptedLineFingerprint(
                path_hash=fingerprint_hash("path", "src/lib.rs"),
                line_hash=fingerprint_hash("line", "fn useful() {"),
            ),
            AcceptedLineFingerprint(
                path_hash=fingerprint_hash("path", "src/lib.rs"),
                line_hash=fingerprint_hash("line", "return user.id;"),
            ),
        ],
    )


def test_skips_added_file_metadata_headers() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/accepted_lines.rs
    # Rust test: skips_added_file_metadata_headers
    # Contract: /dev/null metadata is not fingerprinted as a path, but hunk additions are.
    diff = """\
diff --git a/new.py b/new.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/new.py
@@ -0,0 +1 @@
+print('hello')
"""

    summary = accepted_line_fingerprints_from_unified_diff(diff)

    assert summary.accepted_added_lines == 1
    assert summary.accepted_deleted_lines == 0
    assert len(summary.line_fingerprints) == 1


def test_parses_hunk_lines_that_look_like_file_headers() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/accepted_lines.rs
    # Rust test: parses_hunk_lines_that_look_like_file_headers
    # Contract: ---/+++ inside a hunk are content lines, not file metadata.
    diff = """\
diff --git a/src/lib.rs b/src/lib.rs
index 1111111..2222222
--- a/src/lib.rs
+++ b/src/lib.rs
@@ -1,2 +1,2 @@
--- old value
+++ new value
"""

    summary = accepted_line_fingerprints_from_unified_diff(diff)

    assert summary == AcceptedLineFingerprintSummary(
        accepted_added_lines=1,
        accepted_deleted_lines=1,
        line_fingerprints=[
            AcceptedLineFingerprint(
                path_hash=fingerprint_hash("path", "src/lib.rs"),
                line_hash=fingerprint_hash("line", "++ new value"),
            )
        ],
    )


def test_accepted_line_fingerprints_event_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/accepted_lines.rs + src/events.rs
    # Rust test: analytics_client_tests::accepted_line_fingerprints_event_serializes_expected_shape
    # Contract: accepted-line event payload omits computed fingerprints from upload.
    payload = accepted_line_fingerprint_event_requests(
        AcceptedLineFingerprintEventInput(
            event_type="codex.accepted_line_fingerprints",
            turn_id="turn-1",
            thread_id="thread-1",
            product_surface="codex",
            model_slug="gpt-5.1-codex",
            completed_at=1710000000,
            repo_hash="repo-hash-1",
            accepted_added_lines=42,
            accepted_deleted_lines=40,
            line_fingerprints=[
                AcceptedLineFingerprint(
                    path_hash=fingerprint_hash("path", "src/lib.rs"),
                    line_hash=fingerprint_hash("line", "fn useful() {"),
                )
            ],
        )
    )[0]

    assert payload == {
        "event_type": "codex_accepted_line_fingerprints",
        "event_params": {
            "event_type": "codex.accepted_line_fingerprints",
            "turn_id": "turn-1",
            "thread_id": "thread-1",
            "product_surface": "codex",
            "model_slug": "gpt-5.1-codex",
            "completed_at": 1710000000,
            "repo_hash": "repo-hash-1",
            "accepted_added_lines": 42,
            "accepted_deleted_lines": 40,
            "line_fingerprints": [],
        },
    }
