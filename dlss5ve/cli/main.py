"""``dlss5ve-cli`` command-line entry point.

Conventions:
- stdout is reserved for machine-readable output (``--json`` payloads, ``info``).
- progress and diagnostics go to stderr.
- defaults come from config.ini, replaced by ``--preset`` when given; flags
  override individual values on top of that. Validation of the values lives
  in the processing layer and is not repeated here.
- the effective UISettings are published to ``settings.storage.SETTINGS_STATE``
  so that the GPU lookups the processors and previews do see the same values
  the flags produced.
- the ``--json`` payload is built from the batch result the processing layer
  returns; since v8 the processing layer writes no manifest files, only the
  session log (``logs/app-<stamp>.log``), whose path the payload carries as
  ``log_path``.

Exit codes: 0 all inputs succeeded, 1 some or all inputs failed, 2 usage error
or missing input, 3 runtime or GPU unavailable, 130 interrupted by the user.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import traceback
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Sequence

from ..core.ffmpeg import CODEC_CHOICES, ENCODING_QUALITIES
from ..core.jobs import cancel_active_job
from ..core.naming import RENAME_MODES
from ..core.paths import CONFIG_PATH, ROOT
from ..core.runtime import NR_STYLES, UPSCALING_MODES
from ..frame_interpolation.models import ENGINE_CHOICES, FPS_CHOICES
from ..settings.models import CONTAINER_CHOICES, IMAGE_FORMAT_CHOICES, UISettings
from ..settings.presets import import_settings_preset
from ..settings.storage import SETTINGS_STATE, load_settings
from ..upscale.video.models import HDR_PRECISIONS, SCALE_FACTORS
from ..version import APP_VERSION, __version__
from .progress import ProgressReporter

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_USAGE = 2
EXIT_RUNTIME = 3
EXIT_CANCELLED = 130

NR_SCALE_CHOICES = tuple(UPSCALING_MODES)


class UsageError(ValueError):
    """A problem the caller can fix by changing arguments or inputs."""


# --------------------------------------------------------------------------- parser


def _load_settings(argv: Sequence[str]) -> UISettings:
    """Resolve config.ini plus an optional --preset before the real parser runs.

    The full parser shows these values as defaults, so the preset must be known
    before it is built.
    """
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--preset")
    known, _rest = pre.parse_known_args(argv)
    settings = load_settings(CONFIG_PATH)
    if known.preset:
        try:
            _name, settings = import_settings_preset(known.preset, settings)
        except ValueError as exc:
            raise UsageError(f"--preset: {exc}") from exc
    return settings


def _add_common(parser: argparse.ArgumentParser, settings: UISettings) -> None:
    group = parser.add_argument_group("common")
    group.add_argument(
        "--output-dir", metavar="DIR", default=None,
        help="Directory for rendered files (default: outputs/ next to the runtime).",
    )
    group.add_argument(
        "--preset", metavar="FILE",
        help="Settings preset JSON exported from the Settings tab; replaces config.ini values before flags apply.",
    )
    group.add_argument(
        "--ai-gpu", metavar="UUID", default=settings.ai_gpu_uuid,
        help="AI Processing GPU UUID from 'dlss5ve-cli info', or auto (default: %(default)s).",
    )
    group.add_argument(
        "--video-gpu", metavar="UUID", default=settings.video_gpu_uuid,
        help="Video Processing (NVENC) GPU UUID, or auto (default: %(default)s). Neural Rendering with --nr-gpu encodes on the AI GPU and ignores this.",
    )
    group.add_argument("--json", action="store_true", help="Write the batch result as JSON to stdout.")
    group.add_argument(
        "--progress", choices=("text", "json", "none"), default="text",
        help="Progress on stderr: text (one updating line plus a line per finished file), json (JSON Lines per file state), none (default: %(default)s).",
    )
    group.add_argument("--quiet", action="store_true", help="Suppress progress and the per-file summary on stderr.")


def _add_neural(parser: argparse.ArgumentParser, settings: UISettings, *, video: bool) -> None:
    group = parser.add_argument_group("neural rendering")
    group.add_argument("--nr-style", choices=tuple(NR_STYLES), default=settings.nr_style, help="(default: %(default)s)")
    group.add_argument("--nr-intensity", type=float, metavar="0..2", default=settings.nr_intensity, help="(default: %(default)s)")
    group.add_argument("--nr-passes", type=int, metavar="1..4", default=settings.nr_passes, help="Multi Pass: number of Neural Rendering passes (default: %(default)s)")
    group.add_argument("--local-tone", type=float, metavar="0..2", default=settings.local_tone_strength, help="Local Tone Strength (default: %(default)s)")
    group.add_argument("--local-structure", type=float, metavar="0..2", default=settings.local_structure_strength, help="Local Structure Strength (default: %(default)s)")
    group.add_argument("--skin-structure", type=float, metavar="-1..2", default=settings.skin_structure_strength, help="Skin Structure Strength; -1 is the native default (default: %(default)s)")
    group.add_argument("--automatic-mask", action=argparse.BooleanOptionalAction, default=settings.automatic_mask, help="Experimental runtime-generated mask.")
    scales = ", ".join(f"{factor:g}" for factor in NR_SCALE_CHOICES)
    group.add_argument(
        "--nr-scale", type=float, choices=NR_SCALE_CHOICES, metavar="FACTOR", default=settings.upscaling_factor,
        help=f"Resolution entering Neural Rendering as a fraction of the source: {scales}; below 1 is a Lanczos downscale, the output keeps that size (default: %(default)s)",
    )
    group.add_argument("--nr-gpu", action=argparse.BooleanOptionalAction, default=settings.nr_gpu_mode, help="Processing Engine Path: keep frames in VRAM (CUDA/D3D12 interop); --no-nr-gpu stages through system memory.")

    composition = parser.add_argument_group("composition")
    composition.add_argument("--color-strength", type=float, metavar="0..1", default=settings.nr_color_strength, help="NR Color Strength; 0 keeps the source colour (default: %(default)s)")
    composition.add_argument("--tone-preservation", type=float, metavar="0..1", default=settings.tone_preservation, help="Tone Preservation; 1 keeps the source tone (default: %(default)s)")
    composition.add_argument("--face-skin-protection", type=float, metavar="0..1", default=settings.face_skin_protection, help="(default: %(default)s)")
    composition.add_argument("--grain-preservation", type=float, metavar="0..1", default=settings.grain_preservation, help="(default: %(default)s)")
    composition.add_argument("--nr-mask", metavar="FILE", default=None, help="Custom NR Mask image; luminance times alpha limits where Neural Rendering is applied.")
    composition.add_argument("--mask-feather", type=int, metavar="0..128", default=settings.mask_feather, help="Blur radius of the Custom NR Mask in output pixels (default: %(default)s)")
    if video:
        composition.add_argument("--shimmer-suppression", type=float, metavar="0..1", default=settings.shimmer_suppression, help="Temporal stabilization of fine detail between frames (default: %(default)s)")


def _add_encoding(parser: argparse.ArgumentParser, codec: str, container: str, quality: str, hdr: bool | None) -> None:
    """Codec flags; ``hdr`` is the HDR Mode default, or None when the command defines its own --hdr."""
    group = parser.add_argument_group("encoding")
    group.add_argument("--codec", choices=CODEC_CHOICES, default=codec, help="(default: %(default)s)")
    group.add_argument("--container", choices=CONTAINER_CHOICES, default=container, help="(default: %(default)s)")
    group.add_argument("--encoding-quality", choices=ENCODING_QUALITIES, default=quality, help="(default: %(default)s)")
    if hdr is not None:
        group.add_argument("--hdr", action=argparse.BooleanOptionalAction, default=hdr, help="10-bit output that keeps HDR metadata; H.265, AV1, and ProRes only.")


def _add_naming(parser: argparse.ArgumentParser, mode: str, suffix: str) -> None:
    group = parser.add_argument_group("naming")
    group.add_argument("--rename", choices=RENAME_MODES, default=mode, help="Auto adds a timestamp; Copy keeps the source name; Custom appends --suffix (default: %(default)s)")
    group.add_argument("--suffix", default=suffix, help="Suffix for --rename Custom (default: %(default)s)")


def _add_upscale_sizing(parser: argparse.ArgumentParser, settings: UISettings, prefix: str) -> None:
    """RTX VSR quality and output size; defaults come from the upscale_* or upscale_image_* settings."""
    def saved(name: str) -> Any:
        return getattr(settings, prefix + name)

    if saved("size_mode") == "Scale factor":
        saved_size = f"{saved('scale_factor'):g}x from settings"
    elif saved("aspect_lock"):
        saved_size = f"{saved('width')} px wide from settings"
    else:
        saved_size = f"{saved('width')}x{saved('height')} from settings"
    factors = ", ".join(f"{factor:g}" for _label, factor in SCALE_FACTORS)
    group = parser.add_argument_group("sizing")
    group.add_argument("--vsr-quality", type=int, metavar="1..4", default=saved("vsr_quality"), help="RTX Video Super Resolution quality (default: %(default)s)")
    group.add_argument("--scale", type=float, metavar="FACTOR", default=None, help=f"Output size as a multiple of the source, at least 1; the WebUI offers {factors} (default: {saved_size})")
    group.add_argument("--width", type=int, metavar="PX", default=None, help="Output width in pixels instead of --scale; the height follows the source aspect ratio unless --no-aspect-lock.")
    group.add_argument("--height", type=int, metavar="PX", default=None, help="Output height in pixels; used with --width and --no-aspect-lock.")
    group.add_argument("--aspect-lock", action=argparse.BooleanOptionalAction, default=saved("aspect_lock"), help="Derive the height from --width and the source aspect ratio.")


def _sizing_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """Translate --scale / --width / --height into the size_mode the Options use."""
    overrides: dict[str, Any] = {"aspect_lock": bool(args.aspect_lock)}
    custom = args.width is not None or args.height is not None
    if args.scale is not None and custom:
        raise UsageError("Use either --scale or --width/--height, not both.")
    if args.scale is not None:
        overrides.update(size_mode="Scale factor", scale_factor=args.scale)
    elif custom:
        if args.width is None:
            raise UsageError("--height needs --width; with --aspect-lock the height follows the width.")
        overrides.update(size_mode="Custom dimensions", width=args.width)
        if args.height is not None:
            overrides["height"] = args.height
    return overrides


_BANNER = f"dlss5ve-cli {__version__} (DLSS 5 Visual Enhancer {APP_VERSION})"


def _command(commands: Any, name: str, help_text: str) -> argparse.ArgumentParser:
    """Add a subcommand whose --help and --version also show the version banner."""
    parser = commands.add_parser(name, help=help_text, description=f"{_BANNER}: {help_text}")
    parser.add_argument("--version", action="version", version=_BANNER)
    return parser


def build_parser(settings: UISettings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dlss5ve-cli",
        description=f"{_BANNER}: Neural Rendering for images and videos, DLSS Frame Generation, and RTX Video Super Resolution / HDR.",
        epilog="Defaults come from config.ini (or --preset). Exit codes: 0 ok, 1 some inputs failed, 2 usage, 3 runtime/GPU unavailable, 130 interrupted.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (DLSS 5 Visual Enhancer {APP_VERSION})")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    inputs_help = "Files, or folders whose supported files are processed in name order (subfolders excluded)."

    image = _command(commands, "image", "Neural Rendering for images.")
    image.add_argument("inputs", nargs="+", metavar="PATH", help=inputs_help)
    _add_common(image, settings)
    _add_neural(image, settings, video=False)
    output = image.add_argument_group("output")
    output.add_argument("--format", choices=IMAGE_FORMAT_CHOICES, default=settings.image_format, help="(default: %(default)s)")
    output.add_argument("--quality", type=int, metavar="1..100", default=settings.image_quality, help="Lossy quality for JPEG, WebP, AVIF (default: %(default)s)")
    output.add_argument("--zip", action="store_true", help="Also write a ZIP of the successful outputs next to them.")
    _add_naming(image, settings.image_rename_mode, settings.image_custom_suffix)

    video = _command(commands, "video", "Neural Rendering for videos.")
    video.add_argument("inputs", nargs="+", metavar="PATH", help=inputs_help)
    _add_common(video, settings)
    _add_neural(video, settings, video=True)
    _add_encoding(video, settings.codec, settings.container, settings.quality, settings.hdr_mode)
    _add_naming(video, settings.video_rename_mode, settings.video_custom_suffix)
    output = video.add_argument_group("output")
    output.add_argument("--zip", action="store_true", help="Also write a ZIP of the successful outputs next to them (two or more inputs).")
    output.add_argument("--preview-seconds", type=float, metavar="SEC", help="Render only the first SEC seconds with the chosen codec.")
    output.add_argument("--preview-frames", type=int, metavar="N", help="Render only the first N frames with the chosen codec.")

    interpolate = _command(commands, "interpolate", "DLSS Frame Generation to a target frame rate.")
    interpolate.add_argument("inputs", nargs="+", metavar="PATH", help=inputs_help)
    _add_common(interpolate, settings)
    frame = interpolate.add_argument_group("frame generation")
    frame.add_argument("--fps", choices=FPS_CHOICES, default=settings.frame_interpolation_target_fps, help="(default: %(default)s)")
    frame.add_argument("--engine", choices=ENGINE_CHOICES, default=settings.frame_interpolation_engine, help="(default: %(default)s)")
    _add_encoding(
        interpolate, settings.frame_interpolation_codec, settings.frame_interpolation_container,
        settings.frame_interpolation_quality, settings.frame_interpolation_hdr_mode,
    )
    _add_naming(interpolate, settings.frame_interpolation_rename_mode, settings.frame_interpolation_custom_suffix)
    interpolate.add_argument("--preview-seconds", type=float, metavar="SEC", help="Interpolate only the first SEC seconds with the chosen codec.")

    upscale_image = _command(commands, "upscale-image", "RTX Video Super Resolution for images.")
    upscale_image.add_argument("inputs", nargs="+", metavar="PATH", help=inputs_help)
    _add_common(upscale_image, settings)
    _add_upscale_sizing(upscale_image, settings, "upscale_image_")
    output = upscale_image.add_argument_group("output")
    output.add_argument("--format", choices=IMAGE_FORMAT_CHOICES, default=settings.upscale_image_output_format, help="(default: %(default)s)")
    output.add_argument("--quality", type=int, metavar="1..100", default=settings.upscale_image_quality, help="Lossy quality for JPEG, WebP, AVIF (default: %(default)s)")
    output.add_argument("--preserve-metadata", action=argparse.BooleanOptionalAction, default=settings.upscale_image_preserve_metadata, help="Keep EXIF, DPI, and XMP metadata from the source.")
    output.add_argument("--zip", action="store_true", help="Also write a ZIP of the successful outputs next to them.")
    _add_naming(upscale_image, settings.upscale_image_rename_mode, settings.upscale_image_custom_suffix)

    upscale_video = _command(commands, "upscale-video", "RTX Video Super Resolution and RTX Video HDR for videos.")
    upscale_video.add_argument("inputs", nargs="+", metavar="PATH", help=inputs_help)
    _add_common(upscale_video, settings)
    _add_upscale_sizing(upscale_video, settings, "upscale_")
    upscale_video.add_argument("--vsr", action=argparse.BooleanOptionalAction, default=settings.upscale_vsr_enabled, help="RTX Video Super Resolution; --no-vsr keeps the source size and applies only RTX Video HDR.")
    hdr = upscale_video.add_argument_group("RTX Video HDR")
    hdr.add_argument("--hdr", action=argparse.BooleanOptionalAction, default=settings.upscale_hdr_enabled, help="Convert SDR to HDR10 with RTX Video HDR; H.265, AV1, and ProRes only.")
    hdr.add_argument("--hdr-contrast", type=int, metavar="0..200", default=settings.upscale_hdr_contrast, help="(default: %(default)s)")
    hdr.add_argument("--hdr-saturation", type=int, metavar="0..200", default=settings.upscale_hdr_saturation, help="(default: %(default)s)")
    hdr.add_argument("--hdr-middle-gray", type=int, metavar="10..100", default=settings.upscale_hdr_middle_gray, help="(default: %(default)s)")
    hdr.add_argument("--hdr-peak-luminance", type=int, metavar="400..2000", default=settings.upscale_hdr_peak_luminance, help="Display peak in nits (default: %(default)s)")
    hdr.add_argument("--hdr-precision", choices=HDR_PRECISIONS, default=settings.upscale_hdr_precision, help="Frame format handed to the encoder (default: %(default)s)")
    _add_encoding(upscale_video, settings.upscale_codec, settings.upscale_container, settings.upscale_quality, None)
    _add_naming(upscale_video, settings.upscale_rename_mode, settings.upscale_custom_suffix)
    upscale_video.add_argument("--preview-seconds", type=float, metavar="SEC", help="Process only the first SEC seconds.")

    info = _command(commands, "info", "Show the version, GPUs, encoders, the Neural Rendering bridge, frame-generation and RTX Video capabilities, and choices.")
    info.add_argument("--json", action="store_true", help="Write the report as JSON instead of text.")
    info.add_argument("--ai-gpu", metavar="UUID", default=settings.ai_gpu_uuid, help="GPU to probe for frame generation (default: %(default)s).")
    info.add_argument("--preset", metavar="FILE", help=argparse.SUPPRESS)
    return parser


# --------------------------------------------------------------------------- commands


def _resolve_inputs(values: Sequence[str], kind: str) -> list[Path]:
    """Expand folders to their supported files; every file must exist."""
    from ..core.disk_paths import supported_file

    paths: list[Path] = []
    missing: list[str] = []
    for value in values:
        path = Path(value)
        if path.is_dir():
            files = sorted(
                (item for item in path.iterdir() if item.is_file() and supported_file(item, kind)),
                key=lambda item: (item.name.casefold(), item.name),
            )
            if not files:
                raise UsageError(f"No supported {kind} files in {path} (subfolders are excluded).")
            paths.extend(files)
        elif path.is_file():
            paths.append(path)
        else:
            missing.append(str(path))
    if missing:
        raise UsageError("Input not found:\n" + "\n".join(missing))
    return paths


def _publish_settings(settings: UISettings, args: argparse.Namespace) -> UISettings:
    """Make the effective settings visible to the processing layer.

    The previews and the Live pipeline look up GPUs through settings.storage,
    not through the Options they receive.
    """
    effective = replace(
        settings,
        ai_gpu_uuid=args.ai_gpu,
        video_gpu_uuid=getattr(args, "video_gpu", settings.video_gpu_uuid),
    )
    with SETTINGS_STATE.lock:
        SETTINGS_STATE.current = effective
    return effective


def _neural_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """The Neural Rendering flags as Options fields; the mask file is validated here."""
    from ..core.nr_composition import inspect_nr_mask

    try:
        nr_mask = inspect_nr_mask(args.nr_mask)
    except ValueError as exc:
        raise UsageError(f"--nr-mask: {exc}") from exc
    overrides = {
        "ai_gpu_uuid": args.ai_gpu,
        "nr_style": args.nr_style,
        "nr_intensity": args.nr_intensity,
        "nr_passes": args.nr_passes,
        "local_tone_strength": args.local_tone,
        "local_structure_strength": args.local_structure,
        "skin_structure_strength": args.skin_structure,
        "nr_color_strength": args.color_strength,
        "tone_preservation": args.tone_preservation,
        "face_skin_protection": args.face_skin_protection,
        "grain_preservation": args.grain_preservation,
        "mask_feather": args.mask_feather,
        "nr_mask": nr_mask,
        "automatic_mask": bool(args.automatic_mask),
        "nr_gpu_mode": bool(args.nr_gpu),
        "upscaling_factor": args.nr_scale,
    }
    if hasattr(args, "shimmer_suppression"):
        overrides["shimmer_suppression"] = args.shimmer_suppression
    return overrides


def _check_video_like(options: Any, *, neural: bool) -> None:
    """Reject bad arguments before any GPU work starts.

    The batch functions turn per-file exceptions into failures (exit 1); an
    argument typo should surface as a usage error instead, so the processing
    layer's own validators run here first.
    """
    from ..core.ffmpeg import validate_codec_container
    from ..core.naming import validate_rename
    from ..core.runtime import resolve_native_settings, resolve_upscaling_mode

    validate_codec_container(options.codec, options.container)
    validate_rename(options.rename_mode, options.custom_suffix)
    if neural:
        resolve_native_settings(options)
        resolve_upscaling_mode(options.upscaling_factor)
    preview = getattr(options, "preview_seconds", None)
    if preview is not None and not preview > 0:
        raise UsageError("--preview-seconds must be a positive number of seconds.")
    frames = getattr(options, "preview_frames", None)
    if frames is not None and frames <= 0:
        raise UsageError("--preview-frames must be a positive number of frames.")
    if preview is not None and frames is not None:
        raise UsageError("Use either --preview-seconds or --preview-frames, not both.")


def _check_output_dir(value: str | None) -> str:
    """Create or validate the output directory before any GPU work starts."""
    from ..core.disk_paths import prepare_output_dir

    try:
        return str(prepare_output_dir(value))
    except (OSError, ValueError) as exc:
        raise UsageError(f"--output-dir: {exc}") from exc


def _payload(command: str, result: Any, options: Any, output_directory: str, **extra: Any) -> dict[str, Any]:
    """The batch result as one JSON document.

    ``successes`` and ``failures`` are the processing layer's result
    dataclasses; ``status`` uses one vocabulary for every command
    (``success``, ``partial``, ``cancelled``). ``options`` replaces a Custom
    NR Mask selection with its summary so no temporary path leaks.
    """
    from ..core.nr_composition import report_options

    successes = [asdict(item) for item in result.successes]
    failures = [asdict(item) for item in result.failures]
    cancelled = bool(result.cancelled)
    status = "cancelled" if cancelled else ("partial" if failures else "success")
    has_mask = any(field == "nr_mask" for field in getattr(type(options), "__dataclass_fields__", {}))
    return {
        "command": command,
        "status": status,
        "cancelled": cancelled,
        "output_directory": output_directory,
        "log_path": result.manifest_path,
        "options": report_options(options) if has_mask else asdict(options),
        "successes": successes,
        "failures": failures,
        **extra,
    }


def run_image(args: argparse.Namespace, settings: UISettings, reporter: ProgressReporter) -> dict[str, Any]:
    inputs = _resolve_inputs(args.inputs, "image")
    try:
        from ..neural_rendering.image import convert_images
    except ImportError as exc:
        raise RuntimeError(
            f"Image decoding packages are missing ({exc.name}). Install with the 'image' extra: uv sync --extra image"
        ) from exc
    from ..core.runtime import resolve_native_settings, resolve_upscaling_mode
    from ..settings.factory import image_options

    options = image_options(
        settings,
        **_neural_overrides(args),
        output_format=args.format,
        quality=args.quality,
        rename_mode=args.rename,
        custom_suffix=args.suffix,
    )
    resolve_native_settings(options)
    resolve_upscaling_mode(options.upscaling_factor)
    output_directory = _check_output_dir(args.output_dir)
    reporter.register(inputs)
    result = convert_images(
        inputs, options, reporter, output_dir=args.output_dir, on_item_update=reporter.item_update,
        # Thumbnails for the browser gallery are a WebUI concern.
        generate_previews=False, create_zip=bool(args.zip),
    )
    return _payload("image", result, options, output_directory, zip_path=result.zip_path)


def run_video(args: argparse.Namespace, settings: UISettings, reporter: ProgressReporter) -> dict[str, Any]:
    inputs = _resolve_inputs(args.inputs, "video")
    from ..settings.factory import video_options
    from ..neural_rendering.video import convert_videos

    options = video_options(
        settings,
        **_neural_overrides(args),
        video_gpu_uuid=args.video_gpu,
        codec=args.codec,
        container=args.container,
        quality=args.encoding_quality,
        hdr_mode=bool(args.hdr),
        rename_mode=args.rename,
        custom_suffix=args.suffix,
        preview_seconds=args.preview_seconds,
        preview_frames=args.preview_frames,
        # The CLI has no browser to please: previews keep the caller's codec.
        preview_compat=False,
    )
    _check_video_like(options, neural=True)
    output_directory = _check_output_dir(args.output_dir)
    reporter.register(inputs)
    result = convert_videos(
        inputs, options, reporter, output_dir=args.output_dir, on_item_update=reporter.item_update,
        create_archive=bool(args.zip),
    )
    return _payload(
        "video", result, options, output_directory,
        zip_path=result.archive_path, zip_error=result.archive_error or None,
    )


def run_interpolate(args: argparse.Namespace, settings: UISettings, reporter: ProgressReporter) -> dict[str, Any]:
    inputs = _resolve_inputs(args.inputs, "video")
    from ..frame_interpolation import interpolate_videos
    from ..settings.factory import frame_interpolation_options

    options = frame_interpolation_options(
        settings,
        ai_gpu_uuid=args.ai_gpu,
        video_gpu_uuid=args.video_gpu,
        target_fps=args.fps,
        engine=args.engine,
        codec=args.codec,
        container=args.container,
        quality=args.encoding_quality,
        hdr_mode=bool(args.hdr),
        rename_mode=args.rename,
        custom_suffix=args.suffix,
        preview_seconds=args.preview_seconds,
        preview_compat=False,
    )
    _check_video_like(options, neural=False)
    options.target_rate  # raises ValueError for an unsupported FPS choice
    output_directory = _check_output_dir(args.output_dir)
    reporter.register(inputs)
    result = interpolate_videos(inputs, options, reporter, output_dir=args.output_dir, on_item_update=reporter.item_update)
    return _payload("interpolate", result, options, output_directory)


def run_upscale_image(args: argparse.Namespace, settings: UISettings, reporter: ProgressReporter) -> dict[str, Any]:
    inputs = _resolve_inputs(args.inputs, "image")
    try:
        from ..upscale.image.batch import upscale_images
    except ImportError as exc:
        raise RuntimeError(
            f"Image decoding packages are missing ({exc.name}). Install with the 'image' extra: uv sync --extra image"
        ) from exc
    from ..settings.factory import upscale_image_options

    options = upscale_image_options(
        settings,
        ai_gpu_uuid=args.ai_gpu,
        vsr_quality=args.vsr_quality,
        **_sizing_overrides(args),
        output_format=args.format,
        quality=args.quality,
        preserve_metadata=bool(args.preserve_metadata),
        rename_mode=args.rename,
        custom_suffix=args.suffix,
    )
    options.validate()
    output_directory = _check_output_dir(args.output_dir)
    reporter.register(inputs)
    result = upscale_images(
        inputs, options, reporter, output_dir=args.output_dir, on_item_update=reporter.item_update,
        generate_previews=False,
    )
    zip_path = None
    if args.zip and result.successes and not result.cancelled:
        # The Upscale batch leaves the archive to its caller, unlike Neural Rendering.
        from ..core.disk_paths import create_media_archive

        zip_path = create_media_archive(
            [item.output_path for item in result.successes], args.output_dir, "RTXVIDEO_IMAGE_BATCH",
        )
    return _payload("upscale-image", result, options, output_directory, zip_path=zip_path)


def run_upscale_video(args: argparse.Namespace, settings: UISettings, reporter: ProgressReporter) -> dict[str, Any]:
    inputs = _resolve_inputs(args.inputs, "video")
    from ..settings.factory import upscale_video_options
    from ..upscale.video.batch import upscale_videos

    options = upscale_video_options(
        settings,
        ai_gpu_uuid=args.ai_gpu,
        video_gpu_uuid=args.video_gpu,
        vsr_enabled=bool(args.vsr),
        vsr_quality=args.vsr_quality,
        **_sizing_overrides(args),
        hdr_enabled=bool(args.hdr),
        hdr_contrast=args.hdr_contrast,
        hdr_saturation=args.hdr_saturation,
        hdr_middle_gray=args.hdr_middle_gray,
        hdr_peak_luminance=args.hdr_peak_luminance,
        hdr_precision=args.hdr_precision,
        codec=args.codec,
        container=args.container,
        quality=args.encoding_quality,
        rename_mode=args.rename,
        custom_suffix=args.suffix,
        preview_seconds=args.preview_seconds,
    )
    options.validate()
    output_directory = _check_output_dir(args.output_dir)
    reporter.register(inputs)
    result = upscale_videos(inputs, options, reporter, output_dir=args.output_dir, on_item_update=reporter.item_update)
    return _payload("upscale-video", result, options, output_directory)


def collect_info(ai_gpu_uuid: str) -> dict[str, Any]:
    """Gather what a caller needs to choose arguments; each probe fails independently."""
    from ..core.ffmpeg import probe_nvenc_codecs
    from ..core.gpu_detection import detect_gpus
    from ..core.runtime import prepare_runtime, validate_runtime_files
    from ..frame_interpolation.capabilities import probe_frame_interpolation_capabilities

    report: dict[str, Any] = {
        "version": __version__, "app_version": APP_VERSION, "root": str(ROOT), "config": str(CONFIG_PATH),
    }
    try:
        validate_runtime_files()
        report["runtime_files"] = "ok"
    except Exception as exc:
        report["runtime_files"] = str(exc)
    try:
        gpus = [dict(gpu) for gpu in detect_gpus()]
        for gpu in gpus:
            try:
                gpu["nvenc_codecs"] = list(probe_nvenc_codecs(int(gpu.get("cuda_ordinal", gpu["index"]))))
            except Exception as exc:
                gpu["nvenc_codecs"] = str(exc)
        report["gpus"] = gpus
    except Exception as exc:
        report["gpus"] = str(exc)
    try:
        report["encoders"] = dict(prepare_runtime().encoder_inventory)
    except Exception as exc:
        report["encoders"] = str(exc)
    try:
        # Loading the bridge DLL reads its version and checks the frame ABI;
        # NGX itself is initialized only by a render session.
        from ..core.neural_bridge import BRIDGE_ABI_VERSION, BRIDGE_MANAGER
        from ..core.paths import DLSSNR_BRIDGE

        BRIDGE_MANAGER._load()
        report["neural_bridge"] = {
            "path": str(DLSSNR_BRIDGE), "version": BRIDGE_MANAGER.version, "abi_version": BRIDGE_ABI_VERSION,
        }
    except Exception as exc:
        report["neural_bridge"] = str(exc)
    try:
        report["frame_generation"] = asdict(probe_frame_interpolation_capabilities(ai_gpu_uuid))
    except Exception as exc:
        report["frame_generation"] = str(exc)
    try:
        from ..upscale.video.native import probe_capabilities

        report["rtx_video"] = asdict(probe_capabilities(ai_gpu_uuid))
    except Exception as exc:
        report["rtx_video"] = str(exc)
    report["choices"] = {
        "nr_scale": list(NR_SCALE_CHOICES),
        "nr_style": list(NR_STYLES),
        "nr_passes": [1, 2, 3, 4],
        "codec": list(CODEC_CHOICES),
        "container": list(CONTAINER_CHOICES),
        "encoding_quality": list(ENCODING_QUALITIES),
        "image_format": list(IMAGE_FORMAT_CHOICES),
        "fps": list(FPS_CHOICES),
        "engine": list(ENGINE_CHOICES),
        "rename": list(RENAME_MODES),
        "vsr_quality": [1, 2, 3, 4],
        "upscale_scale": [factor for _label, factor in SCALE_FACTORS],
        "hdr_precision": list(HDR_PRECISIONS),
    }
    return report


def _print_info(report: dict[str, Any]) -> None:
    out = sys.stdout
    out.write(f"dlss5ve-cli {report['version']} | DLSS 5 Visual Enhancer {report['app_version']}\n")
    out.write(f"Root: {report['root']}\nConfig: {report['config']}\nRuntime files: {report['runtime_files']}\n\n")
    gpus = report["gpus"]
    if isinstance(gpus, str):
        out.write(f"GPUs: {gpus}\n\n")
    else:
        out.write("GPUs:\n")
        for gpu in gpus:
            memory = float(gpu.get("memory_mb", 0)) / 1024
            flag = "AI-compatible" if gpu.get("ai_compatible") else str(gpu.get("compatibility_error") or "not compatible")
            out.write(f"  [{gpu.get('index')}] {gpu.get('name')} | {memory:.0f} GB | driver {gpu.get('driver')} | {flag}\n")
            out.write(f"      uuid {gpu.get('uuid')} | PCI {gpu.get('pci_bus_id') or '?'} | CUDA ordinal {gpu.get('cuda_ordinal')}\n")
            nvenc = gpu.get("nvenc_codecs")
            out.write(f"      NVENC: {', '.join(nvenc) if isinstance(nvenc, list) and nvenc else (nvenc if isinstance(nvenc, str) else 'none')}\n")
        out.write("\n")
    encoders = report["encoders"]
    if isinstance(encoders, dict):
        available = [name for name, ok in encoders.items() if ok]
        out.write(f"FFmpeg encoders: {', '.join(available) or 'none'}\n")
    else:
        out.write(f"FFmpeg encoders: {encoders}\n")
    bridge = report["neural_bridge"]
    if isinstance(bridge, dict):
        out.write(f"Neural Rendering bridge: {bridge.get('version')} | frame ABI {bridge.get('abi_version')}\n")
    else:
        out.write(f"Neural Rendering bridge: {bridge}\n")
    capabilities = report["frame_generation"]
    if isinstance(capabilities, dict):
        state = "available" if capabilities.get("available") else "unavailable"
        out.write(
            f"Frame generation: {state} | native {capabilities.get('native_multiplier')}x "
            f"| cascade {'yes' if capabilities.get('cascade_available') else 'no'} "
            f"| HAGS {'on' if capabilities.get('hags_enabled') else 'off'} "
            f"| runtime {capabilities.get('runtime_version')}\n"
        )
        if capabilities.get("detail"):
            out.write(f"  {capabilities['detail']}\n")
    else:
        out.write(f"Frame generation: {capabilities}\n")
    rtx_video = report["rtx_video"]
    if isinstance(rtx_video, dict):
        def state(capability: dict[str, Any]) -> str:
            if capability.get("available"):
                return "available"
            return (
                f"unavailable (needs driver {capability.get('min_driver_major', 0)}.{capability.get('min_driver_minor', 0)}, "
                f"init result 0x{int(capability.get('init_result', 0) or 0):08X})"
            )
        out.write(
            f"RTX Video: VSR {state(rtx_video.get('vsr') or {})} | HDR {state(rtx_video.get('hdr') or {})} "
            f"| SDK {rtx_video.get('sdk_version')} | worker {rtx_video.get('worker_version')}\n"
        )
    else:
        out.write(f"RTX Video: {rtx_video}\n")
    out.write("\nChoices:\n")
    for key, values in report["choices"].items():
        out.write(f"  {key}: {', '.join(f'{v:g}' if isinstance(v, float) else str(v) for v in values)}\n")


def _summarize(payload: dict[str, Any], stream) -> None:
    for item in payload["successes"]:
        result = item.get("result", item)
        stream.write(f"OK    {Path(item['input_path']).name} -> {result['output_path']}\n")
    for item in payload["failures"]:
        state = "STOP " if item.get("cancelled") else "FAIL "
        error = str(item["error"]).splitlines()[0] if item["error"] else ""
        stream.write(f"{state} {Path(item['input_path']).name}: {error}\n")
    extra = f" | zip: {payload['zip_path']}" if payload.get("zip_path") else ""
    if payload.get("zip_error"):
        extra += f" | zip failed: {payload['zip_error']}"
    stream.write(
        f"{payload['status']}: {len(payload['successes'])} ok, {len(payload['failures'])} failed"
        f" | output: {payload['output_directory']} | log: {payload['log_path']}{extra}\n"
    )


# --------------------------------------------------------------------------- entry


class _StopOnInterrupt:
    """First Ctrl+C asks the running batch to stop cleanly; the second one aborts."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, _signum: int, _frame: Any) -> None:
        self.count += 1
        if self.count == 1:
            sys.stderr.write("\nStop requested; the current file is being cleaned up (Ctrl+C again to abort).\n")
            cancel_active_job()
            return
        raise KeyboardInterrupt


def _configure_streams() -> None:
    for stream, kwargs in ((sys.stdout, {"encoding": "utf-8"}), (sys.stderr, {"errors": "replace"})):
        try:
            stream.reconfigure(**kwargs)  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _configure_streams()
    try:
        settings = _load_settings(argv)
    except UsageError as exc:
        sys.stderr.write(f"dlss5ve-cli: error: {exc}\n")
        return EXIT_USAGE
    parser = build_parser(settings)
    args = parser.parse_args(argv)

    if args.command == "info":
        report = collect_info(args.ai_gpu)
        if args.json:
            sys.stdout.write(json.dumps(report, indent=2, default=str) + "\n")
        else:
            _print_info(report)
        return EXIT_OK

    settings = _publish_settings(settings, args)
    reporter = ProgressReporter("none" if args.quiet else args.progress)
    handlers = {
        "image": run_image, "video": run_video, "interpolate": run_interpolate,
        "upscale-image": run_upscale_image, "upscale-video": run_upscale_video,
    }
    interrupt = _StopOnInterrupt()
    previous = signal.signal(signal.SIGINT, interrupt)
    try:
        payload = handlers[args.command](args, settings, reporter)
    except KeyboardInterrupt:
        reporter.finish()
        sys.stderr.write("Aborted.\n")
        return EXIT_CANCELLED
    except UsageError as exc:
        reporter.finish()
        sys.stderr.write(f"dlss5ve-cli: error: {exc}\n")
        return EXIT_USAGE
    except (ValueError, FileNotFoundError, TypeError) as exc:
        reporter.finish()
        sys.stderr.write(f"dlss5ve-cli: error: {exc}\n")
        return EXIT_USAGE
    except RuntimeError as exc:
        reporter.finish()
        sys.stderr.write(f"dlss5ve-cli: runtime error: {exc}\n")
        return EXIT_RUNTIME
    except Exception:
        reporter.finish()
        traceback.print_exc()
        return EXIT_PARTIAL
    finally:
        signal.signal(signal.SIGINT, previous)

    reporter.finish()
    if not args.quiet:
        _summarize(payload, sys.stderr)
    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2, default=str) + "\n")
    if payload["status"] == "cancelled":
        return EXIT_CANCELLED
    return EXIT_PARTIAL if payload["failures"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
