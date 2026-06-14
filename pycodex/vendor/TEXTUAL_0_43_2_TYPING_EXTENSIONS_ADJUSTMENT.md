# Textual 0.43.2 typing-extensions adjustment

## Decision

`typing-extensions` is pinned to `4.3.0` for the vendored Textual stack.

## Reason

The earlier candidate `typing-extensions==4.7.1` satisfies Python 3.7 metadata, but fails during import on the current Python runtime because it writes `ParamSpec.__default__`. Versions `4.6.x` have the same runtime issue here, while `4.5.x` and `4.4.x` fail when subclassing modern `typing.TypeVar`.

Version `4.3.0` still supports Python 3.7 and was verified by importing `textual`, `textual.app`, `textual.widget`, and `rich.text` from the vendored stack. Vendored dist-info is stored separately from importable packages, and `pycodex.vendor.ensure_vendor_packages_on_path()` exposes both locations so `importlib.metadata` lookups such as `textual.__version__` continue to work.

## Source

- Wheel: `typing_extensions-4.3.0-py3-none-any.whl`
- SHA256: `25642c956049920a5aa49edcdd6ab1e06d7e5d467fc00e0506c44ac86fbfca02`
- URL: `https://files.pythonhosted.org/packages/ed/d6/2afc375a8d55b8be879d6b4986d4f69f01115e795e36827fd3a40166028b/typing_extensions-4.3.0-py3-none-any.whl`
