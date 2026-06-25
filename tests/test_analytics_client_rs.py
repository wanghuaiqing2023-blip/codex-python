import http.server
import json
import threading

from pycodex.analytics import (
    AnalyticsEventsClient,
    accepted_line_fingerprint_event_requests,
    AcceptedLineFingerprintEventInput,
    analytics_relevant_client_request,
    analytics_relevant_client_response,
    send_track_events,
    should_send_in_isolated_request,
    track_event_request_batches,
)


class _CodexBackendAuth:
    def uses_codex_backend(self) -> bool:
        return True

    def to_auth_headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer analytics-token"}


def regular_event(thread_id: str) -> dict:
    return {"event_type": "codex_regular_event", "event_params": {"thread_id": thread_id}}


def accepted_line_event(thread_id: str) -> dict:
    return accepted_line_fingerprint_event_requests(
        AcceptedLineFingerprintEventInput(
            event_type="codex.accepted_line_fingerprints",
            turn_id="turn-1",
            thread_id=thread_id,
            product_surface=None,
            model_slug=None,
            completed_at=1,
            repo_hash=None,
            accepted_added_lines=1,
            accepted_deleted_lines=0,
            line_fingerprints=[],
        )
    )[0]


def test_track_request_only_enqueues_analytics_relevant_requests() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/client.rs
    # Rust test: client_tests::track_request_only_enqueues_analytics_relevant_requests
    # Contract: only TurnStart and TurnSteer client requests are analytics facts.
    client = AnalyticsEventsClient()
    client.track_request(7, 1, "TurnStart")
    client.track_request(7, 2, "TurnSteer")
    client.track_request(7, 3, "ThreadArchive")

    assert analytics_relevant_client_request("TurnStart") is True
    assert analytics_relevant_client_request("TurnSteer") is True
    assert analytics_relevant_client_request("ThreadArchive") is False
    assert [fact["request_kind"] for fact in client.recorded_facts] == ["TurnStart", "TurnSteer"]


def test_track_response_only_enqueues_analytics_relevant_responses() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/client.rs
    # Rust test: client_tests::track_response_only_enqueues_analytics_relevant_responses
    # Contract: only thread start/resume/fork and turn start/steer responses are analytics facts.
    client = AnalyticsEventsClient()
    for index, kind in enumerate(("ThreadStart", "ThreadResume", "ThreadFork", "TurnStart", "TurnSteer"), 1):
        client.track_response(7, index, kind)
    client.track_response(7, 6, "ThreadArchive")

    assert analytics_relevant_client_response("ThreadStart") is True
    assert analytics_relevant_client_response("ThreadArchive") is False
    assert [fact["response_kind"] for fact in client.recorded_facts] == [
        "ThreadStart",
        "ThreadResume",
        "ThreadFork",
        "TurnStart",
        "TurnSteer",
    ]


def test_track_event_request_batches_only_isolates_accepted_line_fingerprint_events() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/client.rs
    # Rust test: client_tests::track_event_request_batches_only_isolates_accepted_line_fingerprint_events
    # Contract: accepted-line fingerprint events are isolated from regular analytics batches.
    batches = track_event_request_batches(
        [
            regular_event("thread-1"),
            regular_event("thread-2"),
            accepted_line_event("thread-3"),
            accepted_line_event("thread-4"),
            regular_event("thread-5"),
            regular_event("thread-6"),
        ]
    )

    assert [len(batch) for batch in batches] == [2, 1, 1, 2]
    assert should_send_in_isolated_request(batches[1][0]) is True
    assert should_send_in_isolated_request(batches[2][0]) is True


def test_send_track_events_posts_batches_with_auth_to_codex_backend() -> None:
    # Source: rust_contract
    # Rust crate: codex-analytics
    # Rust module: src/client.rs
    # Anchors: send_track_events, send_track_events_request,
    # track_event_request_batches.
    # Contract: Rust sends only for Codex-backend auth, trims base-url trailing
    # slashes, posts JSON to /codex/analytics-events/events with auth headers,
    # and preserves accepted-line isolated batching.
    captured: list[dict[str, object]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("content-length", "0")))
            captured.append(
                {
                    "path": self.path,
                    "authorization": self.headers.get("authorization"),
                    "content_type": self.headers.get("content-type"),
                    "body": json.loads(body.decode("utf-8")),
                }
            )
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, _format: str, *args: object) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threads: list[threading.Thread] = []
    try:
        for _ in range(3):
            thread = threading.Thread(target=server.handle_request)
            thread.start()
            threads.append(thread)

        statuses = send_track_events(
            _CodexBackendAuth(),
            f"http://127.0.0.1:{server.server_port}/",
            [
                regular_event("thread-1"),
                regular_event("thread-2"),
                accepted_line_event("thread-3"),
                regular_event("thread-4"),
            ],
        )

        for thread in threads:
            thread.join(timeout=2)

        assert statuses == [204, 204, 204]
        assert [request["path"] for request in captured] == [
            "/codex/analytics-events/events",
            "/codex/analytics-events/events",
            "/codex/analytics-events/events",
        ]
        assert all(request["authorization"] == "Bearer analytics-token" for request in captured)
        assert all(str(request["content_type"]).startswith("application/json") for request in captured)
        assert [len(request["body"]["events"]) for request in captured] == [2, 1, 1]
        assert captured[1]["body"]["events"][0]["event_type"] == "codex_accepted_line_fingerprints"
    finally:
        server.server_close()
        for thread in threads:
            thread.join(timeout=2)


def test_send_track_events_skips_without_codex_backend_auth() -> None:
    # Source: rust_contract
    # Rust crate: codex-analytics
    # Rust module: src/client.rs
    # Anchor: send_track_events.
    # Contract: Rust returns before sending when auth is absent or not a Codex
    # backend auth mode.
    assert send_track_events(None, "http://127.0.0.1:9", [regular_event("thread")]) == []
    assert (
        send_track_events(
            {"uses_codex_backend": False, "headers": {"Authorization": "Bearer no-send"}},
            "http://127.0.0.1:9",
            [regular_event("thread")],
        )
        == []
    )
