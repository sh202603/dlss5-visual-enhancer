"""Portable DLSS 5 Visual Enhancer for images and video.

The feature packages are imported lazily so that ``import dlss5ve`` works in
environments without the optional image decoders (``image`` extra): video,
frame interpolation, and the engine API only need numpy, av, and OpenCV.
"""
from __future__ import annotations

import importlib
from typing import Any

_EXPORTS: dict[str, str] = {
    "probe_video": ".core.ffmpeg",
    "ImageBatchResult": ".image",
    "ImageConversionFailure": ".image",
    "ImageConversionOptions": ".image",
    "ImageConversionResult": ".image",
    "convert_image": ".image",
    "convert_images": ".image",
    "probe_image": ".image",
    "FrameInterpolationBatchResult": ".frame_interpolation",
    "FrameInterpolationCapabilities": ".frame_interpolation",
    "FrameInterpolationOptions": ".frame_interpolation",
    "FrameInterpolationResult": ".frame_interpolation",
    "interpolate_video": ".frame_interpolation",
    "interpolate_videos": ".frame_interpolation",
    "probe_frame_interpolation_capabilities": ".frame_interpolation",
    "ConversionOptions": ".video",
    "ConversionResult": ".video",
    "VideoBatchResult": ".video",
    "VideoConversionFailure": ".video",
    "VideoConversionSuccess": ".video",
    "convert_video": ".video",
    "convert_videos": ".video",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
