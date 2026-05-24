"""Review output formatting helpers ported from Codex core."""

from __future__ import annotations

from collections.abc import Sequence

from pycodex.protocol import ReviewFinding, ReviewOutputEvent

REVIEW_FALLBACK_MESSAGE = "Reviewer failed to output a response."
_LOCATION_SEPARATOR = " \u2014 "


def format_location(item: ReviewFinding) -> str:
    path = item.code_location.absolute_file_path
    line_range = item.code_location.line_range
    return f"{path}:{line_range.start}-{line_range.end}"


def format_review_findings_block(
    findings: Sequence[ReviewFinding],
    selection: Sequence[bool] | None = None,
) -> str:
    lines: list[str] = [""]

    if len(findings) > 1:
        lines.append("Full review comments:")
    else:
        lines.append("Review comment:")

    for index, item in enumerate(findings):
        lines.append("")

        title = item.title
        location = format_location(item)

        if selection is not None:
            checked = selection[index] if index < len(selection) else True
            marker = "[x]" if checked else "[ ]"
            lines.append(f"- {marker} {title}{_LOCATION_SEPARATOR}{location}")
        else:
            lines.append(f"- {title}{_LOCATION_SEPARATOR}{location}")

        for body_line in item.body.splitlines():
            lines.append(f"  {body_line}")

    return "\n".join(lines)


def render_review_output_text(output: ReviewOutputEvent) -> str:
    sections: list[str] = []
    explanation = output.overall_explanation.strip()
    if explanation:
        sections.append(explanation)

    if output.findings:
        findings = format_review_findings_block(output.findings)
        trimmed_findings = findings.strip()
        if trimmed_findings:
            sections.append(trimmed_findings)

    if not sections:
        return REVIEW_FALLBACK_MESSAGE
    return "\n\n".join(sections)


__all__ = [
    "REVIEW_FALLBACK_MESSAGE",
    "format_location",
    "format_review_findings_block",
    "render_review_output_text",
]
