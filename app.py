from __future__ import annotations

import sys

from dlss5ve.desktop.app import launch_desktop


def main() -> int:
    """Launch the PySide6 + Qt Quick/QML desktop application."""
    return launch_desktop()


if __name__ == "__main__":
    sys.exit(main())
