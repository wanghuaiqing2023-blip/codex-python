# Textual 0.43.2 vendored extraction report

Generated: 2026-06-13 12:37:25Z

This report records extraction of the audited wheel stack into the vendored source tree. The TUI runtime has not been switched to these packages yet.

## Extracted roots

| Package | Pin | Wheel | Import roots | Dist-info | License files copied | Package files copied |
|---|---:|---|---|---|---:|---:|
| `textual` | `0.43.2` | `textual-0.43.2-py3-none-any.whl` | `textual` | `textual-0.43.2.dist-info` | 1 | 213 |
| `rich` | `13.8.1` | `rich-13.8.1-py3-none-any.whl` | `rich` | `rich-13.8.1.dist-info` | 1 | 79 |
| `markdown-it-py` | `2.2.0` | `markdown_it_py-2.2.0-py3-none-any.whl` | `markdown_it` | `markdown_it_py-2.2.0.dist-info` | 2 | 66 |
| `mdit-py-plugins` | `0.3.5` | `mdit_py_plugins-0.3.5-py3-none-any.whl` | `mdit_py_plugins` | `mdit_py_plugins-0.3.5.dist-info` | 7 | 47 |
| `linkify-it-py` | `2.0.3` | `linkify_it_py-2.0.3-py3-none-any.whl` | `linkify_it` | `linkify_it_py-2.0.3.dist-info` | 1 | 4 |
| `mdurl` | `0.1.2` | `mdurl-0.1.2-py3-none-any.whl` | `mdurl` | `mdurl-0.1.2.dist-info` | 1 | 7 |
| `importlib-metadata` | `6.7.0` | `importlib_metadata-6.7.0-py3-none-any.whl` | `importlib_metadata` | `importlib_metadata-6.7.0.dist-info` | 1 | 10 |
| `typing-extensions` | `4.7.1` | `typing_extensions-4.7.1-py3-none-any.whl` | `typing_extensions.py` | `typing_extensions-4.7.1.dist-info` | 1 | 1 |
| `pygments` | `2.17.2` | `pygments-2.17.2-py3-none-any.whl` | `pygments` | `pygments-2.17.2.dist-info` | 1 | 321 |
| `uc-micro-py` | `1.0.3` | `uc_micro_py-1.0.3-py3-none-any.whl` | `uc_micro` | `uc_micro_py-1.0.3.dist-info` | 1 | 13 |
| `zipp` | `3.15.0` | `zipp-3.15.0-py3-none-any.whl` | `zipp` | `zipp-3.15.0.dist-info` | 1 | 2 |

## Import boundary

The extracted roots live under `pycodex/vendor/_packages`. Project TUI code should still import Textual through `pycodex.tui.textual_compat`, not through direct top-level imports.

## Next step

Implement a minimal vendored import helper in `pycodex.vendor` and expose conservative Textual APIs from `pycodex.tui.textual_compat`, with path-integrity checks that reject globally installed packages.
