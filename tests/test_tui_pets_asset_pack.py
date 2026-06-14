from __future__ import annotations

from dataclasses import dataclass

import pytest

from pycodex.tui.pets.asset_pack import (
    PET_MAX_DOWNLOAD_BYTES,
    builtin_pet_url,
    builtin_spritesheet_path,
    ensure_builtin_pet,
    pack_dir,
    validate_download_url,
    write_test_pack,
)


@dataclass(frozen=True)
class Pet:
    spritesheet_file: str


def test_builtin_pet_url_uses_public_cdn_path() -> None:
    assert builtin_pet_url(Pet("dewey-spritesheet-v4.webp")) == (
        "https://persistent.oaistatic.com/codex/pets/v1/dewey-spritesheet-v4.webp"
    )


def test_builtin_spritesheet_path_uses_versioned_pack_assets_dir(tmp_path) -> None:
    assert builtin_spritesheet_path(tmp_path, "dewey.webp") == (
        tmp_path / "cache/tui-pets/v1/assets/dewey.webp"
    )
    assert pack_dir(tmp_path) == tmp_path / "cache/tui-pets/v1"


def test_validate_download_url_rejects_non_https() -> None:
    validate_download_url("https://persistent.oaistatic.com/codex/pets/v1/dewey.webp")
    with pytest.raises(ValueError, match="unsupported pet asset download URL scheme http"):
        validate_download_url("http://example.com/pet.webp")


def test_ensure_builtin_pet_uses_cached_valid_spritesheet(tmp_path) -> None:
    destination = builtin_spritesheet_path(tmp_path, "cached.webp")
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"cached")
    calls: list[str] = []

    def validate(path):
        calls.append(str(path))

    def download(url, max_bytes):  # pragma: no cover - should not be called
        raise AssertionError("download should not run")

    ensure_builtin_pet(tmp_path, Pet("cached.webp"), validate_fn=validate, download_fn=download)

    assert calls == [str(destination)]
    assert destination.read_bytes() == b"cached"


def test_ensure_builtin_pet_downloads_valid_missing_spritesheet(tmp_path) -> None:
    destination = builtin_spritesheet_path(tmp_path, "pet.webp")
    seen_download: list[tuple[str, int]] = []

    def validate(path):
        if not path.exists():
            raise ValueError("missing")

    def download(url, max_bytes):
        seen_download.append((url, max_bytes))
        return b"new-pet"

    ensure_builtin_pet(tmp_path, Pet("pet.webp"), validate_fn=validate, download_fn=download)

    assert destination.read_bytes() == b"new-pet"
    assert seen_download == [
        ("https://persistent.oaistatic.com/codex/pets/v1/pet.webp", PET_MAX_DOWNLOAD_BYTES)
    ]


def test_write_test_pack_installs_all_supplied_builtins(tmp_path) -> None:
    pets = [Pet("a.webp"), Pet("b.webp")]

    write_test_pack(tmp_path, builtin_pets=pets, write_test_spritesheet=lambda path: path.write_bytes(b"x"))

    assert builtin_spritesheet_path(tmp_path, "a.webp").read_bytes() == b"x"
    assert builtin_spritesheet_path(tmp_path, "b.webp").read_bytes() == b"x"
