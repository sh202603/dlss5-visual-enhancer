"""Console entry point used by VE_CLI.exe and the bundled Python runtime."""
import sys

sys.dont_write_bytecode = True

from dlss5ve.portable import configure_portable_environment

configure_portable_environment()

from dlss5ve.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
