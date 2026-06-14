# Textual vendoring plan

This plan records the candidate Python-3.7-compatible Textual stack for the
Codex TUI port. No third-party source has been vendored yet.

## Goal

Vendor Textual as the Python TUI framework while preserving the project's
portability goal, including Python 3.7 compatibility where practical.

## Candidate pin

- `textual==0.43.2`

Rationale:

- PyPI metadata for `textual==0.43.2` declares `Requires-Python: >=3.7,<4.0`.
- Later Textual releases eventually moved to `Requires-Python: >=3.9`.
- `0.43.2` is the latest stable release found in PyPI metadata with explicit
  Python 3.7 support.
- License is MIT.

## Candidate runtime dependency pins

The Textual package uses open dependency ranges. For vendoring, these must be
pinned explicitly so Python 3.7 does not accidentally resolve unsupported newer
versions.

| Package | Candidate pin | Why |
|---|---:|---|
| `textual` | `0.43.2` | Latest stable Textual release found with `>=3.7,<4.0`. |
| `rich` | `13.8.1` | Satisfies Textual `rich>=13.3.3`; declares `>=3.7.0`. |
| `markdown-it-py` | `2.2.0` | Satisfies Textual `markdown-it-py[linkify,plugins]>=2.1.0`; declares `>=3.7`; avoids 3.x Python 3.7 drop. |
| `mdit-py-plugins` | `0.3.5` | Required by `markdown-it-py[plugins]`; declares `>=3.7`; constrained to `<3` by plugin package. |
| `linkify-it-py` | `2.0.3` | Required by `markdown-it-py[linkify]`; declares `>=3.7`. |
| `mdurl` | `0.1.2` | Required by `markdown-it-py`; declares `>=3.7`. |
| `importlib-metadata` | `6.7.0` | Required by Textual; declares `>=3.7`. |
| `typing-extensions` | `4.7.1` | Required by Textual and older Python dependency paths; declares `>=3.7`. |
| `pygments` | `2.17.2` | Required by Rich; declares `>=3.7`. |
| `uc-micro-py` | `1.0.3` | Required by `linkify-it-py`; declares `>=3.7`. |
| `zipp` | `3.15.0` | Required by `importlib-metadata`; declares `>=3.7`. |

## Next audit step

Before vendoring source, download wheels/sdists into a temporary directory and
record each package's:

- source URL
- wheel URL
- SHA256 hash
- license
- package import roots
- whether package metadata/resources are needed at runtime

## Import policy

Codex TUI modules should not import vendored packages directly. The intended
layers remain:

```text
pycodex.tui.ratatui_bridge
    -> pycodex.tui.textual_compat
    -> pycodex.vendor.<vendored packages>
```

## Known tradeoff

Choosing Textual `0.43.2` preserves Python 3.7 compatibility but gives up modern
Textual 8.x APIs and fixes. This is an intentional portability-first candidate,
not a latest-feature candidate.
