# Vendored Textual source import plan

This plan maps the audited Textual 0.43.2 wheel stack into `pycodex/vendor`.
It is the step before actually extracting third-party source into the runtime
import path.

## Source stack

The audited candidate stack is documented in
`pycodex/vendor/TEXTUAL_0_43_2_AUDIT.md`.

Pinned runtime packages:

- `textual==0.43.2`
- `rich==13.8.1`
- `markdown-it-py==2.2.0`
- `mdit-py-plugins==0.3.5`
- `linkify-it-py==2.0.3`
- `mdurl==0.1.2`
- `importlib-metadata==6.7.0`
- `typing-extensions==4.7.1`
- `pygments==2.17.2`
- `uc-micro-py==1.0.3`
- `zipp==3.15.0`

## Target layout

Vendored package roots should be extracted under `pycodex/vendor/_packages`.
The package import roots should remain importable by their canonical names only
inside the vendored import context.

```text
pycodex/vendor/
  _packages/
    textual/
    rich/
    markdown_it/
    mdit_py_plugins/
    linkify_it/
    mdurl/
    importlib_metadata/
    typing_extensions.py
    pygments/
    uc_micro/
    zipp/
  _dist_info/
    textual-0.43.2.dist-info/
    rich-13.8.1.dist-info/
    ...
  licenses/
    textual/
    rich/
    ...
```

## Extraction rules

- Copy Python packages/modules from each wheel into `pycodex/vendor/_packages`.
- Copy each wheel's `.dist-info` directory into `pycodex/vendor/_dist_info`.
- Copy license, copying, and notice files into `pycodex/vendor/licenses/<package>/`.
- Preserve package-relative data files required by runtime imports.
- Do not copy tests, docs, examples, benchmarks, or development extras unless a
  runtime import requires them.
- Do not include syntax extras (`tree-sitter`, `tree_sitter_languages`) in the
  first vendoring pass.

## Import policy

Project code must not directly import vendored packages with top-level imports
such as:

```python
import textual
from rich.text import Text
```

Instead, TUI code should import approved APIs through:

```python
from pycodex.tui.textual_compat import App, Widget, events
from pycodex.tui.ratatui_bridge import Span, Line, Text, Style, Rect
```

`pycodex.tui.textual_compat` owns the mechanics of exposing vendored Textual.
It may temporarily add `pycodex/vendor/_packages` to an internal import context,
but that implementation detail should not leak into TUI modules.

## Metadata policy

Every vendored package entry in `VENDORED_PACKAGES.md` must include:

- pinned version
- upstream source URL or PyPI URL
- wheel filename
- wheel SHA256
- sdist filename and SHA256 when available
- license field and copied license-file path
- import roots copied into `_packages`

## Runtime integrity checks

Before any TUI module depends on vendored Textual, add a lightweight import check
function in `pycodex.tui.textual_compat` that confirms the loaded module path is
inside `pycodex/vendor/_packages`. This prevents accidental use of globally
installed `textual` or `rich`.

## First API exposure

The first `textual_compat` exports should be conservative:

```python
App
Widget
ComposeResult
Container
Horizontal
Vertical
events
```

Add more only when a ported module needs them.

## Ratatui bridge first API

The first `ratatui_bridge` exports should be independent semantic types:

```python
Style
Span
Line
Text
Rect
Renderable
```

These should be small local dataclasses/protocols that can later convert to
Textual/Rich renderables. They should not require importing Textual at module
import time.

## Next implementation step

Extract the audited wheels into `pycodex/vendor/_packages`, `_dist_info`, and
`licenses`, then implement a minimal vendored import helper that can load and
verify `textual==0.43.2` from the vendored tree.
