"""Port of Rust ``codex-cloud-tasks/src/env_detect.rs``."""

from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence
from urllib import request

from pycodex.cloud_tasks.app import EnvironmentRow


Headers = Mapping[str, str]
Transport = Callable[[str, Headers], "CloudTasksHttpResponse"]


@dataclass(frozen=True)
class CodeEnvironment:
    id: str
    label: str | None = None
    is_pinned: bool | None = None
    task_count: int | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CodeEnvironment":
        return cls(
            id=str(value["id"]),
            label=None if value.get("label") is None else str(value.get("label")),
            is_pinned=None
            if value.get("is_pinned") is None
            else bool(value.get("is_pinned")),
            task_count=None
            if value.get("task_count") is None
            else int(value.get("task_count")),
        )


@dataclass(frozen=True)
class AutodetectSelection:
    id: str
    label: str | None = None


@dataclass(frozen=True)
class CloudTasksHttpResponse:
    status: int
    body: str
    content_type: str = ""

    @property
    def is_success(self) -> bool:
        return 200 <= self.status < 300


def environment_list_url(base_url: str) -> str:
    if "/backend-api" in base_url:
        return f"{base_url}/wham/environments"
    return f"{base_url}/api/codex/environments"


def by_repo_environments_url(base_url: str, owner: str, repo: str) -> str:
    if "/backend-api" in base_url:
        return f"{base_url}/wham/environments/by-repo/github/{owner}/{repo}"
    return f"{base_url}/api/codex/environments/by-repo/github/{owner}/{repo}"


def parse_owner_repo(url: str) -> tuple[str, str] | None:
    s = url.strip()
    if s.startswith("ssh://"):
        s = s[len("ssh://") :]

    marker = "@github.com:"
    idx = s.find(marker)
    if idx != -1:
        rest = s[idx + len(marker) :].lstrip("/").removesuffix(".git")
        parts = rest.split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return None

    for prefix in (
        "https://github.com/",
        "http://github.com/",
        "git://github.com/",
        "github.com/",
    ):
        if s.startswith(prefix):
            rest = s[len(prefix) :].lstrip("/").removesuffix(".git")
            parts = rest.split("/", 1)
            if len(parts) == 2:
                return parts[0], parts[1]
            return None
    return None


def uniq(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def pick_environment_row(
    envs: Sequence[CodeEnvironment], desired_label: str | None = None
) -> CodeEnvironment | None:
    if not envs:
        return None
    if desired_label is not None:
        lc = desired_label.lower()
        for env in envs:
            if (env.label or "").lower() == lc:
                return env
    if len(envs) == 1:
        return envs[0]
    for env in envs:
        if env.is_pinned or False:
            return env

    best = envs[0]
    best_key = best.task_count or 0
    for env in envs[1:]:
        key = env.task_count or 0
        if key >= best_key:
            best = env
            best_key = key
    return best


def _default_transport(url: str, headers: Headers) -> CloudTasksHttpResponse:
    req = request.Request(url, headers=dict(headers), method="GET")
    try:
        with request.urlopen(req) as res:  # noqa: S310 - caller controls URL.
            body = res.read().decode("utf-8", errors="replace")
            content_type = res.headers.get("content-type", "")
            return CloudTasksHttpResponse(res.status, body, content_type)
    except request.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        content_type = exc.headers.get("content-type", "") if exc.headers else ""
        return CloudTasksHttpResponse(exc.code, body, content_type)


def get_json(
    url: str,
    headers: Headers | None = None,
    *,
    transport: Transport | None = None,
) -> list[CodeEnvironment]:
    response = (transport or _default_transport)(url, headers or {})
    if not response.is_success:
        raise RuntimeError(
            f"GET {url} failed: {response.status}; "
            f"content-type={response.content_type}; body={response.body}"
        )
    try:
        parsed = json.loads(response.body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Decode error for {url}: {exc}; "
            f"content-type={response.content_type}; body={response.body}"
        ) from exc
    if not isinstance(parsed, list):
        raise RuntimeError(
            f"Decode error for {url}: expected list; "
            f"content-type={response.content_type}; body={response.body}"
        )
    return [CodeEnvironment.from_mapping(item) for item in parsed]


def get_git_origins(
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] | None = None,
) -> list[str]:
    run = runner or _run_git

    config = run(["git", "config", "--get-regexp", r"remote\..*\.url"])
    if config.returncode == 0:
        urls = []
        for line in config.stdout.splitlines():
            if " " in line:
                _, url = line.split(" ", 1)
                urls.append(url.strip())
        if urls:
            return uniq(urls)

    remote = run(["git", "remote", "-v"])
    if remote.returncode == 0:
        urls = []
        for line in remote.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                urls.append(parts[1])
        if urls:
            return uniq(urls)

    return []


def _run_git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def autodetect_environment_id(
    base_url: str,
    headers: Headers | None = None,
    desired_label: str | None = None,
    *,
    origins: Sequence[str] | None = None,
    transport: Transport | None = None,
) -> AutodetectSelection:
    request_headers = headers or {}
    by_repo_envs: list[CodeEnvironment] = []
    for origin in (origins if origins is not None else get_git_origins()):
        parsed = parse_owner_repo(origin)
        if parsed is None:
            continue
        owner, repo = parsed
        url = by_repo_environments_url(base_url, owner, repo)
        try:
            by_repo_envs.extend(get_json(url, request_headers, transport=transport))
        except Exception:
            continue

    picked = pick_environment_row(by_repo_envs, desired_label)
    if picked is not None:
        return AutodetectSelection(picked.id, picked.label)

    list_url = environment_list_url(base_url)
    all_envs = get_json(list_url, request_headers, transport=transport)
    picked = pick_environment_row(all_envs, desired_label)
    if picked is not None:
        return AutodetectSelection(picked.id, picked.label)
    raise RuntimeError("no environments available")


def list_environments(
    base_url: str,
    headers: Headers | None = None,
    *,
    origins: Sequence[str] | None = None,
    transport: Transport | None = None,
) -> list[EnvironmentRow]:
    request_headers = headers or {}
    rows: MutableMapping[str, EnvironmentRow] = {}

    for origin in (origins if origins is not None else get_git_origins()):
        parsed = parse_owner_repo(origin)
        if parsed is None:
            continue
        owner, repo = parsed
        url = by_repo_environments_url(base_url, owner, repo)
        try:
            envs = get_json(url, request_headers, transport=transport)
        except Exception:
            continue
        repo_hint = f"{owner}/{repo}"
        for env in envs:
            existing = rows.get(env.id)
            if existing is None:
                rows[env.id] = EnvironmentRow(
                    id=env.id,
                    label=env.label,
                    is_pinned=env.is_pinned or False,
                    repo_hints=repo_hint,
                )
            else:
                rows[env.id] = EnvironmentRow(
                    id=existing.id,
                    label=existing.label if existing.label is not None else env.label,
                    is_pinned=existing.is_pinned or (env.is_pinned or False),
                    repo_hints=existing.repo_hints or repo_hint,
                )

    list_url = environment_list_url(base_url)
    try:
        envs = get_json(list_url, request_headers, transport=transport)
    except Exception:
        if not rows:
            raise
    else:
        for env in envs:
            existing = rows.get(env.id)
            if existing is None:
                rows[env.id] = EnvironmentRow(
                    id=env.id,
                    label=env.label,
                    is_pinned=env.is_pinned or False,
                    repo_hints=None,
                )
            else:
                rows[env.id] = EnvironmentRow(
                    id=existing.id,
                    label=existing.label if existing.label is not None else env.label,
                    is_pinned=existing.is_pinned or (env.is_pinned or False),
                    repo_hints=existing.repo_hints,
                )

    return sorted(
        rows.values(),
        key=lambda row: (
            not row.is_pinned,
            (row.label or "").lower(),
            row.id,
        ),
    )
