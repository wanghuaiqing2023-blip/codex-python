"""Startup synchronization for the OpenAI curated plugin repository.

Rust owner: ``codex-core-plugins::startup_sync``.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_ACCEPT_HEADER = "application/vnd.github+json"
GITHUB_API_VERSION_HEADER = "2022-11-28"
CURATED_PLUGINS_BACKUP_ARCHIVE_API_URL = (
    "https://chatgpt.com/backend-api/plugins/export/curated"
)
OPENAI_PLUGINS_OWNER = "openai"
OPENAI_PLUGINS_REPO = "plugins"
CURATED_PLUGINS_RELATIVE_DIR = ".tmp/plugins"
CURATED_PLUGINS_SHA_FILE = ".tmp/plugins.sha"
CURATED_PLUGINS_BACKUP_ARCHIVE_FALLBACK_VERSION = "export-backup"
CURATED_PLUGINS_GIT_TIMEOUT = 30
CURATED_PLUGINS_HTTP_TIMEOUT = 30
CURATED_PLUGINS_BACKUP_ARCHIVE_TIMEOUT = 30
CURATED_PLUGINS_STALE_TEMP_DIR_MAX_AGE = 10 * 60


def curated_plugins_repo_path(codex_home: Path) -> Path:
    return Path(codex_home) / CURATED_PLUGINS_RELATIVE_DIR


def read_curated_plugins_sha(codex_home: Path) -> str | None:
    return _read_sha_file(Path(codex_home) / CURATED_PLUGINS_SHA_FILE)


def has_local_curated_plugins_snapshot(codex_home: Path) -> bool:
    codex_home = Path(codex_home)
    return (
        curated_plugins_repo_path(codex_home)
        / ".agents"
        / "plugins"
        / "marketplace.json"
    ).is_file() and (codex_home / CURATED_PLUGINS_SHA_FILE).is_file()


def sync_openai_plugins_repo(codex_home: Path) -> str:
    codex_home = Path(codex_home)
    git_error: Exception | None = None
    try:
        return _sync_via_git(codex_home, "git")
    except Exception as exc:
        git_error = exc
    try:
        return _sync_via_http(codex_home, GITHUB_API_BASE_URL)
    except Exception as http_error:
        if has_local_curated_plugins_snapshot(codex_home):
            raise RuntimeError(
                f"git sync failed for curated plugin sync: {git_error}; "
                f"GitHub HTTP sync failed for curated plugin sync: {http_error}; "
                "export archive fallback skipped because a local curated plugins "
                "snapshot already exists"
            ) from http_error
        try:
            return _sync_via_backup_archive(
                codex_home,
                CURATED_PLUGINS_BACKUP_ARCHIVE_API_URL,
            )
        except Exception as backup_error:
            raise RuntimeError(
                f"git sync failed for curated plugin sync: {git_error}; "
                f"GitHub HTTP sync failed for curated plugin sync: {http_error}; "
                f"export archive sync failed for curated plugin sync: {backup_error}"
            ) from backup_error


def _sync_via_git(codex_home: Path, git_binary: str) -> str:
    repo_path = curated_plugins_repo_path(codex_home)
    sha_path = codex_home / CURATED_PLUGINS_SHA_FILE
    remote_sha = _git_ls_remote_head_sha(git_binary)
    local_sha = _read_local_git_or_sha_file(repo_path, sha_path, git_binary)
    if local_sha == remote_sha and (repo_path / ".git").is_dir():
        return remote_sha

    staging = _prepare_temp_dir(repo_path)
    try:
        _run_git(
            [
                git_binary,
                "clone",
                "--depth",
                "1",
                "https://github.com/openai/plugins.git",
                str(staging),
            ],
            "git clone curated plugins repo",
        )
        cloned_sha = _git_head_sha(staging, git_binary)
        if cloned_sha != remote_sha:
            raise RuntimeError(
                f"curated plugins clone HEAD mismatch: expected {remote_sha}, "
                f"got {cloned_sha}"
            )
        _ensure_marketplace_manifest_exists(staging)
        _activate_curated_repo(repo_path, staging)
        _write_curated_plugins_sha(sha_path, remote_sha)
        return remote_sha
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _sync_via_http(codex_home: Path, api_base_url: str) -> str:
    repo_path = curated_plugins_repo_path(codex_home)
    sha_path = codex_home / CURATED_PLUGINS_SHA_FILE
    remote_sha = _fetch_curated_repo_remote_sha(api_base_url)
    if _read_sha_file(sha_path) == remote_sha and repo_path.is_dir():
        return remote_sha

    staging = _prepare_temp_dir(repo_path)
    try:
        extract_zipball_to_dir(
            _fetch_curated_repo_zipball(api_base_url, remote_sha),
            staging,
        )
        _ensure_marketplace_manifest_exists(staging)
        _activate_curated_repo(repo_path, staging)
        _write_curated_plugins_sha(sha_path, remote_sha)
        return remote_sha
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _sync_via_backup_archive(codex_home: Path, api_url: str) -> str:
    repo_path = curated_plugins_repo_path(codex_home)
    staging = _prepare_temp_dir(repo_path)
    try:
        metadata = json.loads(_fetch_text(api_url, public=True))
        download_url = metadata.get("download_url") or metadata.get("downloadUrl")
        if not isinstance(download_url, str) or not download_url:
            raise RuntimeError(
                f"curated plugins backup archive response from {api_url} "
                "did not include a download URL"
            )
        extract_zipball_to_dir(_fetch_bytes(download_url, public=True), staging)
        _ensure_marketplace_manifest_exists(staging)
        version = (
            _read_extracted_backup_archive_git_sha(staging)
            or CURATED_PLUGINS_BACKUP_ARCHIVE_FALLBACK_VERSION
        )
        _activate_curated_repo(repo_path, staging)
        _write_curated_plugins_sha(
            codex_home / CURATED_PLUGINS_SHA_FILE,
            version,
        )
        return version
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def extract_zipball_to_dir(contents: bytes, destination: Path) -> None:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"failed to open curated plugins zip archive: {exc}") from exc

    with archive:
        for entry in archive.infolist():
            raw_name = entry.filename.replace("\\", "/")
            relative = PurePosixPath(raw_name)
            if (
                relative.is_absolute()
                or any(part == ".." for part in relative.parts)
            ):
                raise ValueError(
                    f"curated plugins zip entry `{entry.filename}` escapes extraction root"
                )
            parts = [part for part in relative.parts if part not in {"", "."}]
            if len(parts) <= 1:
                continue
            output_path = destination.joinpath(*parts[1:])
            if entry.is_dir():
                output_path.mkdir(parents=True, exist_ok=True)
                continue
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, output_path.open("wb") as target:
                shutil.copyfileobj(source, target)
            mode = entry.external_attr >> 16
            if os.name != "nt" and mode:
                output_path.chmod(mode)


def _prepare_temp_dir(repo_path: Path) -> Path:
    parent = repo_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    _remove_stale_temp_dirs(parent)
    return Path(tempfile.mkdtemp(prefix="plugins-clone-", dir=parent))


def _remove_stale_temp_dirs(parent: Path) -> None:
    cutoff = time.time() - CURATED_PLUGINS_STALE_TEMP_DIR_MAX_AGE
    for path in parent.glob("plugins-clone-*"):
        try:
            if path.stat().st_mtime < cutoff:
                shutil.rmtree(path)
        except OSError:
            continue


def _activate_curated_repo(repo_path: Path, staging: Path) -> None:
    backup = repo_path.parent / f"plugins-backup-{next(tempfile._get_candidate_names())}"
    if repo_path.exists():
        repo_path.replace(backup)
        try:
            staging.replace(repo_path)
        except BaseException:
            if not repo_path.exists() and backup.exists():
                backup.replace(repo_path)
            raise
        shutil.rmtree(backup, ignore_errors=True)
    else:
        staging.replace(repo_path)


def _ensure_marketplace_manifest_exists(repo_path: Path) -> None:
    manifest = repo_path / ".agents" / "plugins" / "marketplace.json"
    if not manifest.is_file():
        raise RuntimeError(
            f"curated plugins archive missing marketplace manifest at {manifest}"
        )


def _write_curated_plugins_sha(path: Path, sha: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{sha}\n", encoding="utf-8")


def _read_sha_file(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _read_local_git_or_sha_file(
    repo_path: Path,
    sha_path: Path,
    git_binary: str,
) -> str | None:
    if (repo_path / ".git").is_dir():
        try:
            return _git_head_sha(repo_path, git_binary)
        except RuntimeError:
            pass
    return _read_sha_file(sha_path)


def _git_ls_remote_head_sha(git_binary: str) -> str:
    output = _run_git(
        [
            git_binary,
            "ls-remote",
            "https://github.com/openai/plugins.git",
            "HEAD",
        ],
        "git ls-remote curated plugins repo",
    )
    first = output.stdout.splitlines()[0] if output.stdout.splitlines() else ""
    sha, separator, _ = first.partition("\t")
    if not separator or not sha:
        raise RuntimeError(
            f"unexpected git ls-remote output for curated plugins repo: {first}"
        )
    return sha


def _git_head_sha(repo_path: Path, git_binary: str) -> str:
    output = _run_git(
        [git_binary, "-C", str(repo_path), "rev-parse", "HEAD"],
        "git rev-parse HEAD",
    )
    sha = output.stdout.strip()
    if not sha:
        raise RuntimeError(f"git rev-parse HEAD returned empty output in {repo_path}")
    return sha


def _run_git(arguments: list[str], context: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            arguments,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=CURATED_PLUGINS_GIT_TIMEOUT,
            check=False,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"failed to run {context}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip()
        raise RuntimeError(
            f"{context} failed with status {result.returncode}"
            + (f": {detail}" if detail else "")
        )
    return result


def _fetch_curated_repo_remote_sha(api_base_url: str) -> str:
    repo_url = (
        f"{api_base_url.rstrip('/')}/repos/{OPENAI_PLUGINS_OWNER}/"
        f"{OPENAI_PLUGINS_REPO}"
    )
    repository = json.loads(_fetch_text(repo_url))
    branch = repository.get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise RuntimeError(
            f"curated plugins repository response from {repo_url} did not "
            "include a default branch"
        )
    ref_url = f"{repo_url}/git/ref/heads/{branch}"
    reference = json.loads(_fetch_text(ref_url))
    sha = reference.get("object", {}).get("sha")
    if not isinstance(sha, str) or not sha:
        raise RuntimeError(
            f"curated plugins ref response from {ref_url} did not include a HEAD sha"
        )
    return sha


def _fetch_curated_repo_zipball(api_base_url: str, sha: str) -> bytes:
    url = (
        f"{api_base_url.rstrip('/')}/repos/{OPENAI_PLUGINS_OWNER}/"
        f"{OPENAI_PLUGINS_REPO}/zipball/{sha}"
    )
    return _fetch_bytes(url)


def _fetch_text(url: str, *, public: bool = False) -> str:
    return _fetch_bytes(url, public=public).decode("utf-8", errors="replace")


def _fetch_bytes(url: str, *, public: bool = False) -> bytes:
    headers = (
        {}
        if public
        else {
            "accept": GITHUB_API_ACCEPT_HEADER,
            "x-github-api-version": GITHUB_API_VERSION_HEADER,
        }
    )
    request = urllib.request.Request(url, headers=headers)
    timeout = (
        CURATED_PLUGINS_BACKUP_ARCHIVE_TIMEOUT
        if public
        else CURATED_PLUGINS_HTTP_TIMEOUT
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"request to {url} failed with status {exc.code}: {body}"
        ) from exc


def _read_extracted_backup_archive_git_sha(repo_path: Path) -> str | None:
    git_dir = repo_path / ".git"
    if not git_dir.is_dir():
        return None
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if head.startswith("ref: "):
        reference = head[5:].strip()
        path = PurePosixPath(reference)
        if not reference.startswith("refs/") or any(
            part in {"", ".", ".."} for part in path.parts
        ):
            raise RuntimeError(
                f"curated plugins backup archive git ref must stay under refs/: "
                f"{reference}"
            )
        ref_path = git_dir.joinpath(*path.parts)
        if ref_path.is_file():
            return ref_path.read_text(encoding="utf-8").strip()
        packed = git_dir / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                if line.startswith(("#", "^")):
                    continue
                sha, separator, candidate = line.partition(" ")
                if separator and candidate == reference:
                    return sha
        raise RuntimeError(
            f"failed to resolve curated plugins backup archive git ref {reference}"
        )
    return head or None


__all__ = [
    "CURATED_PLUGINS_BACKUP_ARCHIVE_API_URL",
    "CURATED_PLUGINS_RELATIVE_DIR",
    "CURATED_PLUGINS_SHA_FILE",
    "curated_plugins_repo_path",
    "extract_zipball_to_dir",
    "has_local_curated_plugins_snapshot",
    "read_curated_plugins_sha",
    "sync_openai_plugins_repo",
]
