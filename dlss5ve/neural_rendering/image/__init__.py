"""Neural Rendering for still images.

The decoder, encoder, and batch modules pull in the optional image packages
(rawpy, pillow-heif, resvg-py), so they are resolved lazily: settings and the
upscale models import ``.models`` from here, and that must keep working in
environments that only carry the core dependencies (the engine API, lada-ex).
"""
from __future__ import annotations

import importlib
from typing import Any

from .models import (
    IMAGE_EXTENSIONS, IMAGE_FORMATS, RAW_EXTENSIONS, ImageBatchResult,
    ImageConversionFailure, ImageConversionOptions, ImageConversionResult,
)

_LAZY: dict[str, str] = {
    "convert_images": ".batch",
    "decode_image": ".decoder",
    "initialize_image_runtime": ".decoder",
    "probe_image": ".decoder",
    "save_image": ".encoder",
    "take_image_preview": ".encoder",
    "convert_image": ".processor",
}

__all__ = [
    "IMAGE_EXTENSIONS", "IMAGE_FORMATS", "RAW_EXTENSIONS", "ImageBatchResult",
    "ImageConversionFailure", "ImageConversionOptions", "ImageConversionResult",
    "convert_image", "convert_images", "decode_image", "initialize_image_runtime",
    "probe_image", "save_image", "take_image_preview",
]


def __getattr__(name: str) -> Any:
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))
