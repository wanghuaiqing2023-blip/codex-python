from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pycodex.app_server_protocol.experimental_api import (
    clear_experimental_fields,
    experimental_fields,
    experimental_reason,
)
from pycodex.codex_experimental_api_macros import (
    derive_experimental_api,
    experimental_metadata,
    nested_metadata,
    presence_for_value,
    snake_to_camel,
)


@derive_experimental_api(
    enum_reasons={
        "UNIT": "enum/unit",
        "TUPLE": "enum/tuple",
        "NAMED": "enum/named",
    }
)
class EnumVariantShapes(Enum):
    UNIT = "unit"
    TUPLE = ("tuple", 1)
    NAMED = {"value": 1}
    STABLE_TUPLE = ("stable", 1)


@derive_experimental_api
@dataclass
class NestedFieldShape:
    inner: EnumVariantShapes | None = field(default=None, metadata=nested_metadata())


@derive_experimental_api
@dataclass
class NestedCollectionShape:
    inners: list[EnumVariantShapes] = field(default_factory=list, metadata=nested_metadata())


@derive_experimental_api
@dataclass
class NestedMapShape:
    inners: dict[str, EnumVariantShapes] = field(default_factory=dict, metadata=nested_metadata())


def test_derive_supports_all_enum_variant_shapes():
    # Rust crate/module: codex-experimental-api-macros src/lib.rs,
    # exercised by app-server-protocol experimental_api.rs derive_supports_all_enum_variant_shapes.
    assert EnumVariantShapes.UNIT.experimental_reason() == "enum/unit"
    assert EnumVariantShapes.TUPLE.experimental_reason() == "enum/tuple"
    assert EnumVariantShapes.NAMED.experimental_reason() == "enum/named"
    assert EnumVariantShapes.STABLE_TUPLE.experimental_reason() is None


def test_derive_supports_nested_experimental_fields():
    assert NestedFieldShape(EnumVariantShapes.NAMED).experimental_reason() == "enum/named"
    assert NestedFieldShape(None).experimental_reason() is None


def test_derive_supports_nested_collections():
    shape = NestedCollectionShape([EnumVariantShapes.STABLE_TUPLE, EnumVariantShapes.TUPLE])

    assert shape.experimental_reason() == "enum/tuple"
    assert NestedCollectionShape([]).experimental_reason() is None


def test_derive_supports_nested_maps():
    shape = NestedMapShape({"default": EnumVariantShapes.NAMED})

    assert shape.experimental_reason() == "enum/named"
    assert NestedMapShape({}).experimental_reason() is None


def test_derive_marks_optional_experimental_fields_when_some():
    clear_experimental_fields()

    @derive_experimental_api
    @dataclass
    class ExperimentalFieldShape:
        optional_collection: list[EnumVariantShapes] | None = field(
            default=None,
            metadata=experimental_metadata(
                "field/optionalCollection",
                presence="option",
            ),
        )

    assert ExperimentalFieldShape([]).experimental_reason() == "field/optionalCollection"
    assert ExperimentalFieldShape(None).experimental_reason() is None
    assert ExperimentalFieldShape.EXPERIMENTAL_FIELDS[0].field_name == "optionalCollection"
    assert experimental_fields()[0].field_name == "optionalCollection"


def test_presence_rules_match_rust_type_branches():
    assert presence_for_value(None, "option") is False
    assert presence_for_value([], "collection") is False
    assert presence_for_value({}, "map") is False
    assert presence_for_value(False, "bool") is False
    assert presence_for_value(0, "always") is True


def test_snake_to_camel_matches_field_serialized_name_helper():
    assert snake_to_camel("optional_collection") == "optionalCollection"
    assert snake_to_camel("already_camel") == "alreadyCamel"


def test_nested_checks_follow_field_order():
    @derive_experimental_api
    @dataclass
    class OrderedShape:
        inner: EnumVariantShapes | None = field(metadata=nested_metadata())
        direct: bool = field(
            default=True,
            metadata=experimental_metadata("field/direct", presence="bool"),
        )

    assert OrderedShape(EnumVariantShapes.TUPLE).experimental_reason() == "enum/tuple"
    assert experimental_reason(OrderedShape(None, True)) == "field/direct"
