"""Built-in pet asset acquisition and cache ownership.

Upstream source: ``codex/codex-rs/tui/src/pets/asset_pack.rs``.

This module owns cache paths, CDN URL validation, bounded downloads, staging
installs, and the ensure-flow.  Faithful WebP/image-dimension validation is a
non-stdlib dependency boundary and is therefore injectable.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any, Callable, Optional, Sequence, Union
from urllib.parse import urlparse
from urllib.request import urlopen
from uuid import uuid4

from .._porting import RustTuiModule
from . import catalog
from .model import _image_dimensions

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets::asset_pack",
    source="codex/codex-rs/tui/src/pets/asset_pack.rs",
    status="complete",
)

PET_PACK_VERSION = "v1"
PET_PACK_DIR = "cache/tui-pets"
PET_CDN_BASE_URL = "https://persistent.oaistatic.com/codex/pets/v1"
PET_DOWNLOAD_TIMEOUT = 60
PET_MAX_DOWNLOAD_BYTES = 4 * 1024 * 1024


def builtin_spritesheet_path(codex_home: Union[str, os.PathLike[str]], file: str) -> Path:
    return pack_dir(codex_home) / "assets" / file


def ensure_builtin_pet(
    codex_home: Union[str, os.PathLike[str]],
    pet: Any,
    *,
    validate_fn: Optional[Callable[[Path], None]] = None,
    download_fn: Optional[Callable[[str, int], bytes]] = None,
    install_fn: Optional[Callable[[Path, Path], None]] = None,
) -> None:
    """Ensure a built-in spritesheet exists and passes structural validation."""

    validate = validate_cached_spritesheet if validate_fn is None else validate_fn
    download = download_bytes_with_limit if download_fn is None else download_fn
    install = install_downloaded_spritesheet if install_fn is None else install_fn

    spritesheet_file = _spritesheet_file(pet)
    destination = builtin_spritesheet_path(codex_home, spritesheet_file)
    try:
        validate(destination)
        return
    except Exception:
        pass

    url = builtin_pet_url(pet)
    bytes_ = download(url, PET_MAX_DOWNLOAD_BYTES)
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)

    staging = destination.with_name(f".{spritesheet_file}.download-{uuid4()}.webp")
    staging.write_bytes(bytes_)
    try:
        validate(staging)
    except Exception:
        staging.unlink(missing_ok=True)
        raise

    try:
        install(staging, destination)
        return
    except Exception:
        pass

    try:
        validate(destination)
        staging.unlink(missing_ok=True)
        return
    except Exception:
        if destination.exists():
            destination.unlink()
        install(staging, destination)


def builtin_pet_url(pet: Any) -> str:
    url = f"{PET_CDN_BASE_URL}/{_spritesheet_file(pet)}"
    validate_download_url(url)
    return url


def pack_dir(codex_home: Union[str, os.PathLike[str]]) -> Path:
    return Path(codex_home) / PET_PACK_DIR / PET_PACK_VERSION


def download_bytes_with_limit(url: str, max_bytes: int) -> bytes:
    validate_download_url(url)
    with urlopen(url, timeout=PET_DOWNLOAD_TIMEOUT) as response:
        final_url = getattr(response, "url", url)
        validate_download_url(final_url)
        length = response.headers.get("Content-Length") if getattr(response, "headers", None) else None
        if length is not None and int(length) > max_bytes:
            raise ValueError(f"pet asset download from {url} exceeded {max_bytes} bytes")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"pet asset download from {url} exceeded {max_bytes} bytes")
    return data


def install_downloaded_spritesheet(
    staging: Union[str, os.PathLike[str]],
    destination: Union[str, os.PathLike[str]],
) -> None:
    shutil.move(str(staging), str(destination))


def validate_download_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme == "":
        raise ValueError(f"parse pet asset download URL {value}")
    if parsed.scheme != "https":
        raise ValueError(f"unsupported pet asset download URL scheme {parsed.scheme}")


def validate_cached_spritesheet(path: Union[str, os.PathLike[str]]) -> None:
    path_obj = Path(path)
    width, height = _image_dimensions(path_obj)
    if width != catalog.SPRITESHEET_WIDTH or height != catalog.SPRITESHEET_HEIGHT:
        raise ValueError(
            "invalid pet spritesheet dimensions for "
            f"{path_obj}: expected {catalog.SPRITESHEET_WIDTH}x{catalog.SPRITESHEET_HEIGHT}, "
            f"got {width}x{height}"
        )


def write_test_pack(
    codex_home: Union[str, os.PathLike[str]],
    *,
    builtin_pets: Optional[Sequence[Any]] = None,
    write_test_spritesheet: Optional[Callable[[Path], None]] = None,
) -> None:
    if builtin_pets is None:
        builtin_pets = catalog.BUILTIN_PETS
    if write_test_spritesheet is None:
        write_test_spritesheet = catalog.write_test_spritesheet
    assets_dir = pack_dir(codex_home) / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for pet in builtin_pets:
        write_test_spritesheet(assets_dir / _spritesheet_file(pet))


def _spritesheet_file(pet: Any) -> str:
    if isinstance(pet, dict):
        return str(pet["spritesheet_file"])
    value = getattr(pet, "spritesheet_file", None)
    if value is None:
        payload = getattr(pet, "_payload", None)
        if isinstance(payload, dict):
            value = payload.get("spritesheet_file")
        elif payload is not None:
            value = getattr(payload, "spritesheet_file", None)
    if value is None:
        raise AttributeError("pet must expose spritesheet_file")
    return str(value)


__all__ = [
    "PET_CDN_BASE_URL",
    "PET_DOWNLOAD_TIMEOUT",
    "PET_MAX_DOWNLOAD_BYTES",
    "PET_PACK_DIR",
    "PET_PACK_VERSION",
    "RUST_MODULE",
    "builtin_pet_url",
    "builtin_spritesheet_path",
    "download_bytes_with_limit",
    "ensure_builtin_pet",
    "install_downloaded_spritesheet",
    "pack_dir",
    "validate_cached_spritesheet",
    "validate_download_url",
    "write_test_pack",
]
