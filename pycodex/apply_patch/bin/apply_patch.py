"""Python entrypoint corresponding to ``src/main.rs``."""

from pycodex.apply_patch.standalone_executable import run_main as run_standalone_main


def main() -> int:
    import sys

    result = run_standalone_main(sys.argv[1:])
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
