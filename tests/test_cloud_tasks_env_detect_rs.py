import json
import subprocess

import pytest

from pycodex.cloud_tasks import (
    CloudTasksHttpResponse,
    CodeEnvironment,
    EnvironmentRow,
    autodetect_environment_id,
    by_repo_environments_url,
    environment_list_url,
    get_git_origins,
    get_json,
    list_environments,
    parse_owner_repo,
    pick_environment_row,
    uniq,
)
from pycodex.cloud_tasks.app import EnvironmentRow as AppEnvironmentRow


BASE = "https://chatgpt.com/backend-api"
PUBLIC_BASE = "https://chatgpt.com"


def response(items, *, status=200, content_type="application/json"):
    body = items if isinstance(items, str) else json.dumps(items)
    return CloudTasksHttpResponse(status=status, body=body, content_type=content_type)


def test_parse_owner_repo_matches_github_origin_variants():
    # Rust crate/module: codex-cloud-tasks/src/env_detect.rs::parse_owner_repo
    # Contract: accept GitHub SSH scp-style origins with any user and common HTTP/git prefixes.
    assert parse_owner_repo("git@github.com:openai/codex.git") == ("openai", "codex")
    assert parse_owner_repo("org-123@github.com:openai/codex.git") == (
        "openai",
        "codex",
    )
    assert parse_owner_repo("ssh://git@github.com:openai/codex.git") == (
        "openai",
        "codex",
    )
    assert parse_owner_repo("https://github.com/openai/codex.git") == (
        "openai",
        "codex",
    )
    assert parse_owner_repo("http://github.com/openai/codex") == ("openai", "codex")
    assert parse_owner_repo("git://github.com/openai/codex.git") == (
        "openai",
        "codex",
    )
    assert parse_owner_repo("github.com/openai/codex.git") == ("openai", "codex")
    assert parse_owner_repo("ssh://git@github.com/openai/codex.git") is None
    assert parse_owner_repo("https://gitlab.com/openai/codex.git") is None
    assert parse_owner_repo("https://github.com/openai") is None


def test_urls_match_backend_api_and_public_paths():
    # Rust crate/module: codex-cloud-tasks/src/env_detect.rs URL construction.
    assert environment_list_url(BASE) == "https://chatgpt.com/backend-api/wham/environments"
    assert (
        by_repo_environments_url(BASE, "openai", "codex")
        == "https://chatgpt.com/backend-api/wham/environments/by-repo/github/openai/codex"
    )
    assert environment_list_url(PUBLIC_BASE) == "https://chatgpt.com/api/codex/environments"
    assert (
        by_repo_environments_url(PUBLIC_BASE, "openai", "codex")
        == "https://chatgpt.com/api/codex/environments/by-repo/github/openai/codex"
    )


def test_uniq_sorts_and_deduplicates_like_rust_vec_sort_dedup():
    # Rust crate/module: codex-cloud-tasks/src/env_detect.rs::uniq.
    assert uniq(["b", "a", "b", "c", "a"]) == ["a", "b", "c"]


def test_get_git_origins_prefers_config_then_falls_back_to_remote_v():
    # Rust crate/module: codex-cloud-tasks/src/env_detect.rs::get_git_origins.
    calls = []

    def config_runner(args):
        calls.append(tuple(args))
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=(
                "remote.origin.url https://github.com/openai/codex.git\n"
                "remote.upstream.url git@github.com:openai/codex.git\n"
            ),
            stderr="",
        )

    assert get_git_origins(config_runner) == [
        "git@github.com:openai/codex.git",
        "https://github.com/openai/codex.git",
    ]
    assert calls == [("git", "config", "--get-regexp", r"remote\..*\.url")]

    def fallback_runner(args):
        if args[1] == "config":
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=(
                "origin https://github.com/openai/codex.git (fetch)\n"
                "origin https://github.com/openai/codex.git (push)\n"
                "upstream git@github.com:openai/codex.git (fetch)\n"
            ),
            stderr="",
        )

    assert get_git_origins(fallback_runner) == [
        "git@github.com:openai/codex.git",
        "https://github.com/openai/codex.git",
    ]


def test_pick_environment_row_label_single_pinned_and_task_count_tie_order():
    # Rust crate/module: codex-cloud-tasks/src/env_detect.rs::pick_environment_row.
    envs = [
        CodeEnvironment("first", label="Prod", task_count=20),
        CodeEnvironment("pinned", label="Pinned", is_pinned=True, task_count=0),
        CodeEnvironment("last-max", label="Prod", task_count=20),
    ]
    assert pick_environment_row(envs, "prod").id == "first"
    assert pick_environment_row([CodeEnvironment("only")]).id == "only"
    assert pick_environment_row(envs).id == "pinned"

    unpinned = [
        CodeEnvironment("first", task_count=7),
        CodeEnvironment("middle", task_count=4),
        CodeEnvironment("last", task_count=7),
    ]
    assert pick_environment_row(unpinned).id == "last"
    assert pick_environment_row([]) is None


def test_get_json_reports_rust_shaped_status_and_decode_errors():
    # Rust crate/module: codex-cloud-tasks/src/env_detect.rs::get_json.
    with pytest.raises(RuntimeError) as status_error:
        get_json(
            "https://example.invalid/envs",
            {},
            transport=lambda _url, _headers: response(
                "nope", status=500, content_type="text/plain"
            ),
        )
    assert str(status_error.value) == (
        "GET https://example.invalid/envs failed: 500; "
        "content-type=text/plain; body=nope"
    )

    with pytest.raises(RuntimeError) as decode_error:
        get_json(
            "https://example.invalid/envs",
            {},
            transport=lambda _url, _headers: response("{", content_type="application/json"),
        )
    assert str(decode_error.value).startswith(
        "Decode error for https://example.invalid/envs:"
    )
    assert "content-type=application/json; body={" in str(decode_error.value)


def test_autodetect_prefers_by_repo_then_global_and_ignores_by_repo_failures():
    # Rust crate/module: codex-cloud-tasks/src/env_detect.rs::autodetect_environment_id.
    seen = []

    def transport(url, headers):
        seen.append((url, dict(headers)))
        if url.endswith("/openai/codex"):
            return response(
                [
                    {"id": "repo-1", "label": "Repo One", "task_count": 1},
                    {"id": "repo-2", "label": "Desired", "task_count": 0},
                ]
            )
        if url.endswith("/other/repo"):
            return response("bad", status=503, content_type="text/plain")
        return response([{"id": "global", "label": "Global"}])

    selected = autodetect_environment_id(
        BASE,
        {"authorization": "Bearer token"},
        "desired",
        origins=[
            "https://github.com/other/repo.git",
            "https://github.com/openai/codex.git",
        ],
        transport=transport,
    )

    assert selected.id == "repo-2"
    assert selected.label == "Desired"
    assert [url for url, _headers in seen] == [
        "https://chatgpt.com/backend-api/wham/environments/by-repo/github/other/repo",
        "https://chatgpt.com/backend-api/wham/environments/by-repo/github/openai/codex",
    ]
    assert all(headers == {"authorization": "Bearer token"} for _url, headers in seen)


def test_autodetect_global_fallback_and_empty_error():
    # Rust crate/module: codex-cloud-tasks/src/env_detect.rs::autodetect_environment_id.
    selected = autodetect_environment_id(
        PUBLIC_BASE,
        {},
        origins=["https://example.com/not-github.git"],
        transport=lambda url, _headers: response(
            [{"id": "global", "label": "Global", "is_pinned": True}]
            if url.endswith("/environments")
            else []
        ),
    )
    assert selected.id == "global"
    assert selected.label == "Global"

    with pytest.raises(RuntimeError, match="^no environments available$"):
        autodetect_environment_id(
            PUBLIC_BASE,
            {},
            origins=[],
            transport=lambda _url, _headers: response([]),
        )


def test_list_environments_merges_sources_and_sorts_like_rust_rows():
    # Rust crate/module: codex-cloud-tasks/src/env_detect.rs::list_environments.
    def transport(url, _headers):
        if url.endswith("/openai/codex"):
            return response(
                [
                    {"id": "shared", "label": None, "is_pinned": False},
                    {"id": "repo-only", "label": "beta", "task_count": 1},
                ]
            )
        if url.endswith("/other/repo"):
            return response(
                [
                    {"id": "alpha", "label": "Alpha", "is_pinned": True},
                    {"id": "shared", "label": "Shared", "is_pinned": True},
                ]
            )
        return response(
            [
                {"id": "global", "label": "aardvark"},
                {"id": "shared", "label": "Global Shared", "is_pinned": False},
            ]
        )

    rows = list_environments(
        BASE,
        {},
        origins=[
            "https://github.com/openai/codex.git",
            "git@github.com:other/repo.git",
        ],
        transport=transport,
    )

    assert [(row.id, row.label, row.is_pinned, row.repo_hints) for row in rows] == [
        ("alpha", "Alpha", True, "other/repo"),
        ("shared", "Shared", True, "openai/codex"),
        ("global", "aardvark", False, None),
        ("repo-only", "beta", False, "openai/codex"),
    ]


def test_environment_row_is_app_module_type():
    # Rust crate/module: codex-cloud-tasks/src/app.rs::EnvironmentRow.
    # Source contract: EnvironmentRow is an app.rs model re-exported by the crate surface.
    assert EnvironmentRow is AppEnvironmentRow

    rows = list_environments(
        BASE,
        {},
        origins=[],
        transport=lambda _url, _headers: response(
            [{"id": "global", "label": "Global", "is_pinned": True}]
        ),
    )

    assert rows == [AppEnvironmentRow("global", "Global", True, None)]
    assert all(type(row) is AppEnvironmentRow for row in rows)


def test_list_environments_uses_by_repo_when_global_fails_but_errors_when_empty():
    # Rust crate/module: codex-cloud-tasks/src/env_detect.rs::list_environments.
    def with_by_repo(url, _headers):
        if url.endswith("/openai/codex"):
            return response([{"id": "repo-only", "label": "Repo"}])
        return response("down", status=502, content_type="text/plain")

    assert [
        row.id
        for row in list_environments(
            BASE,
            {},
            origins=["https://github.com/openai/codex.git"],
            transport=with_by_repo,
        )
    ] == ["repo-only"]

    with pytest.raises(RuntimeError) as exc:
        list_environments(
            BASE,
            {},
            origins=[],
            transport=lambda _url, _headers: response(
                "down", status=502, content_type="text/plain"
            ),
        )
    assert str(exc.value) == (
        "GET https://chatgpt.com/backend-api/wham/environments failed: 502; "
        "content-type=text/plain; body=down"
    )
