"""Rust parity tests for ``request_processors/git_processor.rs``."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from pycodex.app_server.request_processors_git_processor import GitRequestProcessor, GitRequestProcessorError
from pycodex.app_server_protocol import GitDiffToRemoteParams, GitDiffToRemoteResponse


@dataclass(frozen=True)
class DiffToRemote:
    sha: str
    diff: str


def test_git_request_processor_new_is_stateless() -> None:
    # Rust: GitRequestProcessor::new() returns Self.
    assert isinstance(GitRequestProcessor.new(), GitRequestProcessor)


def test_git_diff_to_remote_projects_sha_and_diff_response() -> None:
    # Rust: git_diff_to_origin maps git_diff_to_remote result to response sha/diff.
    calls: list[Path] = []

    def diff_to_remote(cwd: Path) -> DiffToRemote:
        calls.append(cwd)
        return DiffToRemote(sha="abc123", diff="diff --git a/file b/file\n")

    processor = GitRequestProcessor(diff_to_remote)

    response = processor.git_diff_to_remote(GitDiffToRemoteParams("repo"))

    assert calls == [Path("repo")]
    assert response == GitDiffToRemoteResponse(sha="abc123", diff="diff --git a/file b/file\n")


def test_git_diff_to_remote_accepts_mapping_params() -> None:
    processor = GitRequestProcessor(lambda cwd: {"sha": "def456", "diff": "diff body"})

    response = processor.git_diff_to_remote({"cwd": "repo"})

    assert response == GitDiffToRemoteResponse(sha="def456", diff="diff body")


def test_git_diff_to_remote_maps_absent_diff_to_invalid_request() -> None:
    # Rust: None becomes invalid_request("failed to compute git diff to remote for cwd: {cwd:?}").
    processor = GitRequestProcessor(lambda cwd: None)

    with pytest.raises(GitRequestProcessorError) as caught:
        processor.git_diff_to_origin(Path("missing repo"))

    assert caught.value.error.code == -32600
    assert caught.value.error.message == 'failed to compute git diff to remote for cwd: "missing repo"'
    assert caught.value.error.data is None
