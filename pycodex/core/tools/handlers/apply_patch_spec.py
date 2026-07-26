"""Tool specification for the Rust ``apply_patch_spec`` module."""

from __future__ import annotations

from pycodex.core.tools.hosted_spec import FreeformToolFormat, ToolSpec

APPLY_PATCH_TOOL_NAME = "apply_patch"
APPLY_PATCH_FREEFORM_DESCRIPTION = (
    "Use the `apply_patch` tool to edit files. This is a FREEFORM tool, so do "
    "not wrap the patch in JSON."
)
APPLY_PATCH_LARK_GRAMMAR = """start: begin_patch hunk+ end_patch
begin_patch: "*** Begin Patch" LF
end_patch: "*** End Patch" LF?

hunk: add_hunk | delete_hunk | update_hunk
add_hunk: "*** Add File: " filename LF add_line+
delete_hunk: "*** Delete File: " filename LF
update_hunk: "*** Update File: " filename LF change_move? change?

filename: /(.+)/
add_line: "+" /(.*)/ LF -> line

change_move: "*** Move to: " filename LF
change: (change_context | change_line)+ eof_line?
change_context: ("@@" | "@@ " /(.+)/) LF
change_line: ("+" | "-" | " ") /(.*)/ LF
eof_line: "*** End of File" LF

%import common.LF
"""


def create_apply_patch_freeform_tool(include_environment_id: bool) -> ToolSpec:
    if not isinstance(include_environment_id, bool):
        raise TypeError("include_environment_id must be a bool")
    definition = APPLY_PATCH_LARK_GRAMMAR
    if include_environment_id:
        definition = definition.replace(
            "start: begin_patch hunk+ end_patch",
            (
                "start: begin_patch environment_id? hunk+ end_patch\n"
                'environment_id: "*** Environment ID: " filename LF'
            ),
        )
    return ToolSpec.freeform(
        name=APPLY_PATCH_TOOL_NAME,
        description=APPLY_PATCH_FREEFORM_DESCRIPTION,
        format=FreeformToolFormat.grammar(syntax="lark", definition=definition),
    )


__all__ = [
    "APPLY_PATCH_FREEFORM_DESCRIPTION",
    "APPLY_PATCH_LARK_GRAMMAR",
    "APPLY_PATCH_TOOL_NAME",
    "create_apply_patch_freeform_tool",
]
