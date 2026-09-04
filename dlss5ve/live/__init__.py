"""Live playback with DLSS 5 Neural Rendering.

The Gradio tab (``LiveTab``, ``build_live_tab``) is resolved lazily so that
``dlss5ve.live.pipeline`` can be used from the command line without Gradio.
"""
from __future__ import annotations

from typing import Any

from .models import LiveOptions, LiveSessionInfo
from .pipeline import (
    is_live_running,
    live_status,
    start_live_session,
    stop_live_session,
    sweep_stale_live_dirs,
)

__all__ = [
    "LiveOptions",
    "LiveSessionInfo",
    "LiveTab",
    "build_live_tab",
    "is_live_running",
    "live_status",
    "start_live_session",
    "stop_live_session",
    "sweep_stale_live_dirs",
]


def __getattr__(name: str) -> Any:
    if name in ("LiveTab", "build_live_tab"):
        from . import ui

        value = getattr(ui, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
