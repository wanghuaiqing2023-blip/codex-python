"""Minimal TOML compatibility helpers.

Upstream code depends on Python's ``tomllib``. This project also supports
Python versions where ``tomllib`` is unavailable, so this module provides a
small fallback parser for the TOML subset exercised by local configuration
files and tests.
"""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Any, BinaryIO, Mapping
import os
import io

try:
    import tomllib as _stdlib_tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised under legacy Python.
    _stdlib_tomllib = None


if _stdlib_tomllib is not None:

    TOMLDecodeError = _stdlib_tomllib.TOMLDecodeError
    tomllib = _stdlib_tomllib

    def load(fileobj: BinaryIO | str | os.PathLike[str] | os.PathLike[bytes]) -> Mapping[str, Any]:
        return _stdlib_tomllib.load(fileobj)

    def loads(contents: str) -> Mapping[str, Any]:
        return _stdlib_tomllib.loads(contents)

else:

    class TOMLDecodeError(ValueError):
        """Raised when the fallback parser cannot decode the provided TOML."""

    class _TomlParser:
        def __init__(self, contents: str):
            self.contents = contents
            self.position = 0
            self.length = len(contents)
            self.root: dict[str, Any] = {}
            self.current_table: dict[str, Any] = self.root

        def parse(self) -> dict[str, Any]:
            while self._peek() is not None:
                self._skip_ws_and_comments()

                ch = self._peek()
                if ch is None:
                    break
                if ch == "[":
                    self._parse_table_header()
                else:
                    self._parse_key_value()

            return self.root

        def _parse_table_header(self) -> None:
            self._expect("[")
            is_array_table = False
            if self._peek() == "[":
                is_array_table = True
                self._expect("[")

            path = self._parse_key_path(stop={"]"})
            if not path:
                raise self._error("empty table path")

            self._skip_ws_and_comments()
            if is_array_table:
                self._expect("]")
                self._expect("]")
                if self._peek() not in (None, "\n", "\r", "#", " ", "\t"):
                    raise self._error("expected end of array-of-table header")
                self._skip_to_line_end()
                self.current_table = self._ensure_array_table(path)
                return

            self._expect("]")
            if self._peek() not in (None, "\n", "\r", "#", " ", "\t"):
                raise self._error("expected end of table header")
            self._skip_to_line_end()
            self.current_table = self._ensure_table(path)

        def _parse_key_value(self) -> None:
            path = self._parse_key_path()
            if not path:
                raise self._error("empty key")

            self._skip_ws_and_comments()
            self._expect("=")
            self._skip_ws_and_comments()
            value = self._parse_value()

            self._skip_ws_and_comments()
            if self._peek() not in (None, "\n", "\r"):
                raise self._error("invalid trailing content in key/value line")
            self._skip_to_line_end()
            self._assign(path, value)

        def _assign(self, path: tuple[str, ...], value: Any) -> None:
            parent = self.current_table
            for segment in path[:-1]:
                next_value = parent.get(segment)
                if next_value is None:
                    nested: dict[str, Any] = {}
                    parent[segment] = nested
                    parent = nested
                    continue
                if not isinstance(next_value, dict):
                    raise self._error(f"cannot assign to nested key {segment!r} as it is not a table")
                parent = next_value
            parent[path[-1]] = value

        def _ensure_table(self, path: tuple[str, ...]) -> dict[str, Any]:
            table = self.root
            for segment in path:
                next_value = table.get(segment)
                if next_value is None:
                    nested: dict[str, Any] = {}
                    table[segment] = nested
                    table = nested
                    continue
                if not isinstance(next_value, dict):
                    raise self._error(f"table {segment!r} is not a mapping")
                table = next_value
            return table

        def _ensure_array_table(self, path: tuple[str, ...]) -> dict[str, Any]:
            if len(path) < 1:
                raise self._error("empty array-of-table path")

            parent = self.root
            for segment in path[:-1]:
                next_value = parent.get(segment)
                if next_value is None:
                    nested: dict[str, Any] = {}
                    parent[segment] = nested
                    parent = nested
                    continue
                if not isinstance(next_value, dict):
                    raise self._error(f"array-of-table path {segment!r} is not a mapping")
                parent = next_value

            key = path[-1]
            entries = parent.get(key)
            if entries is None:
                entries = []
                parent[key] = entries
            elif not isinstance(entries, list):
                raise self._error(f"array-of-table key {key!r} is not an array")

            item: dict[str, Any] = {}
            entries.append(item)
            return item

        def _parse_key_path(self, *, stop: set[str] | None = None) -> tuple[str, ...]:
            stop = stop or {"=", "\n", "\r"}

            path: list[str] = []
            while True:
                self._skip_ws_and_comments()
                segment = self._parse_key_segment(stop=stop.union({"."}))
                path.append(segment)

                self._skip_ws_and_comments()
                if self._peek() == ".":
                    self._expect(".")
                    continue
                break
            return tuple(path)

        def _parse_key_segment(self, *, stop: set[str]) -> str:
            ch = self._peek()
            if ch is None:
                raise self._error("unexpected end while parsing key")
            if ch in ('"', "'"):
                return self._parse_string(is_key=True)

            start = self.position
            while (ch := self._peek()) is not None and ch not in stop and ch not in {" ", "\t", "\r", "\n"}:
                self.position += 1
            if self.position == start:
                raise self._error("empty key segment")
            return self.contents[start : self.position].strip()

        def _parse_value(self) -> Any:
            ch = self._peek()
            if ch is None:
                raise self._error("unexpected end while parsing value")

            if ch == "[":
                return self._parse_array()
            if ch == "{":
                return self._parse_inline_table()
            if ch in ('"', "'"):
                return self._parse_string()
            if ch.isalpha():
                return self._parse_unquoted_value()
            if ch.isdigit() or ch in "+-.":
                return self._parse_unquoted_value()

            raise self._error("unexpected value token")

        def _parse_unquoted_value(self) -> Any:
            token = self._consume_token({" ", "\t", "\r", "\n", ",", "]", "}", "#"})
            if not token:
                raise self._error("unexpected value token")

            lowered = token.lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False

            if lowered in {"inf", "+inf", "-inf"}:
                return float(f"{'-' if lowered == '-inf' else ''}inf")
            if lowered in {"nan", "+nan", "-nan"}:
                return float(f"{'-' if lowered == '-nan' else ''}nan")

            parsed_datetime = self._parse_datetime_value(token)
            if parsed_datetime is not None:
                return parsed_datetime

            return self._parse_number(token)

        def _parse_number(self, token: str) -> int | float:
            normalized = token.replace("_", "")
            if not normalized:
                raise self._error("invalid numeric value")
            try:
                if "." in normalized or "e" in normalized.lower():
                    return float(normalized)
                return int(normalized, 10)
            except ValueError as exc:
                raise self._error(f"invalid numeric value: {token}") from exc

        def _parse_datetime_value(self, token: str) -> object | None:
            if "T" in token or "t" in token:
                text = token
                if token.endswith("Z"):
                    text = token[:-1] + "+00:00"
                try:
                    return datetime.fromisoformat(text)
                except ValueError:
                    return None

            if len(token) >= 10 and token[4] == "-" and token[7] == "-":
                try:
                    return date.fromisoformat(token)
                except ValueError:
                    pass

            if ":" in token:
                if "." in token:
                    parts = token.split(".")
                    if len(parts) != 2:
                        return None
                    if len(parts[0]) < 8:
                        return None
                try:
                    return time.fromisoformat(token)
                except ValueError:
                    return None

            return None

        def _parse_string(self, *, is_key: bool = False) -> str:
            quote = self._expect_any("\'\"")
            is_triple = self._peek_sequence(quote, 2)
            if is_triple:
                self.position += 2

            value_chars: list[str] = []
            while True:
                ch = self._peek()
                if ch is None:
                    kind = "key" if is_key else "string"
                    raise self._error(f"unterminated {kind} string")

                if is_triple and self._peek_sequence(quote, 3):
                    self.position += 3
                    break
                if not is_triple and ch == quote:
                    self.position += 1
                    break

                if not is_triple and ch == "\n":
                    kind = "key" if is_key else "string"
                    raise self._error(f"unterminated {kind} string")

                if quote == '"' and not is_triple and ch == "\\":
                    self.position += 1
                    escaped = self._expect_any("\"\\/btnfruU")
                    if escaped in {"u", "U"}:
                        value_chars.append(self._parse_unicode_escape(escaped))
                        continue
                    value_chars.append(self._escaped_char(escaped))
                    continue

                if quote == '"' and is_triple and ch == "\\":
                    self.position += 1
                    if self._peek() in {"\n", "\r"}:
                        while self._peek() in {"\n", "\r"}:
                            if self._peek() == "\r" and self.contents[self.position : self.position + 2] == "\r\n":
                                self.position += 2
                            else:
                                self.position += 1
                        while self._peek() in {" ", "\t"}:
                            self.position += 1
                        continue
                    escaped = self._expect_any("\"\\/btnfruU")
                    if escaped in {"u", "U"}:
                        value_chars.append(self._parse_unicode_escape(escaped))
                        continue
                    value_chars.append(self._escaped_char(escaped))
                    continue

                value_chars.append(ch)
                self.position += 1

            return "".join(value_chars)

        def _parse_array(self) -> list[Any]:
            self._expect("[")
            values: list[Any] = []
            while True:
                self._skip_ws_and_comments()
                if self._peek() == "]":
                    self.position += 1
                    break
                values.append(self._parse_value())
                self._skip_ws_and_comments()
                if self._peek() == ",":
                    self.position += 1
                    self._skip_ws_and_comments()
                    if self._peek() == "]":
                        # allow trailing comma.
                        continue
                elif self._peek() != "]":
                    raise self._error("expected ',' or ']' in array")
            return values

        def _parse_inline_table(self) -> dict[str, Any]:
            self._expect("{")
            data: dict[str, Any] = {}
            while True:
                self._skip_ws_and_comments()
                if self._peek() == "}":
                    self.position += 1
                    break

                key = self._parse_key_path(stop={"=", "}", ",", "\n", "\r"})
                if len(key) != 1:
                    raise self._error("invalid inline table key")
                key_text = key[0]

                self._skip_ws_and_comments()
                self._expect("=")
                self._skip_ws_and_comments()
                value = self._parse_value()
                data[key_text] = value

                self._skip_ws_and_comments()
                if self._peek() == ",":
                    self.position += 1
                    continue
                if self._peek() != "}":
                    raise self._error("expected ',' or '}' in inline table")

            return data

        def _expect_any(self, chars: str) -> str:
            ch = self._peek()
            if ch is None or ch not in set(chars):
                raise self._error(f"expected one of {sorted(chars)!r}")
            self.position += 1
            return ch

        def _peek_sequence(self, prefix: str, count: int) -> bool:
            return self.contents.startswith(prefix * count, self.position)

        def _consume_token(self, stop: set[str]) -> str:
            start = self.position
            while (ch := self._peek()) is not None and ch not in stop:
                self.position += 1
            return self.contents[start:self.position]

        def _escaped_char(self, escaped: str) -> str:
            mapping = {
                '"': '"',
                "\\": "\\",
                "/": "/",
                "b": "\b",
                "f": "\f",
                "n": "\n",
                "r": "\r",
                "t": "\t",
            }
            return mapping[escaped]

        def _parse_unicode_escape(self, kind: str) -> str:
            digits = self.contents[self.position : self.position + (4 if kind == "u" else 8)]
            if kind == "u":
                if len(digits) != 4 or any(char not in "0123456789abcdefABCDEF" for char in digits):
                    raise self._error("invalid unicode escape sequence")
                self.position += 4
                return chr(int(digits, 16))

            if kind == "U":
                if len(digits) != 8 or any(char not in "0123456789abcdefABCDEF" for char in digits):
                    raise self._error("invalid unicode escape sequence")
                self.position += 8
                return chr(int(digits, 16))

            raise self._error("invalid unicode escape sequence")

        def _expect(self, expected: str) -> None:
            if self._peek() != expected:
                raise self._error(f"expected {expected!r}")
            self.position += 1

        def _skip_ws_and_comments(self) -> None:
            while (ch := self._peek()) is not None:
                if ch in {" ", "\t", "\r", "\n"}:
                    self.position += 1
                    continue
                if ch == "#":
                    self._skip_to_line_end()
                    continue
                return

        def _skip_to_line_end(self) -> None:
            while (ch := self._peek()) is not None and ch not in {"\n", "\r"}:
                self.position += 1
            if self._peek() in {"\n", "\r"}:
                while self._peek() in {"\n", "\r"}:
                    self.position += 1

        def _peek(self) -> str | None:
            if self.position >= self.length:
                return None
            return self.contents[self.position]

        def _error(self, message: str) -> TOMLDecodeError:
            line = self.contents.count("\n", 0, self.position) + 1
            col = self.position - self.contents.rfind("\n", 0, self.position) if self.position > 0 else self.position
            if col <= 0:
                col = self.position + 1
            return TOMLDecodeError(f"toml parse error at line {line}, column {col}: {message}")

    tomllib = None  # type: ignore[assignment]

    def load(fileobj: BinaryIO | str | os.PathLike[str] | os.PathLike[bytes]) -> Mapping[str, Any]:
        contents: str | bytes | io.TextIOBase
        if isinstance(fileobj, os.PathLike):
            path = Path(fileobj)
            contents = path.read_text(encoding="utf-8")
        elif isinstance(fileobj, str):
            path = Path(fileobj)
            if path.exists():
                contents = path.read_text(encoding="utf-8")
            else:
                contents = fileobj
        elif isinstance(fileobj, bytes):
            contents = fileobj
        else:
            contents = fileobj.read()

        if isinstance(contents, io.TextIOBase):
            contents = contents.read()

        if isinstance(contents, bytes):
            contents = contents.decode("utf-8")
        return loads(contents)

    def loads(contents: str) -> Mapping[str, Any]:
        parser = _TomlParser(contents)
        return parser.parse()


__all__ = [
    "TOMLDecodeError",
    "load",
    "loads",
    "tomllib",
]
