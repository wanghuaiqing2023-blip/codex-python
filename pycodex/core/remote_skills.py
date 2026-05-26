"""Remote skill API helpers ported from ``core-skills/src/remote.rs``.

The active product surface does not wire these helpers yet. This module keeps
the low-level, dependency-free client and zip extraction behavior available for
that future integration.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile


REMOTE_SKILLS_API_TIMEOUT = 30.0


class RemoteSkillScope(str, Enum):
    WORKSPACE_SHARED = "workspace-shared"
    ALL_SHARED = "all-shared"
    PERSONAL = "personal"
    EXAMPLE = "example"


class RemoteSkillProductSurface(str, Enum):
    CHATGPT = "chatgpt"
    CODEX = "codex"
    API = "api"
    ATLAS = "atlas"


@dataclass(frozen=True)
class RemoteSkillSummary:
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class RemoteSkillDownloadResult:
    id: str
    path: Path


@dataclass(frozen=True)
class RemoteSkillAuth:
    uses_codex_backend_value: bool = True
    headers: Mapping[str, str] = field(default_factory=dict)

    def uses_codex_backend(self) -> bool:
        return self.uses_codex_backend_value

    def to_auth_headers(self) -> Mapping[str, str]:
        return self.headers


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes

    def is_success(self) -> bool:
        return 200 <= self.status < 300


HttpGet = Callable[[str, Mapping[str, str], float], HttpResponse]


def as_query_scope(scope: RemoteSkillScope | str) -> str | None:
    return RemoteSkillScope(scope).value


def as_query_product_surface(product_surface: RemoteSkillProductSurface | str) -> str:
    return RemoteSkillProductSurface(product_surface).value


def ensure_codex_backend_auth(auth: Any | None) -> Any:
    if auth is None:
        raise ValueError("chatgpt authentication required for remote skill scopes")
    if not _uses_codex_backend(auth):
        raise ValueError(
            "chatgpt authentication required for remote skill scopes; api key auth is not supported"
        )
    return auth


def list_remote_skills(
    chatgpt_base_url: str,
    auth: Any | None,
    scope: RemoteSkillScope | str,
    product_surface: RemoteSkillProductSurface | str,
    enabled: bool | None = None,
    *,
    http_get: HttpGet | None = None,
    timeout: float = REMOTE_SKILLS_API_TIMEOUT,
) -> tuple[RemoteSkillSummary, ...]:
    base_url = chatgpt_base_url.rstrip("/")
    auth = ensure_codex_backend_auth(auth)

    query_params: list[tuple[str, str]] = [("product_surface", as_query_product_surface(product_surface))]
    query_scope = as_query_scope(scope)
    if query_scope is not None:
        query_params.append(("scope", query_scope))
    if enabled is not None:
        query_params.append(("enabled", "true" if enabled else "false"))

    url = f"{base_url}/hazelnuts?{urlencode(query_params)}"
    response = (http_get or _default_http_get)(url, auth_headers_from_auth(auth), timeout)
    body_text = response.body.decode("utf-8", errors="replace")
    if not response.is_success():
        raise RuntimeError(f"Request failed with status {response.status} from {base_url}/hazelnuts: {body_text}")

    try:
        parsed = json.loads(body_text)
        skills = parsed["hazelnuts"]
    except Exception as exc:
        raise ValueError("Failed to parse skills response") from exc

    return tuple(
        RemoteSkillSummary(
            id=str(skill["id"]),
            name=str(skill["name"]),
            description=str(skill["description"]),
        )
        for skill in skills
    )


def export_remote_skill(
    chatgpt_base_url: str,
    codex_home: Path | str,
    auth: Any | None,
    skill_id: str,
    *,
    http_get: HttpGet | None = None,
    timeout: float = REMOTE_SKILLS_API_TIMEOUT,
) -> RemoteSkillDownloadResult:
    auth = ensure_codex_backend_auth(auth)

    base_url = chatgpt_base_url.rstrip("/")
    url = f"{base_url}/hazelnuts/{skill_id}/export"
    response = (http_get or _default_http_get)(url, auth_headers_from_auth(auth), timeout)
    if not response.is_success():
        body_text = response.body.decode("utf-8", errors="replace")
        raise RuntimeError(f"Download failed with status {response.status} from {url}: {body_text}")
    if not is_zip_payload(response.body):
        raise ValueError("Downloaded remote skill payload is not a zip archive")

    output_dir = Path(codex_home) / "skills" / skill_id
    output_dir.mkdir(parents=True, exist_ok=True)
    extract_zip_to_dir(response.body, output_dir, (skill_id,))
    return RemoteSkillDownloadResult(id=skill_id, path=output_dir)


def auth_headers_from_auth(auth: Any) -> Mapping[str, str]:
    if isinstance(auth, Mapping):
        raw_headers = auth.get("headers", {})
    elif hasattr(auth, "to_auth_headers"):
        raw_headers = auth.to_auth_headers()
    else:
        raw_headers = getattr(auth, "headers", {})
    return {str(key): str(value) for key, value in dict(raw_headers or {}).items()}


def safe_join(base: Path | str, name: str) -> Path:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(name)
    if path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"Invalid file path in remote skill payload: {name}")
    parts = path.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Invalid file path in remote skill payload: {name}")
    result = Path(base)
    for part in parts:
        result /= part
    return result


def is_zip_payload(data: bytes) -> bool:
    return data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06") or data.startswith(b"PK\x07\x08")


def extract_zip_to_dir(
    data: bytes,
    output_dir: Path | str,
    prefix_candidates: tuple[str, ...] | list[str] = (),
) -> None:
    output_path = Path(output_dir)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("Failed to open zip archive") from exc

    with archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            normalized = normalize_zip_name(entry.filename, prefix_candidates)
            if normalized is None:
                continue
            file_path = safe_join(output_path, normalized)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as src, file_path.open("wb") as dst:
                dst.write(src.read())


def normalize_zip_name(name: str, prefix_candidates: tuple[str, ...] | list[str]) -> str | None:
    trimmed = name
    while trimmed.startswith("./"):
        trimmed = trimmed[2:]
    for prefix in prefix_candidates:
        if not prefix:
            continue
        prefix_with_slash = f"{prefix}/"
        if trimmed.startswith(prefix_with_slash):
            trimmed = trimmed[len(prefix_with_slash) :]
            break
    return trimmed or None


def _uses_codex_backend(auth: Any) -> bool:
    if isinstance(auth, Mapping):
        return bool(auth.get("uses_codex_backend", auth.get("uses_codex_backend_value", False)))
    if hasattr(auth, "uses_codex_backend"):
        return bool(auth.uses_codex_backend())
    return bool(getattr(auth, "uses_codex_backend_value", False))


def _default_http_get(url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return HttpResponse(status=int(response.status), body=response.read())
    except HTTPError as exc:
        return HttpResponse(status=int(exc.code), body=exc.read())
    except URLError as exc:
        raise RuntimeError(f"Failed to send request to {url}") from exc


__all__ = [
    "HttpGet",
    "HttpResponse",
    "REMOTE_SKILLS_API_TIMEOUT",
    "RemoteSkillAuth",
    "RemoteSkillDownloadResult",
    "RemoteSkillProductSurface",
    "RemoteSkillScope",
    "RemoteSkillSummary",
    "as_query_product_surface",
    "as_query_scope",
    "auth_headers_from_auth",
    "ensure_codex_backend_auth",
    "export_remote_skill",
    "extract_zip_to_dir",
    "is_zip_payload",
    "list_remote_skills",
    "normalize_zip_name",
    "safe_join",
]
