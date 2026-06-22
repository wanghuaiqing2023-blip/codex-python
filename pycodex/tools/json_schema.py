"""JSON Schema helpers ported from ``codex-rs/tools/src/json_schema.rs``."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import unquote

JsonValue = Any
DEFINITION_TABLE_KEYS = ("$defs", "definitions")
SCHEMA_CHILD_KEYS = ("items", "anyOf")
MAX_COMPACT_TOOL_SCHEMA_BYTES = 4_000
MAX_COMPACT_TOOL_SCHEMA_DEPTH = 2


class JsonSchemaPrimitiveType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    OBJECT = "object"
    ARRAY = "array"
    NULL = "null"


@dataclass(frozen=True)
class JsonSchemaType:
    types: tuple[JsonSchemaPrimitiveType, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "types", tuple(_coerce_primitive_type(item) for item in self.types))
        if not self.types:
            raise ValueError("JsonSchemaType requires at least one type")

    @classmethod
    def single(cls, schema_type: JsonSchemaPrimitiveType | str) -> "JsonSchemaType":
        return cls((_coerce_primitive_type(schema_type),))

    @classmethod
    def multiple(cls, schema_types: Sequence[JsonSchemaPrimitiveType | str]) -> "JsonSchemaType":
        return cls(tuple(_coerce_primitive_type(item) for item in schema_types))

    def to_json(self) -> str | list[str]:
        if len(self.types) == 1:
            return self.types[0].value
        return [item.value for item in self.types]


@dataclass(frozen=True)
class AdditionalProperties:
    value: bool | "JsonSchema"

    def __post_init__(self) -> None:
        if isinstance(self.value, bool):
            return
        object.__setattr__(self, "value", _coerce_schema(self.value))

    @classmethod
    def boolean(cls, value: bool) -> "AdditionalProperties":
        return cls(value)

    @classmethod
    def schema(cls, value: "JsonSchema" | Mapping[str, JsonValue]) -> "AdditionalProperties":
        return cls(_coerce_schema(value))

    def to_json(self) -> bool | dict[str, JsonValue]:
        if isinstance(self.value, bool):
            return self.value
        return self.value.to_mapping()


@dataclass(frozen=True)
class JsonSchema:
    schema_ref: str | None = None
    schema_type: JsonSchemaType | None = None
    description: str | None = None
    enum_values: tuple[JsonValue, ...] | None = None
    items: "JsonSchema | None" = None
    properties: Mapping[str, "JsonSchema"] | None = None
    required: tuple[str, ...] | None = None
    additional_properties: AdditionalProperties | None = None
    any_of: tuple["JsonSchema", ...] | None = None
    defs: Mapping[str, "JsonSchema"] | None = None
    definitions: Mapping[str, "JsonSchema"] | None = None

    def __post_init__(self) -> None:
        if self.schema_ref is not None:
            object.__setattr__(self, "schema_ref", _ensure_str(self.schema_ref, "schema_ref"))
        if self.schema_type is not None:
            object.__setattr__(self, "schema_type", _coerce_schema_type(self.schema_type))
        if self.description is not None:
            object.__setattr__(self, "description", _ensure_str(self.description, "description"))
        if self.enum_values is not None:
            object.__setattr__(self, "enum_values", tuple(copy.deepcopy(tuple(self.enum_values))))
        if self.items is not None:
            object.__setattr__(self, "items", _coerce_schema(self.items))
        if self.properties is not None:
            object.__setattr__(self, "properties", _coerce_schema_map(self.properties, "properties"))
        if self.required is not None:
            object.__setattr__(self, "required", tuple(_ensure_str(item, "required item") for item in self.required))
        if self.additional_properties is not None and not isinstance(self.additional_properties, AdditionalProperties):
            object.__setattr__(self, "additional_properties", AdditionalProperties(self.additional_properties))
        if self.any_of is not None:
            object.__setattr__(self, "any_of", tuple(_coerce_schema(item) for item in self.any_of))
        if self.defs is not None:
            object.__setattr__(self, "defs", _coerce_schema_map(self.defs, "defs"))
        if self.definitions is not None:
            object.__setattr__(self, "definitions", _coerce_schema_map(self.definitions, "definitions"))

    @classmethod
    def typed(cls, schema_type: JsonSchemaPrimitiveType | str, description: str | None = None) -> "JsonSchema":
        return cls(schema_type=JsonSchemaType.single(schema_type), description=description)

    @classmethod
    def any_of_schema(cls, variants: Sequence["JsonSchema"], description: str | None = None) -> "JsonSchema":
        return cls(description=description, any_of=tuple(variants))

    @classmethod
    def boolean(cls, description: str | None = None) -> "JsonSchema":
        return cls.typed(JsonSchemaPrimitiveType.BOOLEAN, description)

    @classmethod
    def string(cls, description: str | None = None) -> "JsonSchema":
        return cls.typed(JsonSchemaPrimitiveType.STRING, description)

    @classmethod
    def number(cls, description: str | None = None) -> "JsonSchema":
        return cls.typed(JsonSchemaPrimitiveType.NUMBER, description)

    @classmethod
    def integer(cls, description: str | None = None) -> "JsonSchema":
        return cls.typed(JsonSchemaPrimitiveType.INTEGER, description)

    @classmethod
    def null(cls, description: str | None = None) -> "JsonSchema":
        return cls.typed(JsonSchemaPrimitiveType.NULL, description)

    @classmethod
    def string_enum(cls, values: Sequence[JsonValue], description: str | None = None) -> "JsonSchema":
        return cls(
            schema_type=JsonSchemaType.single(JsonSchemaPrimitiveType.STRING),
            description=description,
            enum_values=tuple(copy.deepcopy(tuple(values))),
        )

    @classmethod
    def array(cls, items: "JsonSchema", description: str | None = None) -> "JsonSchema":
        return cls(
            schema_type=JsonSchemaType.single(JsonSchemaPrimitiveType.ARRAY),
            description=description,
            items=items,
        )

    @classmethod
    def object(
        cls,
        properties: Mapping[str, "JsonSchema"] | None = None,
        required: Sequence[str] | None = None,
        additional_properties: AdditionalProperties | bool | "JsonSchema" | None = None,
    ) -> "JsonSchema":
        if additional_properties is not None and not isinstance(additional_properties, AdditionalProperties):
            additional_properties = AdditionalProperties(additional_properties)
        return cls(
            schema_type=JsonSchemaType.single(JsonSchemaPrimitiveType.OBJECT),
            properties={} if properties is None else dict(properties),
            required=None if required is None else tuple(required),
            additional_properties=additional_properties,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "JsonSchema":
        if not isinstance(value, Mapping):
            raise TypeError("JsonSchema must be built from a mapping")
        schema_type = value.get("type")
        return cls(
            schema_ref=_optional_str(value.get("$ref"), "$ref"),
            schema_type=None if schema_type is None else _coerce_schema_type(schema_type),
            description=_optional_str(value.get("description"), "description"),
            enum_values=None if "enum" not in value else tuple(copy.deepcopy(value.get("enum") or ())),
            items=None if "items" not in value else _coerce_schema(value["items"]),
            properties=None
            if "properties" not in value
            else _coerce_schema_map(_ensure_mapping(value["properties"], "properties"), "properties"),
            required=None
            if "required" not in value
            else tuple(_ensure_str(item, "required item") for item in _ensure_sequence(value["required"], "required")),
            additional_properties=None
            if "additionalProperties" not in value
            else _additional_properties_from_json(value["additionalProperties"]),
            any_of=None
            if "anyOf" not in value
            else tuple(_coerce_schema(item) for item in _ensure_sequence(value["anyOf"], "anyOf")),
            defs=None
            if "$defs" not in value
            else _coerce_schema_map(_ensure_mapping(value["$defs"], "$defs"), "$defs"),
            definitions=None
            if "definitions" not in value
            else _coerce_schema_map(_ensure_mapping(value["definitions"], "definitions"), "definitions"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        if self.schema_ref is not None:
            data["$ref"] = self.schema_ref
        if self.schema_type is not None:
            data["type"] = self.schema_type.to_json()
        if self.description is not None:
            data["description"] = self.description
        if self.enum_values is not None:
            data["enum"] = copy.deepcopy(list(self.enum_values))
        if self.items is not None:
            data["items"] = self.items.to_mapping()
        if self.properties is not None:
            data["properties"] = {key: self.properties[key].to_mapping() for key in sorted(self.properties)}
        if self.required is not None:
            data["required"] = list(self.required)
        if self.additional_properties is not None:
            data["additionalProperties"] = self.additional_properties.to_json()
        if self.any_of is not None:
            data["anyOf"] = [item.to_mapping() for item in self.any_of]
        if self.defs is not None:
            data["$defs"] = {key: self.defs[key].to_mapping() for key in sorted(self.defs)}
        if self.definitions is not None:
            data["definitions"] = {key: self.definitions[key].to_mapping() for key in sorted(self.definitions)}
        return data


@dataclass(frozen=True, order=True)
class DefinitionPointer:
    table: str
    name: str


def parse_tool_input_schema(input_schema: JsonValue) -> JsonSchema:
    prepared = prepare_tool_input_schema(input_schema)
    compact_large_tool_schema(prepared)
    return deserialize_tool_input_schema(prepared)


def parse_tool_input_schema_without_compaction(input_schema: JsonValue) -> JsonSchema:
    return deserialize_tool_input_schema(prepare_tool_input_schema(input_schema))


def prepare_tool_input_schema(input_schema: JsonValue) -> JsonValue:
    value = copy.deepcopy(input_schema)
    value = _sanitize_json_schema_value(value)
    prune_unreachable_definitions(value)
    return value


def deserialize_tool_input_schema(input_schema: JsonValue) -> JsonSchema:
    if not isinstance(input_schema, Mapping):
        raise TypeError("tool input schema must normalize to an object")
    schema = JsonSchema.from_mapping(input_schema)
    if schema.schema_type == JsonSchemaType.single(JsonSchemaPrimitiveType.NULL):
        raise ValueError("tool input schema must not be a singleton null type")
    return schema


def compact_large_tool_schema(value: JsonValue) -> None:
    for compaction_pass in (
        strip_schema_descriptions,
        drop_schema_definitions,
        collapse_deep_schema_objects_from_root,
    ):
        if compact_schema_fits_budget(value):
            break
        compaction_pass(value)


def compact_schema_fits_budget(value: JsonValue) -> bool:
    return compact_normalized_schema_len(value) <= MAX_COMPACT_TOOL_SCHEMA_BYTES


def compact_normalized_schema_len(value: JsonValue) -> int:
    try:
        schema = JsonSchema.from_mapping(value)
        normalized = json.dumps(schema.to_mapping(), separators=(",", ":"), sort_keys=True)
        return len(normalized.encode("utf-8"))
    except Exception:
        return 0


def strip_schema_descriptions(value: JsonValue) -> None:
    if isinstance(value, list):
        for item in value:
            strip_schema_descriptions(item)
        return
    if not isinstance(value, dict):
        return
    value.pop("description", None)
    for child in _schema_children_mut(value, include_definitions=True):
        strip_schema_descriptions(child)


def drop_schema_definitions(value: JsonValue) -> None:
    rewrite_definition_refs_to_empty_schemas(value)
    if isinstance(value, dict):
        for key in DEFINITION_TABLE_KEYS:
            value.pop(key, None)


def rewrite_definition_refs_to_empty_schemas(value: JsonValue) -> None:
    if isinstance(value, list):
        for item in value:
            rewrite_definition_refs_to_empty_schemas(item)
        return
    if not isinstance(value, dict):
        return
    ref = value.get("$ref")
    if isinstance(ref, str) and parse_local_definition_ref(ref) is not None:
        value.clear()
        return
    for child in _schema_children_mut(value, include_definitions=False):
        rewrite_definition_refs_to_empty_schemas(child)


def collapse_deep_schema_objects_from_root(value: JsonValue) -> None:
    collapse_deep_schema_objects(value, 0)


def collapse_deep_schema_objects(value: JsonValue, depth: int) -> None:
    if isinstance(value, list):
        for item in value:
            collapse_deep_schema_objects(item, depth)
        return
    if not isinstance(value, dict):
        return
    if depth >= MAX_COMPACT_TOOL_SCHEMA_DEPTH and is_complex_schema_object(value):
        value.clear()
        return
    for child in _schema_children_mut(value, include_definitions=False):
        collapse_deep_schema_objects(child, depth + 1)


def is_complex_schema_object(value: Mapping[str, JsonValue]) -> bool:
    return (
        any(key in value for key in SCHEMA_CHILD_KEYS)
        or "properties" in value
        or "additionalProperties" in value
        or "$ref" in value
    )


def sanitize_json_schema(value: JsonValue) -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            value[index] = _sanitize_json_schema_value(item)
        return
    if not isinstance(value, dict):
        return

    properties = value.get("properties")
    if isinstance(properties, dict):
        for key, child in list(properties.items()):
            properties[key] = _sanitize_json_schema_value(child)
    if "items" in value:
        value["items"] = _sanitize_json_schema_value(value["items"])
    additional_properties = value.get("additionalProperties")
    if additional_properties is not None and not isinstance(additional_properties, bool):
        value["additionalProperties"] = _sanitize_json_schema_value(additional_properties)
    if isinstance(value.get("prefixItems"), list):
        value["prefixItems"] = _sanitize_json_schema_value(value["prefixItems"])
    if "anyOf" in value:
        value["anyOf"] = _sanitize_json_schema_value(value["anyOf"])
    for table in DEFINITION_TABLE_KEYS:
        sanitize_schema_table(value, table)

    if "const" in value:
        value["enum"] = [value.pop("const")]

    schema_types = normalized_schema_types(value)
    if not schema_types and ("$ref" in value or "anyOf" in value):
        return

    if not schema_types:
        if any(key in value for key in ("properties", "required", "additionalProperties")):
            schema_types.append(JsonSchemaPrimitiveType.OBJECT)
        elif "items" in value or "prefixItems" in value:
            schema_types.append(JsonSchemaPrimitiveType.ARRAY)
        elif "enum" in value or "format" in value:
            schema_types.append(JsonSchemaPrimitiveType.STRING)
        elif any(
            key in value
            for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf")
        ):
            schema_types.append(JsonSchemaPrimitiveType.NUMBER)
        else:
            value.clear()
            return

    write_schema_types(value, schema_types)
    ensure_default_children_for_schema_types(value, schema_types)


def sanitize_schema_table(value: dict[str, JsonValue], key: str) -> None:
    table = value.get(key)
    if table is None:
        return
    if not isinstance(table, dict):
        value.pop(key, None)
        return
    for name, definition in list(table.items()):
        table[name] = _sanitize_json_schema_value(definition)


def _sanitize_json_schema_value(value: JsonValue) -> JsonValue:
    if isinstance(value, bool):
        return {"type": "string"}
    if isinstance(value, list):
        return [_sanitize_json_schema_value(item) for item in value]
    if isinstance(value, dict):
        sanitize_json_schema(value)
    return value


def ensure_default_children_for_schema_types(
    value: dict[str, JsonValue],
    schema_types: Sequence[JsonSchemaPrimitiveType],
) -> None:
    if JsonSchemaPrimitiveType.OBJECT in schema_types and "properties" not in value:
        value["properties"] = {}
    if JsonSchemaPrimitiveType.ARRAY in schema_types and "items" not in value:
        value["items"] = {"type": "string"}


def prune_unreachable_definitions(value: JsonValue) -> None:
    reachable = collect_reachable_definitions(value)
    if not isinstance(value, dict):
        return
    for table in DEFINITION_TABLE_KEYS:
        prune_schema_table(value, table, reachable)


def prune_schema_table(
    value: dict[str, JsonValue],
    table: str,
    reachable: set[DefinitionPointer],
) -> None:
    definitions = value.get(table)
    if not isinstance(definitions, dict):
        return
    for name in list(definitions):
        if DefinitionPointer(table, name) not in reachable:
            definitions.pop(name, None)
    if not definitions:
        value.pop(table, None)


def collect_reachable_definitions(value: JsonValue) -> set[DefinitionPointer]:
    reachable: set[DefinitionPointer] = set()
    pending: list[DefinitionPointer] = []
    collect_refs_outside_definitions(value, pending)
    while pending:
        pointer = pending.pop()
        if pointer in reachable:
            continue
        reachable.add(pointer)
        definition = definition_for_pointer(value, pointer)
        if definition is not None:
            collect_refs(definition, pending)
    return reachable


def collect_refs_outside_definitions(value: JsonValue, refs: list[DefinitionPointer]) -> None:
    if isinstance(value, list):
        for item in value:
            collect_refs_outside_definitions(item, refs)
        return
    if not isinstance(value, Mapping):
        return
    collect_ref_from_map(value, refs)
    for child in _schema_children(value, include_definitions=False):
        collect_refs_outside_definitions(child, refs)


def collect_refs(value: JsonValue, refs: list[DefinitionPointer]) -> None:
    if isinstance(value, list):
        for item in value:
            collect_refs(item, refs)
        return
    if not isinstance(value, Mapping):
        return
    collect_ref_from_map(value, refs)
    for item in value.values():
        collect_refs(item, refs)


def collect_ref_from_map(value: Mapping[str, JsonValue], refs: list[DefinitionPointer]) -> None:
    schema_ref = value.get("$ref")
    if isinstance(schema_ref, str):
        pointer = parse_local_definition_ref(schema_ref)
        if pointer is not None:
            refs.append(pointer)


def definition_for_pointer(value: JsonValue, pointer: DefinitionPointer) -> JsonValue | None:
    if not isinstance(value, Mapping):
        return None
    definitions = value.get(pointer.table)
    if not isinstance(definitions, Mapping):
        return None
    return definitions.get(pointer.name)


def parse_local_definition_ref(schema_ref: str) -> DefinitionPointer | None:
    if not schema_ref.startswith("#"):
        return None
    pointer = unquote(schema_ref[1:])
    tokens = _json_pointer_tokens(pointer)
    if len(tokens) < 2 or tokens[0] not in DEFINITION_TABLE_KEYS:
        return None
    return DefinitionPointer(tokens[0], tokens[1])


def normalized_schema_types(value: Mapping[str, JsonValue]) -> list[JsonSchemaPrimitiveType]:
    schema_type = value.get("type")
    if isinstance(schema_type, str):
        primitive = schema_type_from_str(schema_type)
        return [] if primitive is None else [primitive]
    if isinstance(schema_type, list):
        return [primitive for item in schema_type if isinstance(item, str) if (primitive := schema_type_from_str(item))]
    return []


def write_schema_types(value: dict[str, JsonValue], schema_types: Sequence[JsonSchemaPrimitiveType]) -> None:
    if not schema_types:
        value.pop("type", None)
    elif len(schema_types) == 1:
        value["type"] = schema_types[0].value
    else:
        value["type"] = [item.value for item in schema_types]


def schema_type_from_str(schema_type: str) -> JsonSchemaPrimitiveType | None:
    try:
        return JsonSchemaPrimitiveType(schema_type)
    except ValueError:
        return None


def _schema_children(value: Mapping[str, JsonValue], *, include_definitions: bool) -> list[JsonValue]:
    children: list[JsonValue] = []
    properties = value.get("properties")
    if isinstance(properties, Mapping):
        children.extend(properties.values())
    for key in SCHEMA_CHILD_KEYS:
        if key in value:
            children.append(value[key])
    additional_properties = value.get("additionalProperties")
    if additional_properties is not None and not isinstance(additional_properties, bool):
        children.append(additional_properties)
    if include_definitions:
        for key in DEFINITION_TABLE_KEYS:
            definitions = value.get(key)
            if isinstance(definitions, Mapping):
                children.extend(definitions.values())
    return children


def _schema_children_mut(value: dict[str, JsonValue], *, include_definitions: bool) -> list[JsonValue]:
    return _schema_children(value, include_definitions=include_definitions)


def _json_pointer_tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        return []
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]


def _additional_properties_from_json(value: JsonValue) -> AdditionalProperties:
    if isinstance(value, bool):
        return AdditionalProperties.boolean(value)
    return AdditionalProperties.schema(_coerce_schema(value))


def _coerce_schema(value: "JsonSchema" | Mapping[str, JsonValue]) -> JsonSchema:
    if isinstance(value, JsonSchema):
        return value
    return JsonSchema.from_mapping(_ensure_mapping(value, "schema"))


def _coerce_schema_map(value: Mapping[str, Any], field_name: str) -> dict[str, JsonSchema]:
    return {_ensure_str(key, f"{field_name} key"): _coerce_schema(schema) for key, schema in value.items()}


def _coerce_schema_type(value: JsonSchemaType | JsonSchemaPrimitiveType | str | Sequence[str]) -> JsonSchemaType:
    if isinstance(value, JsonSchemaType):
        return value
    if isinstance(value, (JsonSchemaPrimitiveType, str)):
        return JsonSchemaType.single(value)
    if isinstance(value, Sequence):
        return JsonSchemaType.multiple(value)
    raise TypeError("schema type must be a string or sequence of strings")


def _coerce_primitive_type(value: JsonSchemaPrimitiveType | str) -> JsonSchemaPrimitiveType:
    if isinstance(value, JsonSchemaPrimitiveType):
        return value
    if isinstance(value, str):
        return JsonSchemaPrimitiveType(value)
    raise TypeError("schema primitive type must be a string")


def _ensure_mapping(value: JsonValue, field_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object")
    return value


def _ensure_sequence(value: JsonValue, field_name: str) -> Sequence[JsonValue]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be an array")
    return value


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


__all__ = [
    "AdditionalProperties",
    "JsonSchema",
    "JsonSchemaPrimitiveType",
    "JsonSchemaType",
    "parse_tool_input_schema",
    "parse_tool_input_schema_without_compaction",
]
