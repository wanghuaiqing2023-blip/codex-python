"""Conservative Rust/Python structure inspection.

The scanner identifies coordinates and ownership problems. It never infers
behavioral completion from a candidate path or an existing manifest status.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import glob
from pathlib import Path, PurePosixPath
import re
import textwrap
import tomllib
from typing import Iterable

from parity_harness.contracts.anchors import production_rust_text, rust_module_text
from parity_harness.contracts.schema import ModuleContract
from parity_harness.model import Evidence, Finding, LayerResult, MappingStatus, Verdict
from parity_harness.paths import REPO_ROOT


# Missing Rust modules are coverage debt. Existing Python production files
# without an accepted owner remain ownership drift even when a policy lists
# them, otherwise an empty contract directory could make the ownership gate
# pass without constraining the implementation.
COVERAGE_FINDING_CODES = frozenset({"STR015"})


_MOD_RE = re.compile(
    r"(?m)^(?:pub(?:\([^)]*\))?\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;"
)
_INLINE_MOD_RE = re.compile(
    r"(?m)^(?:pub(?:\([^)]*\))?\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{"
)
_USE_RE = re.compile(
    r"(?m)^(pub(?:\([^)]*\))?\s+)?use\s+([^;]+);"
)
_RUST_ITEM_RE = re.compile(
    r"(?m)^(?:pub(?:\([^)]*\))?\s+)?"
    r"(?:async\s+)?(?:unsafe\s+)?"
    r"(?:struct|enum|trait|type|fn|const|static)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)"
)


def _has_production_rust_content(text: str) -> bool:
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return any(
        code and not code.startswith("#![")
        for line in without_blocks.splitlines()
        if (code := line.split("//", 1)[0].strip())
    )


@dataclass(frozen=True)
class RustModule:
    name: str
    source: str
    declarations: tuple[str, ...]
    uses: tuple[str, ...]
    public_uses: tuple[str, ...]
    items: tuple[str, ...]


def _inline_modules(text: str) -> tuple[tuple[str, str], ...]:
    modules: list[tuple[str, str]] = []
    for match in _INLINE_MOD_RE.finditer(text):
        start = match.end() - 1
        depth = 0
        for index in range(start, len(text)):
            character = text[index]
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    modules.append((match.group(1), text[start + 1 : index]))
                    break
    return tuple(modules)


def discover_workspace_crates(workspace: Path) -> tuple[Path, ...]:
    cargo = workspace / "Cargo.toml"
    data = tomllib.loads(cargo.read_text(encoding="utf-8"))
    members = data.get("workspace", {}).get("members", [])
    crates: set[Path] = set()
    for member in members:
        for match in glob.glob(str(workspace / member)):
            path = Path(match)
            if (path / "Cargo.toml").is_file():
                crates.add(path.resolve())
    return tuple(sorted(crates, key=str))


def _module_file(parent: Path, name: str) -> Path | None:
    direct = parent / f"{name}.rs"
    package = parent / name / "mod.rs"
    if direct.is_file():
        return direct
    if package.is_file():
        return package
    return None


def _crate_roots(crate_root: Path) -> tuple[tuple[Path, str], ...]:
    cargo = tomllib.loads((crate_root / "Cargo.toml").read_text(encoding="utf-8-sig"))
    roots: list[tuple[Path, str]] = []
    lib = cargo.get("lib")
    if isinstance(lib, dict) and isinstance(lib.get("path"), str):
        roots.append((crate_root / lib["path"], "crate"))
    elif (crate_root / "src/lib.rs").is_file():
        roots.append((crate_root / "src/lib.rs", "crate"))

    bins = cargo.get("bin", [])
    if isinstance(bins, dict):
        bins = [bins]
    for item in bins:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            path = crate_root / item["path"]
            bin_name = item.get("name")
            coordinate = (
                f"bin::{bin_name}"
                if isinstance(bin_name, str) and bin_name
                else (
                    "main"
                    if path.as_posix().endswith("/src/main.rs")
                    else f"bin::{path.stem}"
                )
            )
            roots.append((path, coordinate))
    if not bins and (crate_root / "src/main.rs").is_file():
        roots.append((crate_root / "src/main.rs", "main"))
    registered_paths = {path.resolve() for path, _ in roots}
    roots.extend(
        (path, f"bin::{path.stem}")
        for path in sorted((crate_root / "src/bin").glob("*.rs"))
        if path.resolve() not in registered_paths
    )
    return tuple(
        dict.fromkeys(
            (path.resolve(), coordinate)
            for path, coordinate in roots
            if path.is_file()
        )
    )


def discover_rust_modules(
    crate_root: Path,
    *,
    include_inline_modules: bool = True,
) -> tuple[RustModule, ...]:
    discovered: dict[tuple[Path, str], str] = {}
    roots = _crate_roots(crate_root)
    root_paths = {path.resolve() for path, _ in roots}

    def visit(path: Path, coordinate: str, inline_text: str | None = None) -> None:
        resolved = path.resolve()
        key = (resolved, coordinate)
        if key in discovered:
            return
        text = textwrap.dedent(
            production_rust_text(
                inline_text
                if inline_text is not None
                else path.read_text(encoding="utf-8-sig")
            )
        )
        if resolved not in root_paths and not _has_production_rust_content(text):
            return
        discovered[key] = text
        module_parent = path.parent if path.name == "mod.rs" else path.parent
        if path.name not in {"lib.rs", "main.rs", "mod.rs"}:
            package_parent = path.parent / path.stem
        else:
            package_parent = module_parent
        for child in _MOD_RE.findall(text):
            if child == "tests" or child.endswith("_tests"):
                continue
            child_path = _module_file(package_parent, child) or _module_file(module_parent, child)
            if child_path is not None:
                visit(child_path, f"{coordinate}::{child}")
        if include_inline_modules:
            for child, body in _inline_modules(text):
                visit(path, f"{coordinate}::{child}", body)

    for root, coordinate in roots:
        visit(root, coordinate)

    modules: list[RustModule] = []
    for (path, coordinate), text in discovered.items():
        uses = _USE_RE.findall(text)
        modules.append(
            RustModule(
                name=coordinate,
                source=path.relative_to(REPO_ROOT).as_posix()
                if REPO_ROOT in path.parents
                else path.as_posix(),
                declarations=tuple(_MOD_RE.findall(text)),
                uses=tuple(value.strip() for public, value in uses if not public),
                public_uses=tuple(value.strip() for public, value in uses if public),
                # Rustfmt leaves module-level items unindented. Excluding indented
                # methods prevents common trait/impl method names from being
                # mistaken for items owned by a child module.
                items=tuple(sorted(set(_RUST_ITEM_RE.findall(text)))),
            )
        )
    return tuple(sorted(modules, key=lambda item: item.name))


def discover_python_modules(root: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.relative_to(REPO_ROOT).as_posix()
            if REPO_ROOT in path.resolve().parents
            else path.as_posix()
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    )


def _contains_anchor(path: Path, anchor: str, *, python: bool) -> bool:
    # Python source commonly carries a UTF-8 BOM on Windows.  ``utf-8-sig``
    # removes it while remaining equivalent to UTF-8 for files without one.
    text = path.read_text(encoding="utf-8-sig")
    return _contains_anchor_text(text, anchor, python=python)


def _contains_anchor_text(text: str, anchor: str, *, python: bool) -> bool:
    if anchor.startswith("reexport:"):
        name = anchor.removeprefix("reexport:")
        if not python:
            return any(
                expression.strip().endswith("::*")
                or expression.strip() == name
                or expression.strip().startswith(f"{name}::")
                for _, expression in _USE_RE.findall(production_rust_text(text))
            )
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return False
        return any(
            isinstance(node, ast.ImportFrom)
            and (node.module or "").rsplit(".", 1)[-1] == name
            for node in ast.walk(tree)
        )
    if not python:
        return bool(re.search(rf"\b{re.escape(anchor)}\b", text))
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    names.update(
        target.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (
            node.targets if isinstance(node, ast.Assign) else (node.target,)
        )
        if isinstance(target, ast.Name)
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
    return anchor in names


def _contains_module_anchor(path: Path, anchor: str, *, python: bool) -> bool:
    return _contains_module_anchor_text(
        path.read_text(encoding="utf-8-sig"),
        path,
        anchor,
        python=python,
    )


def _contains_module_anchor_text(
    text: str,
    path: Path,
    anchor: str,
    *,
    python: bool,
) -> bool:
    name = anchor.removeprefix("module:")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return False
    if not python:
        return name in _MOD_RE.findall(
            production_rust_text(text)
        )
    if path.name != "__init__.py":
        return False
    return (path.parent / f"{name}.py").is_file() or (
        path.parent / name / "__init__.py"
    ).is_file()


def _defined_python_symbols(paths: Iterable[Path]) -> set[str]:
    symbols: set[str] = set()
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                symbols.update(target.id for target in targets if isinstance(target, ast.Name))
    return symbols


def _parse_python(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return None


def _module_name(path: str | PurePosixPath) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolved_imports(tree: ast.Module, current_module: str, is_package: bool) -> set[str]:
    imports: set[str] = set()
    package_parts = current_module.split(".") if is_package else current_module.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = max(0, len(package_parts) - node.level + 1)
                base_parts = package_parts[:keep]
                if node.module:
                    base_parts.extend(node.module.split("."))
                base = ".".join(base_parts)
            else:
                base = node.module or ""
            if base and node.module:
                imports.add(base)
            for alias in node.names:
                if alias.name != "*" and base:
                    imports.add(f"{base}.{alias.name}")
    return imports


def _decision_literals(tree: ast.Module) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            values.update(
                candidate.value
                for candidate in (node.left, *node.comparators)
                if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str)
            )
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"get", "pop", "setdefault"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    values.add(first.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "getattr" and len(node.args) >= 2:
                key = node.args[1]
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    values.add(key.value)
    return values


def _reexported_names(uses: Iterable[str]) -> set[str]:
    names: set[str] = set()
    for value in uses:
        tail = value.rsplit("::", 1)[-1].strip()
        if tail.startswith("{") and tail.endswith("}"):
            names.update(part.strip().split(" as ")[-1] for part in tail[1:-1].split(","))
        else:
            names.add(tail.split(" as ")[-1].strip())
    return {name for name in names if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)}


def _rust_graph_coordinate(module: str) -> str:
    if (
        module == "crate"
        or module == "main"
        or module.startswith("main::")
        or module.startswith("bin::")
    ):
        return module
    return f"crate::{module}"


def _source_relative_to_root(source: str, root: Path) -> str:
    path = Path(source)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


class StructureAuditor:
    CHECKER_ID = "structure.owner-and-coordinate"

    def __init__(
        self,
        root: Path = REPO_ROOT,
        *,
        check_item_ownership: bool = True,
        include_inline_modules: bool = True,
        python_root: str | None = None,
        check_orphans: bool = False,
    ) -> None:
        self.root = root.resolve()
        self.check_item_ownership = check_item_ownership
        self.include_inline_modules = include_inline_modules
        self.python_root = python_root
        self.check_orphans = check_orphans
        self._rust_module_cache: dict[tuple[Path, bool], dict[str, RustModule]] = {}

    def _rust_modules(self, crate_root: Path) -> dict[str, RustModule]:
        resolved = crate_root.resolve()
        key = (resolved, self.include_inline_modules)
        modules = self._rust_module_cache.get(key)
        if modules is None:
            modules = {
                item.name: item
                for item in discover_rust_modules(
                    resolved,
                    include_inline_modules=self.include_inline_modules,
                )
            }
            self._rust_module_cache[key] = modules
        return modules

    def check(self, contracts: Iterable[ModuleContract]) -> tuple[LayerResult, ...]:
        contracts = tuple(contracts)
        owner_claims: dict[str, list[str]] = {}
        file_claims: dict[str, list[str]] = {}
        for contract in contracts:
            owner_claims.setdefault(contract.python_owner, []).append(contract.contract_id)
            for path in contract.python["implementation_files"]:
                file_claims.setdefault(path, []).append(contract.contract_id)
        return tuple(
            self._check_one(contract, owner_claims, file_claims) for contract in contracts
        )

    def audit_inventory(
        self,
        contracts: Iterable[ModuleContract],
        *,
        python_root: str,
        rust_root: str | None = None,
        allowed_unowned: Iterable[dict[str, str]] = (),
        uncovered_rust_modules: Iterable[str] = (),
        uncovered_python_files: Iterable[str] = (),
        contract_id: str = "structure-inventory",
    ) -> LayerResult:
        """Detect unregistered production files and stale navigation candidates."""
        contracts = tuple(contracts)
        findings: list[Finding] = []
        root = self.root / python_root
        production = {
            path.relative_to(self.root).as_posix()
            for path in root.rglob("*.py")
            if "tests" not in path.relative_to(root).parts
            and "__pycache__" not in path.relative_to(root).parts
        }
        claimed = {
            path
            for contract in contracts
            for path in contract.python["implementation_files"]
        }
        declared_rust_debt = set(uncovered_rust_modules)
        declared_python_debt = set(uncovered_python_files)
        if rust_root is not None:
            rust_modules = discover_rust_modules(
                self.root / rust_root,
                include_inline_modules=self.include_inline_modules,
            )
            discovered_rust = {module.name: module for module in rust_modules}
            claimed_rust = {
                _rust_graph_coordinate(str(contract.rust["module"])): contract
                for contract in contracts
            }
            for coordinate in sorted(discovered_rust.keys() - claimed_rust.keys()):
                module = discovered_rust[coordinate]
                findings.append(
                    Finding(
                        "STR015" if coordinate in declared_rust_debt else "STR018",
                        (
                            "Rust module is declared as coverage debt"
                            if coordinate in declared_rust_debt
                            else "Rust module is neither accepted nor declared as coverage debt"
                        ),
                        coordinate=f"{coordinate} ({module.source})",
                        evidence_type="rust-inventory",
                    )
                )
            for coordinate in sorted(claimed_rust.keys() - discovered_rust.keys()):
                contract = claimed_rust[coordinate]
                findings.append(
                    Finding(
                        "STR016",
                        "contract Rust source is not reachable from the Cargo module graph",
                        coordinate=f"{coordinate} ({contract.rust['source']})",
                        evidence_type="rust-inventory",
                    )
                )
            for coordinate in sorted(claimed_rust.keys() & discovered_rust.keys()):
                contract = claimed_rust[coordinate]
                module = discovered_rust[coordinate]
                contract_source = (self.root / str(contract.rust["source"])).resolve()
                discovered_source = Path(module.source)
                if not discovered_source.is_absolute():
                    discovered_source = self.root / discovered_source
                if contract_source != discovered_source.resolve():
                    findings.append(
                        Finding(
                            "STR025",
                            "contract Rust source does not own this Cargo module coordinate",
                            coordinate=(
                                f"{coordinate}: contract={contract.rust['source']} "
                                f"cargo={module.source}"
                            ),
                            evidence_type="rust-coordinate-source",
                        )
                    )
            for coordinate in sorted(declared_rust_debt - discovered_rust.keys()):
                findings.append(
                    Finding(
                        "STR020",
                        "declared Rust coverage debt is stale or not in the Cargo module graph",
                        coordinate=coordinate,
                        evidence_type="coverage-debt",
                    )
                )
            for coordinate in sorted(declared_rust_debt & claimed_rust.keys()):
                findings.append(
                    Finding(
                        "STR020",
                        "Rust module cannot be both accepted and declared as coverage debt",
                        coordinate=coordinate,
                        evidence_type="coverage-debt",
                    )
                )
        else:
            discovered_rust = {}
            claimed_rust = set()
        allowed: set[str] = set()
        for item in allowed_unowned:
            path = str(item.get("path", ""))
            reason = str(item.get("reason", "")).strip()
            if not path or not reason:
                findings.append(
                    Finding(
                        "STR010",
                        "allowed unowned file requires an existing path and a non-empty reason",
                        coordinate=path,
                        evidence_type="inventory-exception",
                    )
                )
                continue
            if not (self.root / path).is_file():
                findings.append(
                    Finding(
                        "STR011",
                        "allowed unowned file does not exist",
                        coordinate=path,
                        evidence_type="inventory-exception",
                    )
                )
                continue
            allowed.add(path)
        for path in sorted(production - claimed - allowed):
            python_symbols = sorted(
                _defined_python_symbols((self.root / path,))
            )
            rust_symbol_matches = [
                {
                    "module": module.name,
                    "source": _source_relative_to_root(module.source, self.root),
                    "symbols": sorted(set(module.items) & set(python_symbols)),
                }
                for module in discovered_rust.values()
                if set(module.items) & set(python_symbols)
            ]
            findings.append(
                Finding(
                    "STR019" if path in declared_python_debt else "STR012",
                    (
                        "Python production file is declared as ownership drift"
                        if path in declared_python_debt
                        else "Python production file is not registered to a contract owner"
                    ),
                    coordinate=path,
                    evidence_type=(
                        "ownership-debt"
                        if path in declared_python_debt
                        else "python-inventory"
                    ),
                    metadata={
                        "python_file": path,
                        "python_symbols": python_symbols,
                        "rust_symbol_matches": rust_symbol_matches,
                    },
                )
            )
        for path in sorted(declared_python_debt - production):
            findings.append(
                Finding(
                    "STR020",
                    "declared Python coverage debt is stale or not a production file",
                    coordinate=path,
                    evidence_type="coverage-debt",
                )
            )
        for path in sorted(declared_python_debt & (claimed | allowed)):
            findings.append(
                Finding(
                    "STR020",
                    "Python file cannot be accepted or excluded and also declared as coverage debt",
                    coordinate=path,
                    evidence_type="coverage-debt",
                )
            )
        if self.check_orphans:
            imported: set[str] = set()
            for path in self.root.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                tree = _parse_python(path)
                if tree is None:
                    continue
                try:
                    relative = path.relative_to(self.root).as_posix()
                except ValueError:
                    continue
                imported.update(
                    _resolved_imports(
                        tree,
                        _module_name(relative),
                        relative.endswith("/__init__.py"),
                    )
                )
                imported.update(
                    node.value
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and "." in node.value
                    and " " not in node.value
                )
            for path in sorted(claimed):
                if path.endswith(("/__init__.py", "/__main__.py")):
                    continue
                module = _module_name(path)
                if not any(name == module or name.startswith(f"{module}.") for name in imported):
                    findings.append(
                        Finding(
                            "STR024",
                            "no static consumer; verify dynamic registration before deletion",
                            severity="warning",
                            coordinate=path,
                            evidence_type="orphan-candidate",
                        )
                    )
        evidence = Evidence(
            evidence_id=f"{contract_id}.inventory",
            evidence_type="structure-inventory",
            coordinate=python_root,
            source=self.CHECKER_ID,
            status="mapped" if not findings else "candidate",
            detail="Compared Python production files and navigation candidates with explicit owners",
            provenance=("rust", "python", "cross"),
            metadata={
                "production_files": len(production),
                "claimed_files": len(claimed),
                "allowed_unowned": len(allowed),
                "rust_modules": len(discovered_rust),
                "claimed_rust_modules": len(claimed_rust),
            },
        )
        return LayerResult(
            "structure",
            contract_id,
            (
                Verdict.INCONCLUSIVE
                if findings and all(item.code in COVERAGE_FINDING_CODES for item in findings)
                else Verdict.FAILED
                if findings
                else Verdict.VERIFIED
            ),
            evidence=(evidence,),
            findings=tuple(findings),
        )

    def _check_one(
        self,
        contract: ModuleContract,
        owner_claims: dict[str, list[str]],
        file_claims: dict[str, list[str]],
    ) -> LayerResult:
        findings: list[Finding] = []
        evidence: list[Evidence] = []
        coordinate = contract.rust_coordinate

        required_paths = (
            contract.rust["source"],
            contract.python_owner,
            *contract.python["implementation_files"],
            *contract.fixture_refs,
        )
        for relative in dict.fromkeys(required_paths):
            if not (self.root / relative).is_file():
                findings.append(
                    Finding(
                        "STR001",
                        "contract path does not exist",
                        coordinate=relative,
                        evidence_type="filesystem",
                    )
                )

        owner_ids = owner_claims.get(contract.python_owner, [])
        if len(owner_ids) > 1:
            findings.append(
                Finding(
                    "STR002",
                    f"Python owner is claimed by multiple contracts: {', '.join(owner_ids)}",
                    coordinate=contract.python_owner,
                    evidence_type="ownership",
                )
            )
        for path in contract.python["implementation_files"]:
            claims = file_claims.get(path, [])
            if len(claims) > 1:
                findings.append(
                    Finding(
                        "STR003",
                        f"implementation file has duplicate owners: {', '.join(claims)}",
                        coordinate=path,
                        evidence_type="ownership",
                    )
                )

        owner = PurePosixPath(contract.python_owner)
        implementations = tuple(PurePosixPath(path) for path in contract.python["implementation_files"])
        if contract.python["layout"] == "module-package":
            if owner.name != "__init__.py":
                findings.append(
                    Finding("STR004", "module-package owner must be __init__.py", coordinate=str(owner))
                )
            scattered = [path for path in implementations if owner.parent not in path.parents and path != owner]
            if scattered:
                findings.append(
                    Finding(
                        "STR005",
                        "module-package implementation is scattered outside its owner directory",
                        coordinate=", ".join(map(str, scattered)),
                        evidence_type="containment",
                    )
                )
        elif any(path != owner for path in implementations):
            findings.append(
                Finding(
                    "STR006",
                    "module-file mapping cannot claim separate implementation files",
                    coordinate=contract.python_owner,
                    evidence_type="containment",
                )
            )

        rust_source = self.root / contract.rust["source"]
        if rust_source.is_file():
            rust_text = rust_module_text(rust_source, str(contract.rust["module"]))
            for anchor in contract.rust["anchors"]:
                present = (
                    _contains_module_anchor_text(
                        rust_text,
                        rust_source,
                        anchor,
                        python=False,
                    )
                    if anchor.startswith("module:")
                    else _contains_anchor_text(rust_text, anchor, python=False)
                )
                if not present:
                    findings.append(
                        Finding(
                            "STR007",
                            f"Rust anchor is missing: {anchor}",
                            coordinate=contract.rust["source"],
                            evidence_type="rust-anchor",
                        )
                    )
        python_files = [self.root / path for path in contract.python["implementation_files"]]
        for anchor in contract.python["anchors"]:
            if anchor.startswith("module:"):
                present = _contains_module_anchor(
                    self.root / contract.python_owner,
                    anchor,
                    python=True,
                )
            else:
                present = any(
                    path.is_file() and _contains_anchor(path, anchor, python=True)
                    for path in python_files
                )
            if not present:
                findings.append(
                    Finding(
                        "STR008",
                        f"Python anchor is missing: {anchor}",
                        coordinate=contract.python_owner,
                        evidence_type="python-anchor",
                    )
                )

        if self.check_item_ownership and rust_source.is_file():
            crate_root = next(
                (
                    parent
                    for parent in (rust_source.parent, *rust_source.parents)
                    if (parent / "Cargo.toml").is_file()
                ),
                None,
            )
            if crate_root is not None:
                modules = self._rust_modules(crate_root)
                coordinate_name = _rust_graph_coordinate(str(contract.rust["module"]))
                current = modules.get(coordinate_name)
                if current is not None:
                    child_prefix = f"{coordinate_name}::"
                    child_item_owners: dict[str, list[RustModule]] = {}
                    for name, module in modules.items():
                        if not name.startswith(child_prefix) or (
                            name.count("::") != coordinate_name.count("::") + 1
                        ):
                            continue
                        for item in module.items:
                            child_item_owners.setdefault(item, []).append(module)
                    foreign = (
                        _defined_python_symbols(python_files)
                        & child_item_owners.keys()
                        - set(current.items)
                        - _reexported_names(current.public_uses)
                    )
                    for symbol in sorted(foreign):
                        rust_owner_metadata: list[dict[str, str]] = []
                        for module in child_item_owners[symbol]:
                            rust_owner_metadata.append(
                                {
                                    "module": module.name,
                                    "source": _source_relative_to_root(
                                        module.source, self.root
                                    ),
                                }
                            )
                        rust_owners = ", ".join(
                            f"{owner['module']} ({owner['source']})"
                            for owner in rust_owner_metadata
                        )
                        findings.append(
                            Finding(
                                "STR017",
                                (
                                    "Python owner defines item owned by a Rust child "
                                    f"module: {symbol}; Rust owner: {rust_owners}"
                                ),
                                coordinate=contract.python_owner,
                                evidence_type="item-ownership",
                                metadata={
                                    "python_owner": contract.python_owner,
                                    "symbol": symbol,
                                    "rust_owners": rust_owner_metadata,
                                },
                            )
                        )
        structure = contract.checks["structure"]
        scope_root = (
            self.root / self.python_root
            if self.python_root is not None
            else (self.root / contract.python_owner).parent
        )
        scope_files = tuple(
            path
            for path in scope_root.rglob("*.py")
            if "tests" not in path.relative_to(scope_root).parts
            and "__pycache__" not in path.parts
        ) if scope_root.is_dir() else tuple(python_files)
        owned_symbols = set(structure.get("owned_symbols", ()))
        if owned_symbols:
            owner_set = {path.resolve() for path in python_files}
            locations: dict[str, set[str]] = {symbol: set() for symbol in owned_symbols}
            for path in scope_files:
                symbols = _defined_python_symbols((path,))
                for symbol in owned_symbols & symbols:
                    locations[symbol].add(path.relative_to(self.root).as_posix())
            for symbol in sorted(owned_symbols):
                owner_locations = {
                    path for path in locations[symbol] if (self.root / path).resolve() in owner_set
                }
                if not owner_locations:
                    findings.append(
                        Finding(
                            "STR021",
                            f"owned symbol is not defined by its owner: {symbol}",
                            coordinate=contract.python_owner,
                            evidence_type="item-ownership",
                        )
                    )
                for path in sorted(locations[symbol] - owner_locations):
                    findings.append(
                        Finding(
                            "STR021",
                            f"owned symbol duplicates {contract.python_owner}: {symbol}",
                            coordinate=path,
                            evidence_type="item-ownership",
                        )
                    )
        allowed_dependencies = structure.get("allowed_dependencies")
        if allowed_dependencies is not None:
            scope_relative = scope_root.relative_to(self.root).as_posix()
            package = _module_name(f"{scope_relative}/__init__.py")
            own_modules = {
                _module_name(path.relative_to(self.root).as_posix()) for path in python_files
            }
            allowed = set(allowed_dependencies) | own_modules
            for path in python_files:
                tree = _parse_python(path)
                if tree is None:
                    continue
                relative = path.relative_to(self.root).as_posix()
                internal = {
                    name
                    for name in _resolved_imports(
                        tree,
                        _module_name(relative),
                        relative.endswith("/__init__.py"),
                    )
                    if name == package or name.startswith(f"{package}.")
                }
                disallowed = {
                    name
                    for name in internal
                    if not any(name == prefix or name.startswith(f"{prefix}.") for prefix in allowed)
                }
                if disallowed:
                    findings.append(
                        Finding(
                            "STR022",
                            "imports outside declared dependency boundary: "
                            + ", ".join(sorted(disallowed)),
                            coordinate=relative,
                            evidence_type="dependency-boundary",
                        )
                    )
        restricted = set(structure.get("restricted_decisions", ()))
        if restricted:
            allowed_decision_files = {
                (self.root / path).resolve()
                for path in (*contract.python["implementation_files"], *structure.get("allowed_decision_files", ()))
            }
            for path in scope_files:
                if path.resolve() in allowed_decision_files:
                    continue
                tree = _parse_python(path)
                if tree is None:
                    continue
                overlap = restricted & _decision_literals(tree)
                if overlap:
                    findings.append(
                        Finding(
                            "STR023",
                            "raw decisions owned by "
                            f"{contract.python_owner}: {', '.join(sorted(overlap))}",
                            coordinate=path.relative_to(self.root).as_posix(),
                            evidence_type="decision-ownership",
                        )
                    )
        evidence.append(
            Evidence(
                evidence_id=f"{contract.contract_id}.structure",
                evidence_type="module-ownership",
                coordinate=coordinate,
                source=self.CHECKER_ID,
                status=(MappingStatus.MAPPED if not findings else MappingStatus.CANDIDATE).value,
                detail="Rust and Python coordinates, anchors, ownership, and containment were inspected",
                provenance=("rust", "python", "cross"),
                artifact=contract.source_path.as_posix(),
            )
        )
        if contract.evidence_status == MappingStatus.CANDIDATE and not findings:
            findings.append(
                Finding(
                    "STR009",
                    "candidate mapping cannot be promoted to verified by structure alone",
                    severity="warning",
                    coordinate=coordinate,
                    evidence_type="evidence-status",
                )
            )
            verdict = Verdict.INCONCLUSIVE
        else:
            verdict = Verdict.FAILED if any(item.severity == "error" for item in findings) else Verdict.VERIFIED
        return LayerResult(
            layer="structure",
            contract_id=contract.contract_id,
            verdict=verdict,
            evidence=tuple(evidence),
            findings=tuple(findings),
        )
