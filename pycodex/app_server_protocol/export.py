"""Schema export helpers ported from ``export.rs``.

The Rust module combines two different responsibilities:

* pure post-processing helpers for generated TypeScript/JSON schema files; and
* schema emission driven by Rust derive macros from ``ts-rs`` and ``schemars``.

Python mirrors the pure helpers directly and keeps the public generation
entrypoints, but requires explicit generator callbacks for macro-owned schema
emission.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .experimental_api import ExperimentalField, experimental_fields

JsonValue = Any

GENERATED_TS_HEADER = "// GENERATED CODE! DO NOT MODIFY BY HAND!\n\n"
IGNORED_DEFINITIONS = ("Option<()>",)
JSON_V1_ALLOWLIST = ("InitializeParams", "InitializeResponse")
SPECIAL_DEFINITIONS = ("ClientNotification", "ClientRequest", "ServerNotification", "ServerRequest")
FLAT_V2_SHARED_DEFINITIONS = ("ClientRequest", "ServerNotification")
V1_CLIENT_REQUEST_METHODS = ("getConversationSummary", "gitDiffToRemote", "getAuthStatus")
EXCLUDED_SERVER_NOTIFICATION_METHODS_FOR_JSON = ("rawResponseItem/completed",)
DISCRIMINATOR_KEYS = ("type", "method", "mode", "status", "role", "reason")


@dataclass(frozen=True)
class GeneratedSchema:
    namespace: str | None
    logical_name: str
    value: JsonValue
    in_v1_dir: bool = False


@dataclass(frozen=True)
class GenerateTsOptions:
    generate_indices: bool = True
    ensure_headers: bool = True
    run_prettier: bool = True
    experimental_api: bool = False


def generate_types(
    out_dir: str | Path,
    prettier: str | Path | None = None,
    *,
    generate_ts_callback: Callable[[Path, str | Path | None, GenerateTsOptions], None] | None = None,
    generate_json_callback: Callable[[Path, bool], None] | None = None,
) -> None:
    generate_ts(out_dir, prettier, generate_callback=generate_ts_callback)
    generate_json(out_dir, generate_callback=generate_json_callback)


def generate_ts(
    out_dir: str | Path,
    prettier: str | Path | None = None,
    *,
    generate_callback: Callable[[Path, str | Path | None, GenerateTsOptions], None] | None = None,
) -> None:
    generate_ts_with_options(out_dir, prettier, GenerateTsOptions(), generate_callback=generate_callback)


def generate_ts_with_options(
    out_dir: str | Path,
    prettier: str | Path | None,
    options: GenerateTsOptions,
    *,
    generate_callback: Callable[[Path, str | Path | None, GenerateTsOptions], None] | None = None,
) -> None:
    root = Path(out_dir)
    v2_root = root / "v2"
    ensure_dir(root)
    ensure_dir(v2_root)
    if generate_callback is None:
        raise NotImplementedError("TypeScript schema emission is owned by Rust ts-rs derive macros")

    generate_callback(root, prettier, options)
    if not options.experimental_api:
        filter_experimental_ts(root)
    if options.generate_indices:
        generate_index_ts(root)
        generate_index_ts(v2_root)

    ts_files = ts_files_in_recursive(root)
    if options.ensure_headers:
        for path in ts_files:
            prepend_header_if_missing(path)
    if options.run_prettier and prettier is not None and ts_files:
        result = subprocess.run(
            [str(prettier), "--write", "--log-level", "warn", *(str(path) for path in ts_files)],
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Prettier failed with status {result.returncode}")
    trim_trailing_whitespace_in_ts_files(ts_files)


def generate_json(
    out_dir: str | Path,
    *,
    generate_callback: Callable[[Path, bool], Iterable[GeneratedSchema] | JsonValue | None] | None = None,
) -> None:
    generate_json_with_experimental(out_dir, False, generate_callback=generate_callback)


def generate_internal_json_schema(
    out_dir: str | Path,
    *,
    generate_callback: Callable[[Path], JsonValue | None] | None = None,
) -> None:
    root = Path(out_dir)
    ensure_dir(root)
    if generate_callback is None:
        raise NotImplementedError("internal JSON schema emission is owned by Rust schemars derive macros")
    value = generate_callback(root)
    if value is not None:
        write_pretty_json(root / "RolloutLine.json", value)


def generate_json_with_experimental(
    out_dir: str | Path,
    experimental_api: bool,
    *,
    generate_callback: Callable[[Path, bool], Iterable[GeneratedSchema] | JsonValue | None] | None = None,
) -> None:
    root = Path(out_dir)
    ensure_dir(root)
    if generate_callback is None:
        raise NotImplementedError("JSON schema emission is owned by Rust schemars derive macros")

    generated = generate_callback(root, experimental_api)
    if generated is None:
        return
    if isinstance(generated, Mapping):
        bundle = dict(generated)
    else:
        schemas = list(generated)
        bundle = build_schema_bundle(schemas)
    if not experimental_api:
        filter_experimental_schema(bundle)
    write_pretty_json(root / "codex_app_server_protocol.schemas.json", bundle)
    write_pretty_json(root / "codex_app_server_protocol.v2.schemas.json", build_flat_v2_schema(bundle))
    if not experimental_api:
        filter_experimental_json_files(root)


def filter_experimental_ts(out_dir: str | Path, experimental_methods: Iterable[str] = ()) -> None:
    root = Path(out_dir)
    filter_client_request_ts(root, experimental_methods)
    filter_experimental_type_fields_ts(root, experimental_fields())
    remove_generated_type_files(root, experimental_method_types(), "ts")


def filter_experimental_ts_tree(
    tree: MutableMapping[Path, str],
    experimental_methods: Iterable[str] = (),
    experimental_type_names: Iterable[str] = (),
) -> None:
    path = Path("ClientRequest.ts")
    if path in tree:
        tree[path] = filter_client_request_ts_contents(tree[path], experimental_methods)

    fields_by_type_name: dict[str, set[str]] = {}
    for field in experimental_fields():
        fields_by_type_name.setdefault(field.type_name, set()).add(field.field_name)

    for entry_path, content in list(tree.items()):
        type_name = entry_path.stem
        field_names = fields_by_type_name.get(type_name)
        if field_names:
            tree[entry_path] = filter_experimental_type_fields_ts_contents(content, field_names)
    remove_generated_type_entries(tree, set(experimental_type_names) | experimental_method_types(), "ts")


def filter_client_request_ts(out_dir: str | Path, experimental_methods: Iterable[str]) -> None:
    path = Path(out_dir) / "ClientRequest.ts"
    if not path.exists():
        return
    path.write_text(filter_client_request_ts_contents(path.read_text(encoding="utf-8"), experimental_methods), encoding="utf-8")


def filter_client_request_ts_contents(content: str, experimental_methods: Iterable[str]) -> str:
    split = split_type_alias(content)
    if split is None:
        return content
    prefix, body, suffix = split
    experimental = {method for method in experimental_methods if method}
    arms = [
        arm
        for arm in split_top_level(body, "|")
        if (method := extract_method_from_arm(arm)) is None or method not in experimental
    ]
    new_body = " | ".join(arms)
    rewritten = f"{prefix}{new_body}{suffix}"
    usage = split_type_alias(rewritten)
    return prune_unused_type_imports(rewritten, usage[1] if usage else new_body)


def filter_experimental_type_fields_ts(out_dir: str | Path, fields: Iterable[ExperimentalField]) -> None:
    fields_by_type_name: dict[str, set[str]] = {}
    for field in fields:
        fields_by_type_name.setdefault(field.type_name, set()).add(field.field_name)
    if not fields_by_type_name:
        return
    for path in ts_files_in_recursive(out_dir):
        field_names = fields_by_type_name.get(path.stem)
        if not field_names:
            continue
        path.write_text(filter_experimental_type_fields_ts_contents(path.read_text(encoding="utf-8"), field_names), encoding="utf-8")


def filter_experimental_type_fields_ts_contents(content: str, experimental_field_names: Iterable[str]) -> str:
    span = type_body_brace_span(content)
    if span is None:
        return content
    field_names = set(experimental_field_names)
    open_brace, close_brace = span
    inner = content[open_brace + 1 : close_brace]
    fields = [
        field
        for field in split_top_level_multi(inner, [",", ";"])
        if (name := parse_property_name(strip_leading_block_comments(field))) is None or name not in field_names
    ]
    new_inner = ", ".join(fields)
    rewritten = f"{content[: open_brace + 1]}{new_inner}{content[close_brace:]}"
    usage = split_type_alias(rewritten)
    return prune_unused_type_imports(rewritten, usage[1] if usage else new_inner)


def filter_experimental_schema(bundle: JsonValue, fields: Iterable[ExperimentalField] | None = None, experimental_methods: Iterable[str] = ()) -> None:
    registered = list(experimental_fields() if fields is None else fields)
    filter_experimental_fields_in_root(bundle, registered)
    filter_experimental_fields_in_definitions(bundle, registered)
    prune_experimental_methods(bundle, experimental_methods)
    remove_experimental_method_type_definitions(bundle)


def filter_experimental_fields_in_root(schema: JsonValue, fields: Iterable[ExperimentalField]) -> None:
    if not isinstance(schema, MutableMapping):
        return
    title = schema.get("title")
    if not isinstance(title, str):
        return
    for field in fields:
        if title == field.type_name:
            remove_property_from_schema(schema, field.field_name)


def filter_experimental_fields_in_definitions(bundle: JsonValue, fields: Iterable[ExperimentalField]) -> None:
    if not isinstance(bundle, MutableMapping):
        return
    definitions = bundle.get("definitions")
    if isinstance(definitions, MutableMapping):
        filter_experimental_fields_in_definitions_map(definitions, fields)


def filter_experimental_fields_in_definitions_map(definitions: MutableMapping[str, JsonValue], fields: Iterable[ExperimentalField]) -> None:
    for def_name, def_schema in list(definitions.items()):
        if is_namespace_map(def_schema):
            filter_experimental_fields_in_definitions_map(def_schema, fields)
            continue
        for field in fields:
            if definition_matches_type(def_name, field.type_name):
                remove_property_from_schema(def_schema, field.field_name)


def is_namespace_map(value: JsonValue) -> bool:
    if not isinstance(value, Mapping):
        return False
    if any(str(key).startswith("$") for key in value):
        return False
    looks_like_schema = any(key in value for key in ("type", "properties", "anyOf", "oneOf", "allOf"))
    return not looks_like_schema and all(isinstance(child, Mapping) for child in value.values())


def definition_matches_type(def_name: str, type_name: str) -> bool:
    return def_name == type_name or def_name.endswith(f"::{type_name}")


def remove_property_from_schema(schema: JsonValue, field_name: str) -> None:
    if not isinstance(schema, MutableMapping):
        return
    properties = schema.get("properties")
    if isinstance(properties, MutableMapping):
        properties.pop(field_name, None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [entry for entry in required if entry != field_name]
    if "schema" in schema:
        remove_property_from_schema(schema["schema"], field_name)


def prune_experimental_methods(bundle: JsonValue, experimental_methods: Iterable[str]) -> None:
    methods = {method for method in experimental_methods if method}
    prune_experimental_methods_inner(bundle, methods)


def prune_experimental_methods_inner(value: JsonValue, experimental_methods: set[str]) -> None:
    if isinstance(value, list):
        value[:] = [item for item in value if not is_experimental_method_variant(item, experimental_methods)]
        for item in value:
            prune_experimental_methods_inner(item, experimental_methods)
    elif isinstance(value, MutableMapping):
        for child in value.values():
            prune_experimental_methods_inner(child, experimental_methods)


def is_experimental_method_variant(value: JsonValue, experimental_methods: set[str]) -> bool:
    if not isinstance(value, Mapping):
        return False
    properties = value.get("properties")
    if not isinstance(properties, Mapping):
        return False
    method_schema = properties.get("method")
    if not isinstance(method_schema, Mapping):
        return False
    method = method_schema.get("const")
    if isinstance(method, str):
        return method in experimental_methods
    values = method_schema.get("enum")
    return isinstance(values, list) and len(values) == 1 and values[0] in experimental_methods


def filter_experimental_json_files(out_dir: str | Path, experimental_methods: Iterable[str] = ()) -> None:
    for path in json_files_in_recursive(out_dir):
        value = read_json_value(path)
        filter_experimental_schema(value, experimental_methods=experimental_methods)
        write_pretty_json(path, value)
    remove_generated_type_files(out_dir, experimental_method_types(), "json")


def experimental_method_types(entries: Iterable[str] = ()) -> set[str]:
    out: set[str] = set()
    collect_experimental_type_names(entries, out)
    return out


def collect_experimental_type_names(entries: Iterable[str], out: set[str]) -> None:
    for entry in entries:
        trimmed = entry.strip()
        if not trimmed:
            continue
        name = trimmed.rsplit("::", 1)[-1]
        if name:
            out.add(name)


def remove_generated_type_files(out_dir: str | Path, type_names: Iterable[str], extension: str) -> None:
    root = Path(out_dir)
    for type_name in type_names:
        for subdir in ("", "v1", "v2"):
            path = (root / subdir / f"{type_name}.{extension}") if subdir else (root / f"{type_name}.{extension}")
            if path.exists():
                path.unlink()


def remove_generated_type_entries(tree: MutableMapping[Path, str], type_names: Iterable[str], extension: str) -> None:
    for type_name in type_names:
        for subdir in ("", "v1", "v2"):
            path = (Path(subdir) / f"{type_name}.{extension}") if subdir else Path(f"{type_name}.{extension}")
            tree.pop(path, None)


def remove_experimental_method_type_definitions(bundle: JsonValue, experimental_type_names: Iterable[str] = ()) -> None:
    if not isinstance(bundle, MutableMapping):
        return
    definitions = bundle.get("definitions")
    if isinstance(definitions, MutableMapping):
        remove_experimental_method_type_definitions_map(definitions, set(experimental_type_names) | experimental_method_types())


def remove_experimental_method_type_definitions_map(definitions: MutableMapping[str, JsonValue], experimental_type_names: set[str]) -> None:
    for key in [
        name
        for name in definitions
        if any(definition_matches_type(name, type_name) for type_name in experimental_type_names)
    ]:
        definitions.pop(key, None)
    for value in list(definitions.values()):
        if is_namespace_map(value):
            remove_experimental_method_type_definitions_map(value, experimental_type_names)


def prune_unused_type_imports(content: str, type_alias_body: str) -> str:
    trailing_newline = content.endswith("\n")
    lines = []
    for line in content.splitlines():
        type_name = parse_imported_type_name(line)
        if type_name is not None and type_name not in type_alias_body:
            continue
        lines.append(line)
    rewritten = "\n".join(lines)
    if trailing_newline:
        rewritten += "\n"
    return rewritten


def parse_imported_type_name(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("import type {"):
        return None
    rest = stripped[len("import type {") :]
    if "} from " not in rest:
        return None
    type_name = rest.split("} from ", 1)[0].strip()
    if not type_name or "," in type_name or " as " in type_name:
        return None
    return type_name


def json_files_in_recursive(dir_path: str | Path) -> list[Path]:
    root = Path(dir_path)
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix == ".json")


def read_json_value(path: str | Path) -> JsonValue:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def split_type_alias(content: str) -> tuple[str, str, str] | None:
    eq_index = content.find("=")
    semi_index = content.rfind(";")
    if eq_index < 0 or semi_index <= eq_index:
        return None
    return content[: eq_index + 1], content[eq_index + 1 : semi_index], content[semi_index:]


def type_body_brace_span(content: str) -> tuple[int, int] | None:
    eq_index = content.find("=")
    if eq_index >= 0:
        span = find_top_level_brace_span(content[eq_index + 1 :])
        return None if span is None else (eq_index + 1 + span[0], eq_index + 1 + span[1])
    marker = "export interface"
    interface_index = content.find(marker)
    if interface_index < 0:
        return None
    span = find_top_level_brace_span(content[interface_index + len(marker) :])
    return None if span is None else (interface_index + len(marker) + span[0], interface_index + len(marker) + span[1])


def find_top_level_brace_span(input_text: str) -> tuple[int, int] | None:
    state = _ScanState()
    open_index: int | None = None
    for index, ch in enumerate(input_text):
        if not state.in_ignored_syntax() and ch == "{" and state.is_top_level():
            open_index = index
        state.observe(ch)
        if not state.in_ignored_syntax() and ch == "}" and state.is_top_level() and open_index is not None:
            return open_index, index
    return None


def split_top_level(input_text: str, delimiter: str) -> list[str]:
    return split_top_level_multi(input_text, [delimiter])


def split_top_level_multi(input_text: str, delimiters: Iterable[str]) -> list[str]:
    delimiter_set = set(delimiters)
    state = _ScanState()
    start = 0
    parts: list[str] = []
    for index, ch in enumerate(input_text):
        if not state.in_ignored_syntax() and state.is_top_level() and ch in delimiter_set:
            part = input_text[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1
        state.observe(ch)
    tail = input_text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def extract_method_from_arm(arm: str) -> str | None:
    span = find_top_level_brace_span(arm)
    if span is None:
        return None
    inner = arm[span[0] + 1 : span[1]]
    for field in split_top_level(inner, ","):
        parsed = parse_property(field)
        if parsed is None:
            continue
        name, value = parsed
        if name == "method":
            literal = parse_string_literal(value.lstrip())
            return literal[0] if literal else None
    return None


def parse_property(input_text: str) -> tuple[str, str] | None:
    name = parse_property_name(input_text)
    if name is None or ":" not in input_text:
        return None
    return name, input_text.split(":", 1)[1].lstrip()


def strip_leading_block_comments(input_text: str) -> str:
    rest = input_text.lstrip()
    while rest.startswith("/*"):
        end = rest.find("*/", 2)
        if end < 0:
            return rest
        rest = rest[end + 2 :].lstrip()
    return rest


def parse_property_name(input_text: str) -> str | None:
    trimmed = input_text.lstrip()
    if not trimmed:
        return None
    literal = parse_string_literal(trimmed)
    if literal is not None:
        value, consumed = literal
        return value if trimmed[consumed:].lstrip().startswith(":") else None
    end = 0
    for index, ch in enumerate(trimmed):
        if not is_ident_char(ch):
            break
        end = index + 1
    if end == 0:
        return None
    name = trimmed[:end]
    rest = trimmed[end:].lstrip()
    if rest.startswith("?"):
        rest = rest[1:].lstrip()
    return name if rest.startswith(":") else None


def parse_string_literal(input_text: str) -> tuple[str, int] | None:
    if not input_text or input_text[0] not in ("'", '"'):
        return None
    quote = input_text[0]
    escape = False
    for index, ch in enumerate(input_text[1:], start=1):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == quote:
            return input_text[1:index], index + 1
    return None


def is_ident_char(ch: str) -> bool:
    return ch.isascii() and (ch.isalnum() or ch == "_")


@dataclass
class _ScanState:
    brace: int = 0
    bracket: int = 0
    paren: int = 0
    angle: int = 0
    string_delim: str | None = None
    escape: bool = False
    block_comment: bool = False
    line_comment: bool = False
    previous_char: str | None = None

    def observe(self, ch: str) -> None:
        if self.line_comment:
            if ch == "\n":
                self.line_comment = False
            self.previous_char = ch
            return
        if self.block_comment:
            if self.previous_char == "*" and ch == "/":
                self.block_comment = False
                self.previous_char = None
            else:
                self.previous_char = ch
            return
        if self.string_delim is not None:
            if self.escape:
                self.escape = False
                self.previous_char = ch
                return
            if ch == "\\":
                self.escape = True
                self.previous_char = ch
                return
            if ch == self.string_delim:
                self.string_delim = None
            self.previous_char = ch
            return
        if self.previous_char == "/" and ch == "/":
            self.line_comment = True
            self.previous_char = ch
            return
        if self.previous_char == "/" and ch == "*":
            self.block_comment = True
            self.previous_char = ch
            return
        if ch in ("'", '"'):
            self.string_delim = ch
        elif ch == "{":
            self.brace += 1
        elif ch == "}":
            self.brace = max(0, self.brace - 1)
        elif ch == "[":
            self.bracket += 1
        elif ch == "]":
            self.bracket = max(0, self.bracket - 1)
        elif ch == "(":
            self.paren += 1
        elif ch == ")":
            self.paren = max(0, self.paren - 1)
        elif ch == "<":
            self.angle += 1
        elif ch == ">" and self.angle > 0:
            self.angle -= 1
        self.previous_char = ch

    def in_ignored_syntax(self) -> bool:
        return self.string_delim is not None or self.block_comment or self.line_comment

    def is_top_level(self) -> bool:
        return self.brace == 0 and self.bracket == 0 and self.paren == 0 and self.angle == 0


def build_schema_bundle(schemas: Iterable[GeneratedSchema]) -> dict[str, JsonValue]:
    schema_list = list(schemas)
    namespaced_types = collect_namespaced_types(schema_list)
    definitions: dict[str, JsonValue] = {}
    for schema in schema_list:
        if schema.logical_name in IGNORED_DEFINITIONS:
            continue
        value = _deepcopy_json(schema.value)
        if schema.namespace is not None:
            rewrite_refs_to_namespace(value, schema.namespace)
        else:
            rewrite_refs_to_known_namespaces(value, namespaced_types)
        forced_namespace_refs: list[tuple[str, str]] = []
        defs = value.pop("definitions", None) if isinstance(value, MutableMapping) else None
        if isinstance(defs, Mapping):
            for def_name, def_schema in defs.items():
                if def_name in IGNORED_DEFINITIONS or def_name in SPECIAL_DEFINITIONS:
                    continue
                def_schema = _deepcopy_json(def_schema)
                annotate_schema(def_schema, def_name)
                target_ns = schema.namespace or (namespace_for_definition(def_name, namespaced_types) if not schema.in_v1_dir else None)
                if target_ns is not None:
                    if schema.namespace == target_ns:
                        rewrite_refs_to_namespace(def_schema, target_ns)
                        insert_into_namespace(definitions, target_ns, def_name, def_schema)
                    elif (def_name, target_ns) not in forced_namespace_refs:
                        forced_namespace_refs.append((def_name, target_ns))
                else:
                    definitions[def_name] = def_schema
        for name, namespace in forced_namespace_refs:
            rewrite_named_ref_to_namespace(value, namespace, name)
        if schema.namespace is not None:
            insert_into_namespace(definitions, schema.namespace, schema.logical_name, value)
        else:
            definitions[schema.logical_name] = value
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "CodexAppServerProtocol",
        "type": "object",
        "definitions": definitions,
    }


def build_flat_v2_schema(bundle: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    definitions = bundle.get("definitions")
    if not isinstance(definitions, Mapping):
        raise ValueError("expected bundle definitions map")
    v2_definitions = definitions.get("v2")
    if not isinstance(v2_definitions, Mapping):
        raise ValueError("expected v2 namespace in bundle definitions")
    flat_definitions = dict(v2_definitions)
    shared_definitions: dict[str, JsonValue] = {}
    non_v2_refs: set[str] = set()
    for shared in FLAT_V2_SHARED_DEFINITIONS:
        shared_schema = definitions.get(shared)
        if shared_schema is None:
            continue
        shared_definitions[shared] = _deepcopy_json(shared_schema)
        non_v2_refs.update(collect_non_v2_refs(shared_schema))
    for name in collect_definition_dependencies(definitions, non_v2_refs):
        if name != "v2" and name not in flat_definitions and name in definitions:
            flat_definitions[name] = _deepcopy_json(definitions[name])
    flat_definitions.update(shared_definitions)
    flat_root = dict(bundle)
    flat_root["title"] = f"{bundle.get('title', 'CodexAppServerProtocol')}V2"
    flat_root["definitions"] = flat_definitions
    rewrite_ref_prefix(flat_root, "#/definitions/v2/", "#/definitions/")
    ensure_no_ref_prefix(flat_root, "#/definitions/v2/", "flat v2")
    ensure_referenced_definitions_present(flat_root, "flat v2")
    return flat_root


def collect_non_v2_refs(value: JsonValue) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, Mapping):
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/definitions/") and not reference.startswith("#/definitions/v2/"):
            refs.add(reference.removeprefix("#/definitions/"))
        for child in value.values():
            refs.update(collect_non_v2_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(collect_non_v2_refs(child))
    return refs


def collect_definition_dependencies(definitions: Mapping[str, JsonValue], names: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    to_process = list(names)
    while to_process:
        name = to_process.pop()
        if name in seen:
            continue
        seen.add(name)
        schema = definitions.get(name)
        if schema is None:
            continue
        for dep in collect_non_v2_refs(schema):
            if dep not in seen:
                to_process.append(dep)
    return seen


def rewrite_ref_prefix(value: JsonValue, prefix: str, replacement: str) -> None:
    if isinstance(value, MutableMapping):
        reference = value.get("$ref")
        if isinstance(reference, str):
            value["$ref"] = reference.replace(prefix, replacement)
        for child in value.values():
            rewrite_ref_prefix(child, prefix, replacement)
    elif isinstance(value, list):
        for child in value:
            rewrite_ref_prefix(child, prefix, replacement)


def ensure_no_ref_prefix(value: JsonValue, prefix: str, label: str) -> None:
    reference = first_ref_with_prefix(value, prefix)
    if reference is not None:
        raise ValueError(f"{label} schema still references namespaced definitions; found {reference}")


def first_ref_with_prefix(value: JsonValue, prefix: str) -> str | None:
    if isinstance(value, Mapping):
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith(prefix):
            return reference
        for child in value.values():
            found = first_ref_with_prefix(child, prefix)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = first_ref_with_prefix(child, prefix)
            if found is not None:
                return found
    return None


def ensure_referenced_definitions_present(schema: Mapping[str, JsonValue], label: str) -> None:
    definitions = schema.get("definitions")
    if not isinstance(definitions, Mapping):
        raise ValueError(f"expected definitions map in {label} schema")
    missing: set[str] = set()
    collect_missing_definitions(schema, definitions, missing)
    if missing:
        raise ValueError(f"{label} schema missing definitions: {', '.join(sorted(missing))}")


def collect_missing_definitions(value: JsonValue, definitions: Mapping[str, JsonValue], missing: set[str]) -> None:
    if isinstance(value, Mapping):
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/definitions/"):
            name = reference.removeprefix("#/definitions/").split("/", 1)[0]
            if name not in definitions:
                missing.add(name)
        for child in value.values():
            collect_missing_definitions(child, definitions, missing)
    elif isinstance(value, list):
        for child in value:
            collect_missing_definitions(child, definitions, missing)


def insert_into_namespace(definitions: MutableMapping[str, JsonValue], namespace: str, name: str, schema: JsonValue) -> None:
    entry = definitions.setdefault(namespace, {})
    if not isinstance(entry, MutableMapping):
        raise ValueError(f"expected namespace {namespace} to be an object")
    insert_definition(entry, name, schema, f"namespace `{namespace}`")


def insert_definition(definitions: MutableMapping[str, JsonValue], name: str, schema: JsonValue, location: str) -> None:
    existing = definitions.get(name)
    if existing is not None:
        if existing == schema:
            return
        existing_title = existing.get("title", "<untitled>") if isinstance(existing, Mapping) else "<untitled>"
        new_title = schema.get("title", "<untitled>") if isinstance(schema, Mapping) else "<untitled>"
        raise ValueError(f"schema definition collision in {location}: {name} (existing title: {existing_title}, new title: {new_title})")
    definitions[name] = schema


def split_namespace(name: str) -> tuple[str | None, str]:
    if "::" not in name:
        return None, name
    namespace, logical = name.split("::", 1)
    return namespace, logical


def rewrite_refs_to_namespace(value: JsonValue, namespace: str) -> None:
    if isinstance(value, MutableMapping):
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/definitions/"):
            suffix = reference.removeprefix("#/definitions/")
            if not suffix.startswith(f"{namespace}/"):
                value["$ref"] = f"#/definitions/{namespace}/{suffix}"
        for child in value.values():
            rewrite_refs_to_namespace(child, namespace)
    elif isinstance(value, list):
        for child in value:
            rewrite_refs_to_namespace(child, namespace)


def rewrite_refs_to_known_namespaces(value: JsonValue, types: Mapping[str, str]) -> None:
    if isinstance(value, MutableMapping):
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/definitions/"):
            suffix = reference.removeprefix("#/definitions/")
            name, _, tail = suffix.partition("/")
            namespace = namespace_for_definition(name, types)
            if namespace:
                value["$ref"] = f"#/definitions/{namespace}/{name}{('/' + tail) if tail else ''}"
        for child in value.values():
            rewrite_refs_to_known_namespaces(child, types)
    elif isinstance(value, list):
        for child in value:
            rewrite_refs_to_known_namespaces(child, types)


def collect_namespaced_types(schemas: Iterable[GeneratedSchema]) -> dict[str, str]:
    types: dict[str, str] = {}
    for schema in schemas:
        if schema.namespace is None:
            continue
        types.setdefault(schema.logical_name, schema.namespace)
        if isinstance(schema.value, Mapping):
            for defs_key in ("definitions", "$defs"):
                defs = schema.value.get(defs_key)
                if isinstance(defs, Mapping):
                    for key in defs:
                        types.setdefault(str(key), schema.namespace)
    return types


def namespace_for_definition(name: str, types: Mapping[str, str]) -> str | None:
    if name in types:
        return types[name]
    trimmed = name.rstrip("0123456789")
    return types.get(trimmed) if trimmed != name else None


def variant_definition_name(base: str, variant: JsonValue) -> str | None:
    if isinstance(variant, Mapping):
        props = variant.get("properties")
        if isinstance(props, Mapping):
            if (method := literal_from_property(props, "method")) is not None:
                pascal = to_pascal_case(method)
                if base in ("ClientRequest", "ServerRequest"):
                    return f"{pascal}Request"
                if base in ("ClientNotification", "ServerNotification"):
                    return f"{pascal}Notification"
                return f"{pascal}{base}"
            if (type_literal := literal_from_property(props, "type")) is not None:
                pascal = to_pascal_case(type_literal)
                return f"{pascal}EventMsg" if base == "EventMsg" else f"{pascal}{base}"
            if len(props) == 1:
                key = next(iter(props))
                literal = string_literal(props[key])
                return f"{to_pascal_case(literal or str(key))}{base}"
        required = variant.get("required")
        if isinstance(required, list) and len(required) == 1 and isinstance(required[0], str):
            return f"{to_pascal_case(required[0])}{base}"
    return None


def literal_from_property(props: Mapping[str, JsonValue], key: str) -> str | None:
    return string_literal(props.get(key))


def string_literal(value: JsonValue) -> str | None:
    if isinstance(value, Mapping):
        const = value.get("const")
        if isinstance(const, str):
            return const
        enum = value.get("enum")
        if isinstance(enum, list) and enum and isinstance(enum[0], str):
            return enum[0]
    return None


def annotate_schema(value: JsonValue, base: str | None = None) -> None:
    if isinstance(value, MutableMapping):
        annotate_object(value, base)
    elif isinstance(value, list):
        for item in value:
            annotate_schema(item, base)


def annotate_object(map_value: MutableMapping[str, JsonValue], base: str | None = None) -> None:
    owner = map_value.get("title")
    props = map_value.get("properties")
    if isinstance(owner, str) and isinstance(props, MutableMapping):
        set_discriminator_titles(props, owner)
    for key in ("oneOf", "anyOf"):
        variants = map_value.get(key)
        if isinstance(variants, list):
            annotate_variant_list(variants, base)
    for defs_key in ("definitions", "$defs"):
        defs = map_value.get(defs_key)
        if isinstance(defs, MutableMapping):
            for name, schema in defs.items():
                annotate_schema(schema, str(name))
    if isinstance(props, MutableMapping):
        for child in props.values():
            annotate_schema(child, base)
    for key in ("items", "additionalProperties"):
        if key in map_value:
            annotate_schema(map_value[key], base)
    for key, child in list(map_value.items()):
        if key not in ("oneOf", "anyOf", "definitions", "$defs", "properties", "items", "additionalProperties"):
            annotate_schema(child, base)


def annotate_variant_list(variants: list[JsonValue], base: str | None = None) -> None:
    seen = {title for variant in variants if (title := variant_title(variant)) is not None}
    for variant in variants:
        variant_name = variant_title(variant)
        if variant_name is None and base is not None:
            generated = variant_definition_name(base, variant)
            if generated is not None:
                if generated in seen:
                    raise ValueError(f"Variant title naming collision detected: {variant_title_collision_key(base, generated, variant)}")
                if isinstance(variant, MutableMapping):
                    variant["title"] = generated
                seen.add(generated)
                variant_name = generated
        if variant_name is not None and isinstance(variant, MutableMapping):
            props = variant.get("properties")
            if isinstance(props, MutableMapping):
                set_discriminator_titles(props, variant_name)
        annotate_schema(variant, base)


def variant_title_collision_key(base: str, generated_name: str, variant: JsonValue) -> str:
    parts = [f"base={base}", f"generated={generated_name}"]
    if isinstance(variant, Mapping):
        props = variant.get("properties")
        if isinstance(props, Mapping):
            for key in DISCRIMINATOR_KEYS:
                if (literal := literal_from_property(props, key)) is not None:
                    parts.append(f"{key}={literal}")
            for key, value in props.items():
                if key not in DISCRIMINATOR_KEYS and (literal := string_literal(value)) is not None:
                    parts.append(f"literal:{key}={literal}")
            if len(props) == 1:
                parts.append(f"only_property={next(iter(props))}")
        required = variant.get("required")
        if isinstance(required, list) and len(required) == 1 and isinstance(required[0], str):
            parts.append(f"required_only={required[0]}")
    if len(parts) == 2:
        parts.append(f"variant={variant}")
    return "|".join(parts)


def set_discriminator_titles(props: MutableMapping[str, JsonValue], owner: str) -> None:
    for key in DISCRIMINATOR_KEYS:
        prop_schema = props.get(key)
        if isinstance(prop_schema, MutableMapping) and string_literal(prop_schema) is not None and "title" not in prop_schema:
            prop_schema["title"] = f"{owner}{to_pascal_case(key)}"


def variant_title(value: JsonValue) -> str | None:
    return value.get("title") if isinstance(value, Mapping) and isinstance(value.get("title"), str) else None


def to_pascal_case(input_text: str) -> str:
    result: list[str] = []
    capitalize_next = True
    for ch in input_text:
        if ch in ("_", "-"):
            capitalize_next = True
            continue
        if capitalize_next:
            result.append(ch.upper())
            capitalize_next = False
        else:
            result.append(ch)
    return "".join(result)


def ensure_dir(dir_path: str | Path) -> None:
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def rewrite_named_ref_to_namespace(value: JsonValue, namespace: str, name: str) -> None:
    direct = f"#/definitions/{name}"
    prefixed = f"{direct}/"
    if isinstance(value, MutableMapping):
        reference = value.get("$ref")
        if isinstance(reference, str):
            if reference == direct:
                value["$ref"] = f"#/definitions/{namespace}/{name}"
            elif reference.startswith(prefixed):
                value["$ref"] = f"#/definitions/{namespace}/{name}/{reference[len(prefixed):]}"
        for child in value.values():
            rewrite_named_ref_to_namespace(child, namespace, name)
    elif isinstance(value, list):
        for child in value:
            rewrite_named_ref_to_namespace(child, namespace, name)


def prepend_header_if_missing(path: str | Path) -> None:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    if not content.startswith(GENERATED_TS_HEADER):
        file_path.write_text(GENERATED_TS_HEADER + content, encoding="utf-8")


def ts_files_in(dir_path: str | Path) -> list[Path]:
    root = Path(dir_path)
    return sorted(path for path in root.iterdir() if path.is_file() and path.suffix == ".ts")


def ts_files_in_recursive(dir_path: str | Path) -> list[Path]:
    root = Path(dir_path)
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix == ".ts")


def trim_trailing_whitespace_in_ts_files(paths: Iterable[str | Path]) -> None:
    for path in paths:
        file_path = Path(path)
        content = file_path.read_text(encoding="utf-8")
        trimmed = trim_trailing_line_whitespace(content)
        if trimmed != content:
            file_path.write_text(trimmed, encoding="utf-8")


def trim_trailing_line_whitespace(content: str) -> str:
    parts = content.splitlines(keepends=True)
    if not parts:
        return ""
    return "".join(part[:-1].rstrip(" \t") + "\n" if part.endswith("\n") else part.rstrip(" \t") for part in parts)


def generate_index_ts(out_dir: str | Path) -> Path:
    root = Path(out_dir)
    entries = index_ts_entries(ts_files_in(root), (root / "v2").is_dir() and bool(ts_files_in(root / "v2")))
    content = generated_index_ts_with_header(entries)
    index_path = root / "index.ts"
    index_path.write_text(content, encoding="utf-8")
    return index_path


def generate_index_ts_tree(tree: MutableMapping[Path, str]) -> None:
    root_entries = [path for path in tree if len(path.parts) == 1]
    has_v2_ts = any(path.parent == Path("v2") and path.suffix == ".ts" and path.stem != "index" for path in tree)
    tree[Path("index.ts")] = index_ts_entries(root_entries, has_v2_ts)
    v2_entries = [path for path in tree if path.parent == Path("v2")]
    if v2_entries:
        tree[Path("v2") / "index.ts"] = index_ts_entries(v2_entries, False)


def generated_index_ts_with_header(content: str) -> str:
    return GENERATED_TS_HEADER + content


def index_ts_entries(paths: Iterable[str | Path], has_v2_ts: bool) -> str:
    stems = sorted({Path(path).stem for path in paths if Path(path).suffix == ".ts" and Path(path).stem not in ("index", "EventMsg")})
    entries = "".join(f'export type {{ {name} }} from "./{name}";\n' for name in stems)
    if has_v2_ts:
        entries += 'export * as v2 from "./v2";\n'
    return entries


def write_pretty_json(path: str | Path, value: JsonValue) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _deepcopy_json(value: JsonValue) -> JsonValue:
    return json.loads(json.dumps(value))


__all__ = [
    "DISCRIMINATOR_KEYS",
    "EXCLUDED_SERVER_NOTIFICATION_METHODS_FOR_JSON",
    "FLAT_V2_SHARED_DEFINITIONS",
    "GENERATED_TS_HEADER",
    "IGNORED_DEFINITIONS",
    "JSON_V1_ALLOWLIST",
    "SPECIAL_DEFINITIONS",
    "V1_CLIENT_REQUEST_METHODS",
    "GeneratedSchema",
    "GenerateTsOptions",
    "annotate_schema",
    "build_flat_v2_schema",
    "build_schema_bundle",
    "collect_definition_dependencies",
    "collect_experimental_type_names",
    "collect_namespaced_types",
    "collect_non_v2_refs",
    "definition_matches_type",
    "ensure_dir",
    "ensure_no_ref_prefix",
    "ensure_referenced_definitions_present",
    "experimental_method_types",
    "filter_client_request_ts_contents",
    "filter_experimental_schema",
    "filter_experimental_ts_tree",
    "filter_experimental_type_fields_ts_contents",
    "find_top_level_brace_span",
    "first_ref_with_prefix",
    "generate_index_ts_tree",
    "generate_index_ts",
    "generate_internal_json_schema",
    "generate_json",
    "generate_json_with_experimental",
    "generate_ts",
    "generate_ts_with_options",
    "generate_types",
    "generated_index_ts_with_header",
    "index_ts_entries",
    "insert_definition",
    "insert_into_namespace",
    "is_namespace_map",
    "parse_imported_type_name",
    "prepend_header_if_missing",
    "parse_property_name",
    "prune_experimental_methods",
    "prune_unused_type_imports",
    "remove_generated_type_entries",
    "remove_generated_type_files",
    "remove_property_from_schema",
    "rewrite_ref_prefix",
    "rewrite_refs_to_known_namespaces",
    "rewrite_refs_to_namespace",
    "split_namespace",
    "split_top_level",
    "split_top_level_multi",
    "ts_files_in",
    "ts_files_in_recursive",
    "to_pascal_case",
    "trim_trailing_line_whitespace",
    "trim_trailing_whitespace_in_ts_files",
    "variant_definition_name",
    "write_pretty_json",
]
