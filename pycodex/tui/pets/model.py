"""Pet manifest loading and normalization.

Upstream source: ``codex/codex-rs/tui/src/pets/model.rs``.

The Rust module validates real WebP dimensions through the ``image`` crate.
This Python port keeps the same manifest, selector, animation, and cache-key
semantics, while treating real image decoding as an explicit dependency
boundary.  Test spritesheets written by ``pets.catalog.write_test_spritesheet``
embed a lightweight dimension marker that this module can validate without
third-party packages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path, PurePath, PureWindowsPath
from typing import Any, Mapping

from .._porting import RustTuiModule, not_ported
from . import asset_pack, catalog

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets::model",
    source="codex/codex-rs/tui/src/pets/model.rs",
)

MAX_PET_FRAMES = 256
MAX_ANIMATION_FPS = 60.0
CUSTOM_PET_PREFIX = "custom:"


@dataclass(frozen=True)
class AnimationFrame:
    sprite_index: int
    duration: float

    @property
    def duration_ms(self) -> int:
        return int(round(self.duration * 1000))


@dataclass(frozen=True)
class Animation:
    frames: tuple[AnimationFrame, ...]
    loop_start: int | None
    fallback: str

    def total_duration(self) -> float:
        return sum(frame.duration for frame in self.frames)


@dataclass(frozen=True)
class Pet:
    id: str
    display_name: str
    description: str
    spritesheet_path: Path
    frame_width: int
    frame_height: int
    columns: int
    rows: int
    frame_count_value: int
    animations: dict[str, Animation] = field(default_factory=dict)

    @classmethod
    def load_with_codex_home(cls, value: str, codex_home: str | os.PathLike[str] | None = None) -> "Pet":
        if path_like(value):
            return load_pet_path(value)

        if value.startswith(CUSTOM_PET_PREFIX):
            return load_custom_pet(value[len(CUSTOM_PET_PREFIX) :], codex_home)

        builtin = catalog.builtin_pet(value)
        if builtin is not None:
            return load_builtin_pet(builtin, codex_home)

        return load_custom_pet(value, codex_home)

    def frame_count(self) -> int:
        return self.frame_count_value

    def frame_cache_key(self) -> str:
        try:
            data = self.spritesheet_path.read_bytes()
        except OSError as exc:
            raise OSError(f"read {self.spritesheet_path}") from exc
        digest = hashlib.sha256(data).hexdigest()
        return (
            f"sha256-{digest}-{self.frame_width}x{self.frame_height}-"
            f"{self.columns}x{self.rows}"
        )


@dataclass(frozen=True)
class FrameSpec:
    width: int = catalog.DEFAULT_FRAME_WIDTH
    height: int = catalog.DEFAULT_FRAME_HEIGHT
    columns: int = catalog.DEFAULT_FRAME_COLUMNS
    rows: int = catalog.DEFAULT_FRAME_ROWS

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "FrameSpec":
        if value is None:
            return cls()
        return cls(
            width=int(value.get("width", catalog.DEFAULT_FRAME_WIDTH)),
            height=int(value.get("height", catalog.DEFAULT_FRAME_HEIGHT)),
            columns=int(value.get("columns", catalog.DEFAULT_FRAME_COLUMNS)),
            rows=int(value.get("rows", catalog.DEFAULT_FRAME_ROWS)),
        )


@dataclass(frozen=True)
class AnimationSpec:
    frames: tuple[int, ...] = ()
    fps: float | None = None
    loop_animation: bool | None = None
    fallback: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AnimationSpec":
        return cls(
            frames=tuple(int(frame) for frame in value.get("frames", [])),
            fps=None if value.get("fps") is None else float(value["fps"]),
            loop_animation=None if value.get("loop") is None else bool(value["loop"]),
            fallback=str(value.get("fallback", "")),
        )


@dataclass(frozen=True)
class PetFile:
    id: str | None = None
    display_name: str | None = None
    description: str | None = None
    spritesheet_path: str | None = None
    frame: FrameSpec | None = None
    animations: dict[str, AnimationSpec] = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: str) -> "PetFile":
        data = json.loads(raw)
        animations = {
            str(name): AnimationSpec.from_mapping(spec)
            for name, spec in dict(data.get("animations", {})).items()
        }
        return cls(
            id=data.get("id"),
            display_name=data.get("displayName"),
            description=data.get("description"),
            spritesheet_path=data.get("spritesheetPath"),
            frame=FrameSpec.from_mapping(data.get("frame")) if data.get("frame") is not None else None,
            animations=animations,
        )


def custom_pet_selector(id: str) -> str:
    return f"{CUSTOM_PET_PREFIX}{id}"


def load_builtin_pet(pet: catalog.BuiltinPet, codex_home: str | os.PathLike[str] | None) -> Pet:
    if codex_home is None:
        raise ValueError("CODEX_HOME is not available")
    spritesheet_path = asset_pack.builtin_spritesheet_path(codex_home, pet.spritesheet_file)
    if not spritesheet_path.exists():
        raise FileNotFoundError(f"missing spritesheet {spritesheet_path}")
    return Pet(
        id=pet.id,
        display_name=pet.display_name,
        description=pet.description,
        spritesheet_path=spritesheet_path,
        frame_width=catalog.DEFAULT_FRAME_WIDTH,
        frame_height=catalog.DEFAULT_FRAME_HEIGHT,
        columns=catalog.DEFAULT_FRAME_COLUMNS,
        rows=catalog.DEFAULT_FRAME_ROWS,
        frame_count_value=default_frame_count(),
        animations=default_animations(),
    )


def load_custom_pet(value: str, codex_home: str | os.PathLike[str] | None) -> Pet:
    if codex_home is None:
        raise ValueError("CODEX_HOME is not available")
    home = Path(codex_home)
    pet_dir = home / "pets" / value
    if (pet_dir / "pet.json").is_file():
        return load_pet_manifest(pet_dir, "pet.json", value, custom_pet_cache_id(value))

    avatar_dir = home / "avatars" / value
    if (avatar_dir / "avatar.json").is_file():
        return load_pet_manifest(avatar_dir, "avatar.json", value, custom_pet_cache_id(value))

    raise ValueError(f"unknown pet {value}")


def load_pet_path(value: str) -> Pet:
    path = expand_path(value)
    if not path.exists():
        raise FileNotFoundError(f"pet path {path}")
    directory = path if path.is_dir() else path.parent
    if str(directory) == "":
        raise ValueError("pet json path has no containing directory")
    pet_dir = directory.resolve()
    if (pet_dir / "pet.json").is_file():
        manifest_file = "pet.json"
    elif (pet_dir / "avatar.json").is_file():
        manifest_file = "avatar.json"
    else:
        raise FileNotFoundError(f"missing pet.json or avatar.json in {pet_dir}")
    fallback_id = pet_dir.name or "pet"
    return load_pet_manifest(pet_dir, manifest_file, fallback_id, fallback_id)


def load_pet_manifest(pet_dir: str | os.PathLike[str], manifest_file: str, fallback_id: str, cache_id: str) -> Pet:
    pet_dir_path = Path(pet_dir)
    config_path = pet_dir_path / manifest_file
    try:
        file = PetFile.from_json(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OSError(f"read {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"parse {config_path}: {exc}") from exc

    manifest_id = _non_empty(file.id)
    display_name = _non_empty(file.display_name) or manifest_id or fallback_id
    pet_id = (manifest_id or fallback_id) if cache_id == fallback_id else cache_id
    description = (file.description or "").strip()
    spritesheet_value = _non_empty(file.spritesheet_path) or "spritesheet.webp"
    spritesheet_path = resolve_spritesheet_path(pet_dir_path, spritesheet_value)
    if not spritesheet_path.exists():
        raise FileNotFoundError(f"missing spritesheet {spritesheet_path}")

    spritesheet_width, spritesheet_height = validate_app_spritesheet_dimensions(spritesheet_path)
    frame = file.frame or FrameSpec()
    frame_count = validate_frame_spec(frame, spritesheet_width, spritesheet_height)
    return Pet(
        id=pet_id,
        display_name=display_name,
        description=description,
        spritesheet_path=spritesheet_path,
        frame_width=frame.width,
        frame_height=frame.height,
        columns=frame.columns,
        rows=frame.rows,
        frame_count_value=frame_count,
        animations=load_animations(file.animations, frame_count),
    )


def resolve_spritesheet_path(pet_dir: str | os.PathLike[str], spritesheet_path: str) -> Path:
    if _is_absolute_or_escaping(spritesheet_path):
        raise ValueError(f"spritesheet path must stay inside {Path(pet_dir)}")
    return Path(pet_dir) / spritesheet_path


def validate_app_spritesheet_dimensions(path: str | os.PathLike[str]) -> tuple[int, int]:
    dimensions = _read_test_spritesheet_dimensions(Path(path))
    if dimensions is None:
        return not_ported(RUST_MODULE, "validate_app_spritesheet_dimensions")
    width, height = dimensions
    if width != catalog.SPRITESHEET_WIDTH or height != catalog.SPRITESHEET_HEIGHT:
        raise ValueError(f"spritesheet must be {catalog.SPRITESHEET_WIDTH}x{catalog.SPRITESHEET_HEIGHT} pixels")
    return width, height


def validate_frame_spec(frame: FrameSpec, spritesheet_width: int, spritesheet_height: int) -> int:
    if frame.width == 0 or frame.height == 0 or frame.columns == 0 or frame.rows == 0:
        raise ValueError("pet frame dimensions and grid counts must be non-zero")

    total_width = _checked_mul_u32(frame.width, frame.columns, "pet frame grid width overflow")
    total_height = _checked_mul_u32(frame.height, frame.rows, "pet frame grid height overflow")
    if total_width != spritesheet_width or total_height != spritesheet_height:
        raise ValueError(
            "pet frame grid must cover spritesheet exactly: "
            f"expected {spritesheet_width}x{spritesheet_height}, got {total_width}x{total_height}"
        )

    frame_count = _checked_mul_u32(frame.columns, frame.rows, "pet frame count overflow")
    if frame_count > MAX_PET_FRAMES:
        raise ValueError(f"pet frame count {frame_count} exceeds maximum {MAX_PET_FRAMES}")
    return frame_count


def custom_pet_cache_id(id: str) -> str:
    return f"custom-{id}"


def path_like(value: str) -> bool:
    return (
        value in {".", ".."}
        or value.startswith("~/")
        or value.startswith("../")
        or value.startswith("./")
        or Path(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or "/" in value
        or "\\" in value
    )


def expand_path(value: str) -> Path:
    if value == "~" or value.startswith("~/"):
        home = os.environ.get("HOME")
        if home is None:
            raise OSError("HOME is not set")
        if value == "~":
            return Path(home)
        return Path(home) / value[2:]
    return Path(value)


def load_animations(specs: Mapping[str, AnimationSpec | Mapping[str, Any]], frame_count: int) -> dict[str, Animation]:
    animations = default_animations()
    if not specs:
        validate_animation_indices(animations, frame_count)
        return animations

    for name, raw_spec in specs.items():
        spec = raw_spec if isinstance(raw_spec, AnimationSpec) else AnimationSpec.from_mapping(raw_spec)
        if not spec.frames:
            raise ValueError(f"animation {name} must include at least one frame")
        for sprite_index in spec.frames:
            if sprite_index >= frame_count:
                raise ValueError(
                    f"animation {name} references sprite index {sprite_index}, but pet has {frame_count} frames"
                )

        if spec.fps is None:
            fps = 8.0
        elif math.isfinite(spec.fps) and spec.fps > 0.0 and spec.fps <= MAX_ANIMATION_FPS:
            fps = spec.fps
        else:
            raise ValueError(
                f"animation {name} fps must be finite and between 0 and {MAX_ANIMATION_FPS}, got {spec.fps}"
            )
        duration = 1.0 / fps
        fallback = spec.fallback if spec.fallback else "idle"
        loop_start = 0 if (True if spec.loop_animation is None else spec.loop_animation) else None
        animations[str(name)] = Animation(
            frames=tuple(AnimationFrame(sprite_index, duration) for sprite_index in spec.frames),
            loop_start=loop_start,
            fallback=fallback,
        )

    animations.setdefault("idle", idle_animation())
    validate_animation_indices(animations, frame_count)
    return animations


def validate_animation_indices(animations: Mapping[str, Animation], frame_count: int) -> None:
    for name, animation in animations.items():
        if not animation.frames:
            raise ValueError(f"animation {name} must include at least one frame")
        for frame in animation.frames:
            if frame.sprite_index >= frame_count:
                raise ValueError(
                    f"animation {name} references sprite index {frame.sprite_index}, but pet has {frame_count} frames"
                )
        if animation.fallback not in animations:
            raise ValueError(f"animation {name} fallback {animation.fallback} does not exist")


def default_frame_count() -> int:
    return catalog.DEFAULT_FRAME_COLUMNS * catalog.DEFAULT_FRAME_ROWS


def default_animations() -> dict[str, Animation]:
    return {
        "idle": idle_animation(),
        "running-right": app_state_animation(1, 8, 120, 220),
        "running-left": app_state_animation(2, 8, 120, 220),
        "waving": app_state_animation(3, 4, 140, 280),
        "jumping": app_state_animation(4, 5, 140, 280),
        "failed": app_state_animation(5, 8, 140, 240),
        "waiting": app_state_animation(6, 6, 150, 260),
        "running": app_state_animation(7, 6, 120, 220),
        "review": app_state_animation(8, 6, 150, 280),
        "move_right": app_state_animation(1, 8, 120, 220),
        "move_left": app_state_animation(2, 8, 120, 220),
        "wave": app_state_animation(3, 4, 140, 280),
        "bounce": app_state_animation(4, 5, 140, 280),
        "sad": app_state_animation(5, 8, 140, 240),
    }


def idle_animation() -> Animation:
    return Animation(
        frames=tuple(
            AnimationFrame(sprite_index, duration_ms / 1000.0)
            for sprite_index, duration_ms in ((0, 1680), (1, 660), (2, 660), (3, 840), (4, 840), (5, 1920))
        ),
        loop_start=0,
        fallback="idle",
    )


def app_state_animation(row_index: int, frame_count: int, frame_duration_ms: int, final_frame_duration_ms: int) -> Animation:
    primary = tuple(
        AnimationFrame(
            row_index * catalog.DEFAULT_FRAME_COLUMNS + column_index,
            (final_frame_duration_ms if column_index == frame_count - 1 else frame_duration_ms) / 1000.0,
        )
        for column_index in range(frame_count)
    )
    primary_frame_count = len(primary) * 3
    return Animation(
        frames=primary + primary + primary + idle_animation().frames,
        loop_start=primary_frame_count,
        fallback="idle",
    )


def sprite_indices(animation: Animation) -> list[int]:
    return [frame.sprite_index for frame in animation.frames]


def durations_ms(animation: Animation) -> list[int]:
    return [frame.duration_ms for frame in animation.frames]


def _non_empty(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _checked_mul_u32(left: int, right: int, message: str) -> int:
    result = left * right
    if result > 0xFFFF_FFFF:
        raise OverflowError(message)
    return result


def _is_absolute_or_escaping(value: str) -> bool:
    path = PurePath(value)
    windows_path = PureWindowsPath(value)
    if path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        return True
    return any(part == ".." for part in path.parts) or any(part == ".." for part in windows_path.parts)


def _read_test_spritesheet_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    except OSError:
        raise
    prefix = "test spritesheet "
    if not text.startswith(prefix):
        return None
    size = text[len(prefix) :].strip().split()[0]
    try:
        width, height = size.lower().split("x", 1)
        return int(width), int(height)
    except (ValueError, IndexError):
        return None


__all__ = [
    "Animation",
    "AnimationFrame",
    "AnimationSpec",
    "CUSTOM_PET_PREFIX",
    "FrameSpec",
    "MAX_ANIMATION_FPS",
    "MAX_PET_FRAMES",
    "Pet",
    "PetFile",
    "RUST_MODULE",
    "app_state_animation",
    "custom_pet_cache_id",
    "custom_pet_selector",
    "default_animations",
    "default_frame_count",
    "durations_ms",
    "expand_path",
    "idle_animation",
    "load_animations",
    "load_builtin_pet",
    "load_custom_pet",
    "load_pet_manifest",
    "load_pet_path",
    "path_like",
    "resolve_spritesheet_path",
    "sprite_indices",
    "validate_animation_indices",
    "validate_app_spritesheet_dimensions",
    "validate_frame_spec",
]
