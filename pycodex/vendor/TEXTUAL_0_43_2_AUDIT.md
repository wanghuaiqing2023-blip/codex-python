# Textual 0.43.2 vendoring audit

Generated: 2026-06-13 12:33:55Z

This audit downloads candidate wheels into `.tmp/textual_vendor_audit` and inspects package metadata. It does not vendor third-party source into the runtime import path.

## Candidate pin set

| Package | Pin | Requires-Python | License | Wheel SHA256 | Import roots | License files | Non-Python resources |
|---|---:|---|---|---|---|---|---:|
| `textual` | `0.43.2` | `>=3.7,<4.0` | MIT | `b6a3340738e3c2223049bb6a4fbce059e4f942a4480b8fd146b816ce5228a8ec` | `textual` | `textual-0.43.2.dist-info/LICENSE` | 13 |
| `rich` | `13.8.1` | `>=3.7.0` | MIT | `1760a3c0848469b97b558fc61c85233e3dafb69c7a071b4d60c38099d3cd4c06` | `rich` | `rich-13.8.1.dist-info/LICENSE` | 1 |
| `markdown-it-py` | `2.2.0` | `>=3.7` | metadata/file | `5a35f8d1870171d9acc47b99612dc146129b631baf04970128b568f190d0cc30` | `markdown_it` | `markdown_it_py-2.2.0.dist-info/LICENSE`, `markdown_it_py-2.2.0.dist-info/LICENSE.markdown-it` | 2 |
| `mdit-py-plugins` | `0.3.5` | `>=3.7` | metadata/file | `ca9a0714ea59a24b2b044a1831f48d817dd0c817e84339f20e7889f392d77c4e` | `mdit_py_plugins` | `mdit_py_plugins-0.3.5.dist-info/LICENSE`, `mdit_py_plugins/admon/LICENSE`, `mdit_py_plugins/container/LICENSE`, `mdit_py_plugins/deflist/LICENSE`, `mdit_py_plugins/footnote/LICENSE`, `mdit_py_plugins/front_matter/LICENSE`, `mdit_py_plugins/texmath/LICENSE` | 17 |
| `linkify-it-py` | `2.0.3` | `>=3.7` | MIT | `6bcbc417b0ac14323382aef5c5192c0075bf8a9d6b41820a2b66371eac6b6d79` | `linkify_it` | `linkify_it_py-2.0.3.dist-info/LICENSE` | 0 |
| `mdurl` | `0.1.2` | `>=3.7` | metadata/file | `84008a41e51615a49fc9966191ff91509e3c40b939176e643fd50a5c2196b8f8` | `mdurl` | `mdurl-0.1.2.dist-info/LICENSE` | 1 |
| `importlib-metadata` | `6.7.0` | `>=3.7` | metadata/file | `cb52082e659e97afc5dac71e79de97d8681de3aa07ff18578330904a9d18e5b5` | `importlib_metadata` | `importlib_metadata-6.7.0.dist-info/LICENSE` | 1 |
| `typing-extensions` | `4.7.1` | `>=3.7` | metadata/file | `440d5dd3af93b060174bf433bccd69b0babc3b15b1a8dca43789fd7f61514b36` | `typing_extensions` | `typing_extensions-4.7.1.dist-info/LICENSE` | 0 |
| `pygments` | `2.17.2` | `>=3.7` | BSD-2-Clause | `b27c2826c47d0f3219f29554824c30c5e8945175d888647acd804ddd04af846c` | `pygments` | `pygments-2.17.2.dist-info/licenses/LICENSE` | 0 |
| `uc-micro-py` | `1.0.3` | `>=3.7` | MIT | `db1dffff340817673d7b466ec86114a9dc0e9d4d9b5ba229d9d60e5c12600cd5` | `uc_micro` | `uc_micro_py-1.0.3.dist-info/LICENSE` | 0 |
| `zipp` | `3.15.0` | `>=3.7` | metadata/file | `48904fc76a60e542af151aded95726c1a5c34ed43ab4134b597665c86d7ad556` | `zipp` | `zipp-3.15.0.dist-info/LICENSE` | 0 |

## Runtime dependency metadata

### `textual==0.43.2`

- Wheel: `textual-0.43.2-py3-none-any.whl`
- Sdist: `textual-0.43.2.tar.gz`
- Requires-Python: `>=3.7,<4.0`
- Requires-Dist:
  - `rich (>=13.3.3)`
  - `markdown-it-py[linkify,plugins] (>=2.1.0)`
  - `importlib-metadata (>=4.11.3)`
  - `typing-extensions (>=4.4.0,<5.0.0)`
  - `tree-sitter (>=0.20.1,<0.21.0) ; extra == "syntax"`
  - `tree_sitter_languages (>=1.7.0) ; extra == "syntax"`

### `rich==13.8.1`

- Wheel: `rich-13.8.1-py3-none-any.whl`
- Sdist: `rich-13.8.1.tar.gz`
- Requires-Python: `>=3.7.0`
- Requires-Dist:
  - `typing-extensions<5.0,>=4.0.0; python_version < "3.9"`
  - `pygments<3.0.0,>=2.13.0`
  - `ipywidgets<9,>=7.5.1; extra == "jupyter"`
  - `markdown-it-py>=2.2.0`

### `markdown-it-py==2.2.0`

- Wheel: `markdown_it_py-2.2.0-py3-none-any.whl`
- Sdist: `markdown-it-py-2.2.0.tar.gz`
- Requires-Python: `>=3.7`
- Requires-Dist:
  - `mdurl~=0.1`
  - `typing_extensions>=3.7.4;python_version<'3.8'`
  - `psutil ; extra == "benchmarking"`
  - `pytest ; extra == "benchmarking"`
  - `pytest-benchmark ; extra == "benchmarking"`
  - `pre-commit~=3.0 ; extra == "code_style"`
  - `commonmark~=0.9 ; extra == "compare"`
  - `markdown~=3.4 ; extra == "compare"`
  - `mistletoe~=1.0 ; extra == "compare"`
  - `mistune~=2.0 ; extra == "compare"`
  - `panflute~=2.3 ; extra == "compare"`
  - `linkify-it-py>=1,<3 ; extra == "linkify"`
  - `mdit-py-plugins ; extra == "plugins"`
  - `gprof2dot ; extra == "profiling"`
  - `attrs ; extra == "rtd"`
  - `myst-parser ; extra == "rtd"`
  - `pyyaml ; extra == "rtd"`
  - `sphinx ; extra == "rtd"`
  - `sphinx-copybutton ; extra == "rtd"`
  - `sphinx-design ; extra == "rtd"`
  - `sphinx_book_theme ; extra == "rtd"`
  - `coverage ; extra == "testing"`
  - `pytest ; extra == "testing"`
  - `pytest-cov ; extra == "testing"`
  - `pytest-regressions ; extra == "testing"`

### `mdit-py-plugins==0.3.5`

- Wheel: `mdit_py_plugins-0.3.5-py3-none-any.whl`
- Sdist: `mdit-py-plugins-0.3.5.tar.gz`
- Requires-Python: `>=3.7`
- Requires-Dist:
  - `markdown-it-py>=1.0.0,<3.0.0`
  - `pre-commit ; extra == "code_style"`
  - `attrs ; extra == "rtd"`
  - `myst-parser~=0.16.1 ; extra == "rtd"`
  - `sphinx-book-theme~=0.1.0 ; extra == "rtd"`
  - `coverage ; extra == "testing"`
  - `pytest ; extra == "testing"`
  - `pytest-cov ; extra == "testing"`
  - `pytest-regressions ; extra == "testing"`

### `linkify-it-py==2.0.3`

- Wheel: `linkify_it_py-2.0.3-py3-none-any.whl`
- Sdist: `linkify-it-py-2.0.3.tar.gz`
- Requires-Python: `>=3.7`
- Requires-Dist:
  - `uc-micro-py`
  - `pytest ; extra == 'benchmark'`
  - `pytest-benchmark ; extra == 'benchmark'`
  - `pre-commit ; extra == 'dev'`
  - `isort ; extra == 'dev'`
  - `flake8 ; extra == 'dev'`
  - `black ; extra == 'dev'`
  - `pyproject-flake8 ; extra == 'dev'`
  - `sphinx ; extra == 'doc'`
  - `sphinx-book-theme ; extra == 'doc'`
  - `myst-parser ; extra == 'doc'`
  - `pytest ; extra == 'test'`
  - `coverage ; extra == 'test'`
  - `pytest-cov ; extra == 'test'`

### `mdurl==0.1.2`

- Wheel: `mdurl-0.1.2-py3-none-any.whl`
- Sdist: `mdurl-0.1.2.tar.gz`
- Requires-Python: `>=3.7`
- Requires-Dist:
  - `<none>`

### `importlib-metadata==6.7.0`

- Wheel: `importlib_metadata-6.7.0-py3-none-any.whl`
- Sdist: `importlib_metadata-6.7.0.tar.gz`
- Requires-Python: `>=3.7`
- Requires-Dist:
  - `zipp (>=0.5)`
  - `typing-extensions (>=3.6.4) ; python_version < "3.8"`
  - `sphinx (>=3.5) ; extra == 'docs'`
  - `jaraco.packaging (>=9) ; extra == 'docs'`
  - `rst.linker (>=1.9) ; extra == 'docs'`
  - `furo ; extra == 'docs'`
  - `sphinx-lint ; extra == 'docs'`
  - `jaraco.tidelift (>=1.4) ; extra == 'docs'`
  - `ipython ; extra == 'perf'`
  - `pytest (>=6) ; extra == 'testing'`
  - `pytest-checkdocs (>=2.4) ; extra == 'testing'`
  - `pytest-cov ; extra == 'testing'`
  - `pytest-enabler (>=1.3) ; extra == 'testing'`
  - `pytest-ruff ; extra == 'testing'`
  - `packaging ; extra == 'testing'`
  - `pyfakefs ; extra == 'testing'`
  - `flufl.flake8 ; extra == 'testing'`
  - `pytest-perf (>=0.9.2) ; extra == 'testing'`
  - `pytest-black (>=0.3.7) ; (platform_python_implementation != "PyPy") and extra == 'testing'`
  - `pytest-mypy (>=0.9.1) ; (platform_python_implementation != "PyPy") and extra == 'testing'`
  - `importlib-resources (>=1.3) ; (python_version < "3.9") and extra == 'testing'`

### `typing-extensions==4.7.1`

- Wheel: `typing_extensions-4.7.1-py3-none-any.whl`
- Sdist: `typing_extensions-4.7.1.tar.gz`
- Requires-Python: `>=3.7`
- Requires-Dist:
  - `<none>`

### `pygments==2.17.2`

- Wheel: `pygments-2.17.2-py3-none-any.whl`
- Sdist: `pygments-2.17.2.tar.gz`
- Requires-Python: `>=3.7`
- Requires-Dist:
  - `importlib-metadata; python_version < '3.8' and extra == 'plugins'`
  - `colorama>=0.4.6; extra == 'windows-terminal'`

### `uc-micro-py==1.0.3`

- Wheel: `uc_micro_py-1.0.3-py3-none-any.whl`
- Sdist: `uc-micro-py-1.0.3.tar.gz`
- Requires-Python: `>=3.7`
- Requires-Dist:
  - `pytest ; extra == 'test'`
  - `coverage ; extra == 'test'`
  - `pytest-cov ; extra == 'test'`

### `zipp==3.15.0`

- Wheel: `zipp-3.15.0-py3-none-any.whl`
- Sdist: `zipp-3.15.0.tar.gz`
- Requires-Python: `>=3.7`
- Requires-Dist:
  - `sphinx (>=3.5) ; extra == 'docs'`
  - `jaraco.packaging (>=9) ; extra == 'docs'`
  - `rst.linker (>=1.9) ; extra == 'docs'`
  - `furo ; extra == 'docs'`
  - `sphinx-lint ; extra == 'docs'`
  - `jaraco.tidelift (>=1.4) ; extra == 'docs'`
  - `pytest (>=6) ; extra == 'testing'`
  - `pytest-checkdocs (>=2.4) ; extra == 'testing'`
  - `flake8 (<5) ; extra == 'testing'`
  - `pytest-cov ; extra == 'testing'`
  - `pytest-enabler (>=1.3) ; extra == 'testing'`
  - `jaraco.itertools ; extra == 'testing'`
  - `jaraco.functools ; extra == 'testing'`
  - `more-itertools ; extra == 'testing'`
  - `big-O ; extra == 'testing'`
  - `pytest-black (>=0.3.7) ; (platform_python_implementation != "PyPy") and extra == 'testing'`
  - `pytest-mypy (>=0.9.1) ; (platform_python_implementation != "PyPy") and extra == 'testing'`
  - `pytest-flake8 ; (python_version < "3.12") and extra == 'testing'`

## Preliminary decision

`textual==0.43.2` remains the portability-first candidate pin. The dependency stack has Python 3.7-compatible candidate pins, but vendoring must include transitive runtime packages rather than only `textual/`.

## Next step

Create a source import plan that maps each wheel import root into `pycodex/vendor`, preserves license files, and defines how `pycodex.tui.textual_compat` will import the vendored roots without falling back to globally installed packages.
