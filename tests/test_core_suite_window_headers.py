from pycodex.core import ModelClient, X_CODEX_WINDOW_ID_HEADER


def _window_id_parts(headers: dict[str, str]) -> tuple[str, int]:
    window_id = headers[X_CODEX_WINDOW_ID_HEADER]
    thread_id, generation = window_id.rsplit(":", 1)
    return thread_id, int(generation)


def test_window_id_advances_after_compact_persists_on_resume_and_resets_on_fork() -> None:
    # Rust: core/tests/suite/window_headers.rs::window_id_advances_after_compact_persists_on_resume_and_resets_on_fork.
    initial = ModelClient(session_id="session-1", thread_id="thread-initial", installation_id="install")

    before_compact = initial.build_responses_identity_headers()
    compact_request = initial.build_responses_identity_headers()
    initial.advance_window_generation()
    after_compact = initial.build_responses_identity_headers()

    resumed = ModelClient(session_id="session-2", thread_id="thread-initial", installation_id="install")
    resumed.set_window_generation(1)
    after_resume = resumed.build_responses_identity_headers()

    forked = ModelClient(session_id="session-3", thread_id="thread-forked", installation_id="install")
    after_fork = forked.build_responses_identity_headers()

    initial_thread_id, first_generation = _window_id_parts(before_compact)
    compact_thread_id, compact_generation = _window_id_parts(compact_request)
    after_compact_thread_id, after_compact_generation = _window_id_parts(after_compact)
    after_resume_thread_id, after_resume_generation = _window_id_parts(after_resume)
    after_fork_thread_id, after_fork_generation = _window_id_parts(after_fork)

    assert first_generation == 0
    assert compact_thread_id == initial_thread_id
    assert compact_generation == 0
    assert after_compact_thread_id == initial_thread_id
    assert after_compact_generation == 1
    assert after_resume_thread_id == initial_thread_id
    assert after_resume_generation == 1
    assert after_fork_thread_id != initial_thread_id
    assert after_fork_generation == 0
