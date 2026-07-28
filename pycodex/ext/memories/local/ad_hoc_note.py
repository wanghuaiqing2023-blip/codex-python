"""Ad-hoc memory note validation from Rust ``local/ad_hoc_note.rs``."""

from __future__ import annotations

from ..backend import AddAdHocMemoryNoteRequest
from ..backend import AddAdHocMemoryNoteResponse
from ..backend import MemoriesBackendError

AD_HOC_NOTE_FILENAME_MAX_BYTES = 128
AD_HOC_NOTE_SLUG_MAX_BYTES = 80
TIMESTAMP_PREFIX_LEN = len("YYYY-MM-DDTHH-MM-SS-")


def validate_filename(filename: str) -> None:
    encoded = filename.encode("utf-8")
    if len(encoded) > AD_HOC_NOTE_FILENAME_MAX_BYTES:
        raise MemoriesBackendError.invalid_filename(
            filename, "must be at most 128 bytes"
        )
    if not filename.endswith(".md"):
        raise MemoriesBackendError.invalid_filename(filename, "must end with .md")
    stem = filename[:-3]
    slug = stem[TIMESTAMP_PREFIX_LEN:]
    if not has_valid_timestamp_prefix(stem):
        raise MemoriesBackendError.invalid_filename(
            filename, "must use YYYY-MM-DDTHH-MM-SS-<slug>.md"
        )
    slug_bytes = slug.encode("utf-8")
    if not slug_bytes or len(slug_bytes) > AD_HOC_NOTE_SLUG_MAX_BYTES:
        raise MemoriesBackendError.invalid_filename(
            filename, "slug must be 1 to 80 bytes"
        )
    if not all(
        97 <= byte <= 122 or 48 <= byte <= 57 or byte == 45 for byte in slug_bytes
    ):
        raise MemoriesBackendError.invalid_filename(
            filename,
            "slug must contain only lowercase ASCII letters, digits, or hyphens",
        )


def has_valid_timestamp_prefix(stem: str) -> bool:
    raw = stem.encode("ascii", errors="ignore")
    return (
        len(raw) > TIMESTAMP_PREFIX_LEN
        and raw[4:5] == b"-"
        and raw[7:8] == b"-"
        and raw[10:11] == b"T"
        and raw[13:14] == b"-"
        and raw[16:17] == b"-"
        and raw[19:20] == b"-"
        and are_digits(raw[0:4])
        and are_digits(raw[5:7])
        and are_digits(raw[8:10])
        and are_digits(raw[11:13])
        and are_digits(raw[14:16])
        and are_digits(raw[17:19])
    )


def are_digits(value: bytes) -> bool:
    return all(48 <= byte <= 57 for byte in value)


async def add_ad_hoc_note(
    backend: object, request: AddAdHocMemoryNoteRequest
) -> AddAdHocMemoryNoteResponse:
    validate_filename(request.filename)
    if not request.note.strip():
        raise MemoriesBackendError("ad-hoc note must not be empty")
    notes_dir = (
        getattr(backend, "root") / "extensions" / "ad_hoc" / "notes"
    )
    current = getattr(backend, "root")
    current.mkdir(exist_ok=True)
    for component in ("extensions", "ad_hoc", "notes"):
        current /= component
        if current.is_symlink():
            raise MemoriesBackendError.invalid_path(
                str(current), "must not be a symlink"
            )
        if current.exists() and not current.is_dir():
            raise MemoriesBackendError.invalid_path(
                str(current), "must be a directory"
            )
        current.mkdir(exist_ok=True)
    target = notes_dir / request.filename
    try:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(request.note)
    except FileExistsError as exc:
        raise MemoriesBackendError(
            f"ad-hoc note '{request.filename}' already exists"
        ) from exc
    return AddAdHocMemoryNoteResponse()


__all__ = [
    "add_ad_hoc_note",
    "are_digits",
    "has_valid_timestamp_prefix",
    "validate_filename",
]
