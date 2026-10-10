from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from dlss5ve.portable import configure_portable_environment

configure_portable_environment()

from dlss5ve.desktop.app import launch_desktop


def main() -> int:
    """Launch the PySide6 + Qt Quick/QML desktop application."""
    return launch_desktop()


if __name__ == "__main__":
    sys.exit(main())
