"""Build feature Options from UISettings.

Every entry point (WebUI handlers, CLI, presets) derives its Options here so
that a setting has one meaning everywhere. ``overrides`` are applied on top of
the values taken from ``settings`` and must name real Options fields, with
one exception: ``hdr_mode`` is accepted for video and frame interpolation and
is coerced against the effective codec before it lands in the Options
(``preserve_hdr`` for video, ``hdr_mode`` for frame interpolation).

The Upscale builders wrap the ``options_from_settings`` functions that the
upscale package ships; only the override check is added here.
"""
from __future__ import annotations

from dataclasses import fields, replace
from typing import Any

from ..frame_interpolation.models import FrameInterpolationOptions
from ..neural_rendering.video.models import ConversionOptions
from .models import UISettings, coerce_hdr_mode


def _check_overrides(cls: type, overrides: dict[str, Any]) -> None:
    known = {field.name for field in fields(cls)}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise TypeError(f"Unknown {cls.__name__} field(s): {', '.join(unknown)}.")


def _build(cls: type, values: dict[str, Any], overrides: dict[str, Any]) -> Any:
    _check_overrides(cls, overrides)
    values.update(overrides)
    return cls(**values)


def _neural_values(settings: UISettings) -> dict[str, Any]:
    """The Neural Rendering controls shared by the Image and Video modes."""
    return {
        "ai_gpu_uuid": settings.ai_gpu_uuid,
        "nr_style": settings.nr_style,
        "nr_intensity": settings.nr_intensity,
        "nr_passes": settings.nr_passes,
        "local_tone_strength": settings.local_tone_strength,
        "local_structure_strength": settings.local_structure_strength,
        "skin_structure_strength": settings.skin_structure_strength,
        "nr_color_strength": settings.nr_color_strength,
        "tone_preservation": settings.tone_preservation,
        "face_skin_protection": settings.face_skin_protection,
        "grain_preservation": settings.grain_preservation,
        "mask_feather": settings.mask_feather,
        "nr_mask": settings.nr_mask,
        "automatic_mask": settings.automatic_mask,
        "nr_gpu_mode": settings.nr_gpu_mode,
        "upscaling_factor": settings.upscaling_factor,
    }


def image_options(settings: UISettings, **overrides: Any):
    # Imported lazily: the image package pulls in the optional decoders
    # (rawpy, pillow-heif, resvg) that video-only installs do not carry.
    from ..neural_rendering.image.models import ImageConversionOptions

    values = _neural_values(settings)
    values.update(
        {
            "output_format": settings.image_format,
            "quality": int(settings.image_quality),
            "rename_mode": settings.image_rename_mode,
            "custom_suffix": settings.image_custom_suffix,
        }
    )
    return _build(ImageConversionOptions, values, overrides)


def video_options(settings: UISettings, **overrides: Any) -> ConversionOptions:
    hdr_mode = bool(overrides.pop("hdr_mode", settings.hdr_mode))
    values = _neural_values(settings)
    values.update(
        {
            "video_gpu_uuid": settings.video_gpu_uuid,
            # Temporal stabilization exists only for video (and Live).
            "shimmer_suppression": settings.shimmer_suppression,
            "codec": settings.codec,
            "container": settings.container,
            "quality": settings.quality,
            "rename_mode": settings.video_rename_mode,
            "custom_suffix": settings.video_custom_suffix,
        }
    )
    codec = overrides.get("codec", values["codec"])
    values["preserve_hdr"] = coerce_hdr_mode(codec, hdr_mode)
    return _build(ConversionOptions, values, overrides)


def frame_interpolation_options(
    settings: UISettings, **overrides: Any
) -> FrameInterpolationOptions:
    hdr_mode = bool(overrides.pop("hdr_mode", settings.frame_interpolation_hdr_mode))
    values = {
        "ai_gpu_uuid": settings.ai_gpu_uuid,
        "video_gpu_uuid": settings.video_gpu_uuid,
        "target_fps": settings.frame_interpolation_target_fps,
        "engine": settings.frame_interpolation_engine,
        "codec": settings.frame_interpolation_codec,
        "container": settings.frame_interpolation_container,
        "quality": settings.frame_interpolation_quality,
        "rename_mode": settings.frame_interpolation_rename_mode,
        "custom_suffix": settings.frame_interpolation_custom_suffix,
    }
    codec = overrides.get("codec", values["codec"])
    values["hdr_mode"] = coerce_hdr_mode(codec, hdr_mode)
    return _build(FrameInterpolationOptions, values, overrides)


def upscale_video_options(settings: UISettings, **overrides: Any):
    from ..upscale.video.models import UpscaleOptions, options_from_settings

    _check_overrides(UpscaleOptions, overrides)
    return replace(options_from_settings(settings), **overrides)


def upscale_image_options(settings: UISettings, **overrides: Any):
    # Imported lazily for the same reason as image_options: the image models
    # sit next to the optional decoders.
    from ..upscale.image.models import ImageUpscaleOptions, options_from_settings

    _check_overrides(ImageUpscaleOptions, overrides)
    return replace(options_from_settings(settings), **overrides)
