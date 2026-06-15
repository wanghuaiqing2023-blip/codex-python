"""Config diagnostics helpers ported from ``codex-config``."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .toml_compat import TOMLDecodeError, loads


@dataclass(frozen=True)
class TextPosition:
    line: int
    column: int


@dataclass(frozen=True)
class TextRange:
    start: TextPosition
    end: TextPosition


@dataclass(frozen=True)
class ConfigError:
    path: Path
    range: TextRange
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "message", str(self.message))


class ConfigLoadError(Exception):
    def __init__(self, error: ConfigError, source: BaseException | None = None) -> None:
        super().__init__(str(error.message))
        self.error = error
        self.source = source

    def config_error(self) -> ConfigError:
        return self.error

    def __str__(self) -> str:
        start = self.error.range.start
        return f"{self.error.path}:{start.line}:{start.column}: {self.error.message}"


def io_error_from_config_error(
    kind: type[OSError] | None,
    error: ConfigError,
    source: BaseException | None = None,
) -> ConfigLoadError:
    return ConfigLoadError(error, source)


def config_error_from_toml(path: str | Path, contents: str, err: BaseException) -> ConfigError:
    range_ = _range_from_decode_error(contents, err)
    return ConfigError(Path(path), range_, _error_message(err))


def config_error_from_typed_toml(
    path: str | Path,
    contents: str,
    validator: Callable[[Mapping[str, Any]], None] | None = None,
) -> ConfigError | None:
    try:
        value = loads(contents)
    except TOMLDecodeError as err:
        return config_error_from_toml(path, contents, err)
    if validator is None:
        return None
    try:
        validator(value)
    except TypeError as err:
        return ConfigError(Path(path), default_range(), str(err))
    except ValueError as err:
        return ConfigError(Path(path), default_range(), str(err))
    return None


def first_layer_config_error_from_entries(
    layers: Iterable[Any],
    config_toml_file: str,
    validator: Callable[[Mapping[str, Any]], None] | None = None,
) -> ConfigError | None:
    for layer in layers:
        path = _config_path_for_layer(layer, config_toml_file)
        if path is None:
            continue
        try:
            contents = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except OSError:
            continue
        error = config_error_from_typed_toml(path, contents, validator)
        if error is not None:
            return error
    return None


def first_layer_config_error(
    layers: Any,
    config_toml_file: str,
    validator: Callable[[Mapping[str, Any]], None] | None = None,
) -> ConfigError | None:
    get_layers = getattr(layers, "get_layers", None)
    if callable(get_layers):
        return first_layer_config_error_from_entries(get_layers(), config_toml_file, validator)
    return first_layer_config_error_from_entries(layers, config_toml_file, validator)


def text_range_from_span(contents: str, span: range | tuple[int, int]) -> TextRange:
    start_offset, end_offset = _span_bounds(span)
    end_index = end_offset - 1 if end_offset > start_offset else end_offset
    return TextRange(
        start=position_for_offset(contents, start_offset),
        end=position_for_offset(contents, end_index),
    )


def position_for_offset(contents: str, index: int) -> TextPosition:
    data = contents.encode("utf-8")
    if not data:
        return TextPosition(1, 1)
    safe_index = min(max(index, 0), max(len(data) - 1, 0))
    column_offset = max(index - safe_index, 0)
    prefix = data[:safe_index]
    line_start = prefix.rfind(b"\n") + 1
    line = prefix[:line_start].count(b"\n") + 1
    try:
        column = data[line_start : safe_index + 1].decode("utf-8").__len__()
    except UnicodeDecodeError:
        column = safe_index - line_start + 1
    return TextPosition(line, column + column_offset)


def default_range() -> TextRange:
    position = TextPosition(1, 1)
    return TextRange(position, position)


def format_config_error(error: ConfigError, contents: str) -> str:
    start = error.range.start
    lines = [f"{error.path}:{start.line}:{start.column}: {error.message}"]
    source_lines = contents.splitlines()
    line_index = start.line - 1
    if line_index < 0 or line_index >= len(source_lines):
        return lines[0]
    line = source_lines[line_index].rstrip("\r")
    line_number = str(start.line)
    gutter = len(line_number)
    lines.append(f"{'':>{gutter}} |")
    lines.append(f"{line_number:>{gutter}} | {line}")
    highlight_len = 1
    if error.range.end.line == error.range.start.line and error.range.end.column >= start.column:
        highlight_len = error.range.end.column - start.column + 1
    spaces = " " * max(start.column - 1, 0)
    lines.append(f"{'':>{gutter}} | {spaces}{'^' * max(highlight_len, 1)}")
    return "\n".join(lines)


def format_config_error_with_source(error: ConfigError) -> str:
    try:
        contents = error.path.read_text(encoding="utf-8")
    except OSError:
        contents = ""
    return format_config_error(error, contents)


def span_for_toml_key_path(contents: str, path: list[str] | tuple[str, ...]) -> range | None:
    if not path:
        return None
    key = path[-1]
    for line_start, line in _iter_lines_with_offsets(contents):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        prefix = line.split("=", 1)[0]
        candidate = prefix.strip().strip('"').strip("'")
        if candidate == key:
            start = line_start + line.index(prefix) + prefix.index(prefix.lstrip())
            return range(start, start + len(key))
    return None


def span_for_config_path(contents: str, path: list[str] | tuple[str, ...]) -> range | None:
    return span_for_toml_key_path(contents, path)


def _config_path_for_layer(layer: Any, config_toml_file: str) -> Path | None:
    if isinstance(layer, Mapping):
        source = layer.get("name") or layer.get("source")
        folder = layer.get("config_folder") or layer.get("folder")
    else:
        source = getattr(layer, "name", getattr(layer, "source", None))
        config_folder = getattr(layer, "config_folder", None)
        folder = config_folder() if callable(config_folder) else config_folder
    if folder is not None:
        return Path(folder) / config_toml_file
    if source is None:
        return None
    for attr in ("file", "path"):
        value = source.get(attr) if isinstance(source, Mapping) else getattr(source, attr, None)
        if value is not None:
            return Path(value)
    dot_codex_folder = (
        source.get("dot_codex_folder") if isinstance(source, Mapping) else getattr(source, "dot_codex_folder", None)
    )
    if dot_codex_folder is not None:
        return Path(dot_codex_folder) / config_toml_file
    return None


def _range_from_decode_error(contents: str, err: BaseException) -> TextRange:
    lineno = getattr(err, "lineno", None)
    colno = getattr(err, "colno", None)
    if isinstance(lineno, int) and isinstance(colno, int):
        position = TextPosition(max(lineno, 1), max(colno, 1))
        return TextRange(position, position)
    pos = getattr(err, "pos", None)
    if isinstance(pos, int):
        return text_range_from_span(contents, range(pos, pos + 1))
    return default_range()


def _error_message(err: BaseException) -> str:
    msg = getattr(err, "msg", None)
    return str(msg if msg is not None else err)


def _span_bounds(span: range | tuple[int, int]) -> tuple[int, int]:
    if isinstance(span, range):
        return span.start, span.stop
    return int(span[0]), int(span[1])


def _iter_lines_with_offsets(contents: str) -> Iterable[tuple[int, str]]:
    offset = 0
    for line in contents.splitlines(keepends=True):
        yield offset, line.rstrip("\r\n")
        offset += len(line.encode("utf-8"))


__all__ = [
    "ConfigError",
    "ConfigLoadError",
    "TextPosition",
    "TextRange",
    "config_error_from_toml",
    "config_error_from_typed_toml",
    "default_range",
    "first_layer_config_error",
    "first_layer_config_error_from_entries",
    "format_config_error",
    "format_config_error_with_source",
    "io_error_from_config_error",
    "position_for_offset",
    "span_for_config_path",
    "span_for_toml_key_path",
    "text_range_from_span",
]
