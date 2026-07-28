"""Shared production-symbol anchors for Rust/Python structure contracts."""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
import re
import textwrap
from typing import Iterable


_RUST_ITEM_RE = re.compile(
    r"(?m)^\s*(?P<public>pub(?:\([^)]*\))?\s+)?"
    r"(?:async\s+)?(?:unsafe\s+)?"
    r"(?:struct|enum|trait|type|fn|const|static)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
)
_CFG_RE = re.compile(r"#\s*\[\s*cfg\s*\((.*)\)\s*\]")
_MODULE_RE = re.compile(
    r"(?m)^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;"
)
_RUST_USE_RE = re.compile(
    r"(?m)^\s*pub(?:\([^)]*\))?\s+use\s+([^;]+);"
)
_INLINE_MODULE_RE = re.compile(
    r"(?m)^(?:pub(?:\([^)]*\))?\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{"
)
_INCLUDE_RE = re.compile(r'include!\(\s*"([^"]+)"\s*\)\s*;')


def read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return ""


def _split_cfg_arguments(value: str) -> tuple[str, ...]:
    arguments: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(value):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            arguments.append(value[start:index].strip())
            start = index + 1
    arguments.append(value[start:].strip())
    return tuple(item for item in arguments if item)


def _cfg_requires_test(expression: str) -> bool:
    expression = expression.strip()
    if expression == "test":
        return True
    for operator in ("all", "any", "not"):
        prefix = f"{operator}("
        if not expression.startswith(prefix) or not expression.endswith(")"):
            continue
        children = _split_cfg_arguments(expression[len(prefix) : -1])
        if operator == "all":
            return any(_cfg_requires_test(child) for child in children)
        if operator == "any":
            return bool(children) and all(_cfg_requires_test(child) for child in children)
        return False
    return False


def _line_requires_test(line: str) -> bool:
    match = _CFG_RE.search(line)
    return bool(match and _cfg_requires_test(match.group(1)))


def production_rust_text(text: str) -> str:
    """Remove cfg expressions containing ``test`` before collecting anchors.

    Rust test modules are normally brace-balanced. Counting braces is
    sufficient for this conservative navigation pass; an uncertain item is
    excluded rather than promoted into accepted structural evidence.
    """
    output: list[str] = []
    pending_test_item = False
    skipping_block = False
    base_depth = 0
    depth = 0
    for line in text.splitlines(keepends=True):
        delta = line.count("{") - line.count("}")
        if skipping_block:
            depth += delta
            if depth <= base_depth:
                skipping_block = False
            continue
        if _line_requires_test(line):
            pending_test_item = True
            continue
        if pending_test_item:
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//", "/*", "*")):
                continue
            if "{" in line:
                base_depth = depth
                depth += delta
                skipping_block = depth > base_depth
            # Semicolon items and malformed/unknown cfg(test) declarations are
            # omitted as a single conservative statement.
            pending_test_item = False
            continue
        output.append(line)
        depth += delta
    return "".join(output)


def _inline_module_bodies(text: str, name: str) -> tuple[str, ...]:
    text = textwrap.dedent(text)
    bodies: list[str] = []
    for match in _INLINE_MODULE_RE.finditer(text):
        if match.group(1) != name:
            continue
        start = match.end() - 1
        depth = 0
        for index in range(start, len(text)):
            character = text[index]
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    bodies.append(textwrap.dedent(text[start + 1 : index]))
                    break
    return tuple(bodies)


def _expand_relative_includes(text: str, source_dir: Path, seen: frozenset[Path]) -> str:
    def replace(match: re.Match[str]) -> str:
        included = (source_dir / match.group(1)).resolve()
        if included in seen or not included.is_file():
            return match.group(0)
        included_text = production_rust_text(read_source(included))
        return _expand_relative_includes(
            included_text,
            included.parent,
            seen | {included},
        )

    return _INCLUDE_RE.sub(replace, text)


def rust_module_text(path: Path, module: str) -> str:
    """Return only the Rust body owned by ``module`` for a shared source file."""
    text = textwrap.dedent(production_rust_text(read_source(path)))
    parts = module.split("::")
    if parts and parts[0] == "bin":
        # ``bin::<cargo-target>`` names the root source file; the target is not
        # a Rust inline module and must not participate in body extraction.
        parts = parts[2:]
    elif parts and parts[0] in {"crate", "main"}:
        parts = parts[1:]
    if path.name == "mod.rs":
        source_leaf = path.parent.name
    elif path.name in {"lib.rs", "main.rs"}:
        source_leaf = ""
    else:
        source_leaf = path.stem
    if source_leaf and source_leaf in parts:
        inline_parts = parts[len(parts) - 1 - parts[::-1].index(source_leaf) + 1 :]
    elif source_leaf:
        inline_parts = ()
    else:
        inline_parts = parts
    for name in inline_parts:
        bodies = _inline_module_bodies(text, name)
        if not bodies:
            return ""
        # Conditional cfg variants of one inline module share one coordinate.
        text = "\n".join(bodies)
    return _expand_relative_includes(text, path.parent, frozenset({path.resolve()}))


def rust_symbols(path: Path) -> tuple[tuple[str, bool], ...]:
    values: dict[str, bool] = {}
    for match in _RUST_ITEM_RE.finditer(production_rust_text(read_source(path))):
        name = match.group("name")
        values[name] = values.get(name, False) or bool(match.group("public"))
    return tuple(sorted(values.items()))


def rust_reexports(path: Path) -> tuple[str, ...]:
    values: set[str] = set()
    for expression in _RUST_USE_RE.findall(production_rust_text(read_source(path))):
        expression = expression.strip()
        if expression.endswith("::*"):
            continue
        if "::{" in expression and expression.endswith("}"):
            body = expression.rsplit("::{", 1)[1][:-1]
            values.update(part.strip().split(" as ")[-1] for part in body.split(","))
            continue
        values.add(expression.rsplit("::", 1)[-1].split(" as ")[-1].strip())
    return tuple(sorted(value for value in values if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)))


def python_symbols(paths: Iterable[Path]) -> tuple[str, ...]:
    values: set[str] = set()
    for path in paths:
        try:
            tree = ast.parse(read_source(path), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                values.add(node.name)
            elif isinstance(node, ast.ImportFrom):
                values.update(alias.asname or alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                values.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                values.update(target.id for target in targets if isinstance(target, ast.Name))
    return tuple(sorted(values))


def anchor_candidates(
    rust_path: Path,
    python_paths: Iterable[Path],
    *,
    rust_module: str | None = None,
) -> tuple[str, ...]:
    if rust_module is None:
        rust = dict(rust_symbols(rust_path))
        rust.update((name, True) for name in rust_reexports(rust_path))
    else:
        module_text = rust_module_text(rust_path, rust_module)
        rust = {
            match.group("name"): bool(match.group("public"))
            for match in _RUST_ITEM_RE.finditer(module_text)
        }
        rust.update(
            (name, True)
            for expression in _RUST_USE_RE.findall(module_text)
            for name in _reexport_names(expression)
        )
    python = set(python_symbols(python_paths))
    common = (name for name in rust if name in python and not name.startswith("_"))
    return tuple(sorted(common, key=lambda name: (not rust[name], name)))[:12]


def _reexport_names(expression: str) -> tuple[str, ...]:
    expression = expression.strip()
    if expression.endswith("::*"):
        return ()
    if "::{" in expression and expression.endswith("}"):
        body = expression.rsplit("::{", 1)[1][:-1]
        return tuple(part.strip().split(" as ")[-1] for part in body.split(","))
    return (expression.rsplit("::", 1)[-1].split(" as ")[-1].strip(),)


def fallback_module_anchors(
    rust_source: str,
    owner: str,
    *,
    root: Path,
    rust_module: str | None = None,
) -> tuple[str, ...]:
    owner_path = PurePosixPath(owner)
    rust_path = root / rust_source
    rust_text = (
        rust_module_text(rust_path, rust_module)
        if rust_module is not None
        else production_rust_text(read_source(rust_path))
    )
    python_path = root / owner_path
    wildcard_targets = {
        expression.strip()[:-3].rsplit("::", 1)[-1]
        for expression in _RUST_USE_RE.findall(rust_text)
        if expression.strip().endswith("::*")
    }
    try:
        tree = ast.parse(read_source(python_path), filename=str(python_path))
    except SyntaxError:
        tree = ast.Module(body=[], type_ignores=[])
    python_modules = {
        (node.module or "").rsplit(".", 1)[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    owner_module = owner_path.parent.name if owner_path.name == "__init__.py" else owner_path.stem
    matched_reexports = sorted(wildcard_targets.intersection(python_modules))
    if wildcard_targets and owner_module in python_modules:
        matched_reexports.append(owner_module)
    reexports = tuple(f"reexport:{name}" for name in dict.fromkeys(matched_reexports))
    module_names = _MODULE_RE.findall(rust_text)
    package = root / owner_path.parent
    imported_modules = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level > 0
        for alias in node.names
    }
    modules = tuple(
        f"module:{name}"
        for name in module_names
        if (package / f"{name}.py").is_file()
        or (package / name / "__init__.py").is_file()
        if owner_path.name == "__init__.py" or name in imported_modules
    )
    return (*modules, *reexports)[:12]


__all__ = [
    "anchor_candidates",
    "fallback_module_anchors",
    "python_symbols",
    "production_rust_text",
    "read_source",
    "rust_module_text",
    "rust_symbols",
    "rust_reexports",
]
