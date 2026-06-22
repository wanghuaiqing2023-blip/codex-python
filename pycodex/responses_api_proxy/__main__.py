"""Binary entrypoint for ``python -m pycodex.responses_api_proxy``."""

from __future__ import annotations

import sys

from . import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
