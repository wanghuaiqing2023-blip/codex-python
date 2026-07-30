"""Ad-hoc note tool from Rust ``memories/src/tools/ad_hoc_note.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.ext.extension_api import JsonToolOutput

from ..backend import AddAdHocMemoryNoteRequest, AddAdHocMemoryNoteResponse
from ..metrics import record_tool_call
from . import (
    backend_error_to_function_call,
    memory_function_tool,
    memory_tool_name,
    parse_args,
    reject_unknown_args,
    to_json_value,
)

ADD_AD_HOC_NOTE_TOOL_NAME = "add_ad_hoc_note"


@dataclass(frozen=True)
class AddAdHocNoteArgs:
    filename: str
    note: str


@dataclass
class AddAdHocNoteTool:
    backend: Any
    metrics_client: Any = None

    def tool_name(self) -> Any:
        return memory_tool_name(ADD_AD_HOC_NOTE_TOOL_NAME)

    def spec(self) -> Any:
        return memory_function_tool(
            ADD_AD_HOC_NOTE_TOOL_NAME,
            "Create one append-only ad-hoc memory note after the user explicitly asks Codex to remember, forget, or update something.",
            AddAdHocNoteArgs,
            AddAdHocMemoryNoteResponse,
        )

    async def handle(self, call: Any) -> JsonToolOutput:
        args = parse_args(call)
        reject_unknown_args(args, {"filename", "note"})
        try:
            request = AddAdHocMemoryNoteRequest(
                filename=_required_string(args, "filename"),
                note=_required_string(args, "note"),
            )
            response = await self.backend.add_ad_hoc_note(request)
        except Exception as error:
            record_tool_call(
                self.metrics_client,
                ADD_AD_HOC_NOTE_TOOL_NAME,
                "ad_hoc_notes",
                False,
                "not_applicable",
            )
            raise backend_error_to_function_call(error) from error
        record_tool_call(
            self.metrics_client,
            ADD_AD_HOC_NOTE_TOOL_NAME,
            "ad_hoc_notes",
            True,
            "not_applicable",
        )
        return JsonToolOutput.new(to_json_value(response))


def _required_string(args: dict[str, Any], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str):
        from pycodex.ext.extension_api import FunctionCallError

        raise FunctionCallError.respond_to_model(f"{name} must be a string")
    return value


__all__ = ["AddAdHocNoteArgs", "AddAdHocNoteTool"]
