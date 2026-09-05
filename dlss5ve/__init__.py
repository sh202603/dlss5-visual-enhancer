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
    "ImageBatchResult": ".neural_rendering.image",
    "ImageConversionFailure": ".neural_rendering.image",
    "ImageConversionOptions": ".neural_rendering.image",
    "ImageConversionResult": ".neural_rendering.image",
    "convert_image": ".neural_rendering.image",
    "convert_images": ".neural_rendering.image",
    "probe_image": ".neural_rendering.image",
    "FrameInterpolationBatchResult": ".frame_interpolation",
    "FrameInterpolationCapabilities": ".frame_interpolation",
    "FrameInterpolationOptions": ".frame_interpolation",
    "FrameInterpolationResult": ".frame_interpolation",
    "interpolate_video": ".frame_interpolation",
    "interpolate_videos": ".frame_interpolation",
    "probe_frame_interpolation_capabilities": ".frame_interpolation",
    "ConversionOptions": ".neural_rendering.video",
    "ConversionResult": ".neural_rendering.video",
    "VideoBatchResult": ".neural_rendering.video",
    "VideoConversionFailure": ".neural_rendering.video",
    "VideoConversionSuccess": ".neural_rendering.video",
    "convert_video": ".neural_rendering.video",
    "convert_videos": ".neural_rendering.video",
    "ImageUpscaleBatchResult": ".upscale.image",
    "ImageUpscaleFailure": ".upscale.image",
    "ImageUpscaleOptions": ".upscale.image",
    "ImageUpscaleResult": ".upscale.image",
    "upscale_image": ".upscale.image",
    "upscale_images": ".upscale.image",
    "UpscaleBatchResult": ".upscale.video.models",
    "UpscaleFailure": ".upscale.video.models",
    "UpscaleOptions": ".upscale.video.models",
    "UpscaleResult": ".upscale.video.models",
    "UpscaleSuccess": ".upscale.video.models",
    "upscale_video": ".upscale.video.processor",
    "upscale_videos": ".upscale.video.batch",
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
