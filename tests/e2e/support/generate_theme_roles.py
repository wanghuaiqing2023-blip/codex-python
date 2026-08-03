"""Generate Python runtime theme roles from an independent Rust corpus.

This is an explicit maintenance command. Production never shells out to Cargo
and never reads the E2E preview golden file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from pycodex.tui.render.highlight import BUILTIN_THEME_NAMES

ROOT = Path(__file__).resolve().parents[3]
PROBE_MANIFEST = Path(__file__).with_name("rust_theme_roles") / "Cargo.toml"
RUNTIME_ASSET = ROOT / "pycodex" / "tui" / "render" / "theme_roles.json"
CORPUS_LINES = (
    "fn demo(parameter: &[Widget]) -> String {",
    "    // comment role",
    "    let variable: Vec<&str> = Widget::method(42);",
    "    let filtered = items.iter().filter(|candidate| candidate.ready).count();",
    '    format!("{variable} text {}", parameter.value())',
    "}",
)

ROLE_ANCHORS = {
    "keyword": (0, "fn"),
    "function": (0, "demo"),
    "parameter": (0, "parameter"),
    "punctuation": (0, "("),
    "separator": (2, ":"),
    "operator": (0, "&"),
    "assignment_operator": (2, "="),
    "path_separator": (2, "::"),
    "return_arrow": (0, "->"),
    "type_parameter": (0, "Widget"),
    "builtin_type": (0, "String"),
    "comment": (1, "comment"),
    "declaration_keyword": (2, "let"),
    "variable": (2, "variable"),
    "type_constructor": (2, "Vec"),
    "type_angle": (2, "<"),
    "primitive_type": (2, "str"),
    "namespace": (2, "Widget"),
    "associated_item": (2, "method"),
    "number": (2, "42"),
    "closure_pipe": (3, "|"),
    "member_access": (3, "."),
    "closure_parameter": (3, "candidate"),
    "property": (3, "ready"),
    "macro": (4, "format!"),
    "string": (4, " text "),
    "string_quote": (4, '"'),
    "format_placeholder": (4, "{variable}"),
    "method": (4, "value"),
    "default": (2, "variable"),
    "brace": (5, "}"),
}


def _probe_style_to_json(style: dict[str, Any]) -> dict[str, Any]:
    alpha = int(style["a"])
    if alpha == 0:
        foreground: Any = {"kind": "ansi", "value": int(style["r"])}
    elif alpha == 1:
        foreground = "default"
    else:
        foreground = {
            "kind": "rgb",
            "value": [int(style["r"]), int(style["g"]), int(style["b"])],
        }
    return {"fg": foreground, "bold": bool(style.get("bold", False))}


def _style_at(line: list[dict[str, Any]], source: str, needle: str) -> dict[str, Any]:
    offset = source.index(needle)
    cursor = 0
    for span in line:
        end = cursor + len(span["text"])
        if cursor <= offset < end:
            return _probe_style_to_json(span["style"])
        cursor = end
    raise AssertionError(f"Rust role anchor not highlighted: {needle!r} in {source!r}")


def generate_runtime_theme_roles(output: Path = RUNTIME_ASSET) -> dict[str, Any]:
    completed = subprocess.run(
        ["cargo", "run", "--quiet", "--manifest-path", str(PROBE_MANIFEST)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    probes = json.loads(completed.stdout)
    by_name = {probe["name"]: probe for probe in probes}
    if set(by_name) != set(BUILTIN_THEME_NAMES):
        raise AssertionError(
            f"two-face theme inventory differs: expected={BUILTIN_THEME_NAMES!r} actual={sorted(by_name)!r}"
        )

    themes: dict[str, Any] = {}
    for name in BUILTIN_THEME_NAMES:
        probe = by_name[name]
        roles = {
            role: _style_at(probe["lines"][line_index], CORPUS_LINES[line_index], needle)
            for role, (line_index, needle) in ROLE_ANCHORS.items()
        }
        themes[name] = {
            "roles": roles,
            "diff_backgrounds": {
                "inserted": probe["inserted_background"],
                "deleted": probe["deleted_background"],
            },
        }

    asset = {
        "schema_version": 1,
        "two_face_version": "0.5.1",
        "generator": "tests/e2e/support/rust_theme_roles",
        "corpus": list(CORPUS_LINES),
        "theme_names": list(BUILTIN_THEME_NAMES),
        "themes": themes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asset, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return asset


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Rust-derived Python theme role assets")
    parser.add_argument("--output", type=Path, default=RUNTIME_ASSET)
    args = parser.parse_args()
    asset = generate_runtime_theme_roles(args.output)
    print(f"wrote {len(asset['themes'])} themes to {args.output}")


if __name__ == "__main__":
    main()
