"""JSON-schema projection from Rust ``memories/src/schema.rs``."""

from __future__ import annotations

import copy
from dataclasses import fields, is_dataclass
from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints


def input_schema_for(value_type: type[Any] | dict[str, Any]) -> dict[str, Any]:
    return schema_for(value_type, option_add_null_type=False)


def output_schema_for(value_type: type[Any] | dict[str, Any]) -> dict[str, Any]:
    return schema_for(value_type, option_add_null_type=True)


def schema_for(
    value_type: type[Any] | dict[str, Any],
    option_add_null_type: bool,
) -> dict[str, Any]:
    if isinstance(value_type, dict):
        schema = copy.deepcopy(value_type)
    else:
        declared = getattr(value_type, "__json_schema__", None)
        schema = copy.deepcopy(declared) if declared is not None else _schema_for_type(
            value_type,
            option_add_null_type,
        )
    allowed = {
        "properties",
        "required",
        "type",
        "additionalProperties",
        "$defs",
        "definitions",
    }
    return {key: value for key, value in schema.items() if key in allowed}


def _schema_for_type(value_type: Any, nullable: bool) -> dict[str, Any]:
    origin = get_origin(value_type)
    args = get_args(value_type)
    if origin in (Union, UnionType):
        non_none = tuple(arg for arg in args if arg is not type(None))
        if len(non_none) == 1:
            result = _schema_for_type(non_none[0], nullable)
            if nullable:
                result = {"anyOf": [result, {"type": "null"}]}
            return result
    if origin in (list, tuple):
        item_type = args[0] if args else Any
        return {"type": "array", "items": _schema_for_type(item_type, nullable)}
    if isinstance(value_type, type) and issubclass(value_type, Enum):
        return {
            "type": "string",
            "enum": [member.value for member in value_type],
        }
    if value_type is str:
        return {"type": "string"}
    if value_type is int:
        return {"type": "integer"}
    if value_type is bool:
        return {"type": "boolean"}
    if is_dataclass(value_type):
        hints = get_type_hints(value_type)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for field in fields(value_type):
            hint = hints.get(field.name, Any)
            properties[field.name] = _schema_for_type(hint, nullable)
            if type(None) not in get_args(hint):
                required.append(field.name)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
    return {}


__all__ = ["input_schema_for", "output_schema_for", "schema_for"]
