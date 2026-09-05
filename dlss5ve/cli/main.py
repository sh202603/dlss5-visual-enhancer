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
from ..core.runtime import DLSS_MODEL_PRESETS, NR_PRESETS, NR_STYLES, UPSCALING_MODES
from ..frame_interpolation.models import ENGINE_CHOICES, FPS_CHOICES
from ..settings.models import CONTAINER_CHOICES, IMAGE_FORMAT_CHOICES, UISettings
from ..settings.presets import import_settings_preset
from ..settings.storage import SETTINGS_STATE, load_settings
from .progress import ProgressReporter

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_USAGE = 2
EXIT_RUNTIME = 3
EXIT_CANCELLED = 130


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
        help="Video Processing (NVENC) GPU UUID, or auto (default: %(default)s).",
    )
    group.add_argument("--json", action="store_true", help="Write the batch result as JSON to stdout.")
    group.add_argument(
        "--progress", choices=("text", "json", "none"), default="text",
        help="Progress on stderr: text (one updating line plus a line per finished file), json (JSON Lines per file state), none (default: %(default)s).",
    )
    group.add_argument("--quiet", action="store_true", help="Suppress progress and the per-file summary on stderr.")


def _add_neural(parser: argparse.ArgumentParser, settings: UISettings) -> None:
    group = parser.add_argument_group("neural rendering")
    group.add_argument("--nr-preset", choices=tuple(NR_PRESETS), default=settings.nr_preset, help="(default: %(default)s)")
    group.add_argument("--nr-style", choices=tuple(NR_STYLES), default=settings.nr_style, help="(default: %(default)s)")
    group.add_argument("--nr-intensity", type=float, metavar="0..2", default=settings.nr_intensity, help="(default: %(default)s)")
    group.add_argument("--local-tone", type=float, metavar="0..2", default=settings.local_tone_strength, help="Local Tone Strength (default: %(default)s)")
    group.add_argument("--local-structure", type=float, metavar="0..2", default=settings.local_structure_strength, help="Local Structure Strength (default: %(default)s)")
    group.add_argument("--skin-structure", type=float, metavar="-1..2", default=settings.skin_structure_strength, help="Skin Structure Strength; -1 is the native default (default: %(default)s)")
    group.add_argument("--automatic-mask", action=argparse.BooleanOptionalAction, default=settings.automatic_mask, help="Experimental runtime-generated mask.")
    group.add_argument("--dlss-model-preset", choices=tuple(DLSS_MODEL_PRESETS), default=settings.dlss_model_preset, help="(default: %(default)s)")
    factors = ", ".join(f"{factor:g}" for factor in UPSCALING_MODES)
    group.add_argument("--upscale", type=float, metavar="FACTOR", default=settings.upscaling_factor, help=f"One of {factors}; 1 is DLAA (default: %(default)s)")


def _add_encoding(parser: argparse.ArgumentParser, codec: str, container: str, quality: str, hdr: bool) -> None:
    group = parser.add_argument_group("encoding")
    group.add_argument("--codec", choices=CODEC_CHOICES, default=codec, help="(default: %(default)s)")
    group.add_argument("--container", choices=CONTAINER_CHOICES, default=container, help="(default: %(default)s)")
    group.add_argument("--encoding-quality", choices=ENCODING_QUALITIES, default=quality, help="(default: %(default)s)")
    group.add_argument("--hdr", action=argparse.BooleanOptionalAction, default=hdr, help="10-bit output that keeps HDR metadata; H.265, AV1, and ProRes only.")


def _add_naming(parser: argparse.ArgumentParser, mode: str, suffix: str) -> None:
    group = parser.add_argument_group("naming")
    group.add_argument("--rename", choices=RENAME_MODES, default=mode, help="Auto adds a timestamp; Copy keeps the source name; Custom appends --suffix (default: %(default)s)")
    group.add_argument("--suffix", default=suffix, help="Suffix for --rename Custom (default: %(default)s)")


def build_parser(settings: UISettings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dlss5ve-cli",
        description="DLSS 5 Visual Enhancer command line: Neural Rendering for images and videos, and DLSS Frame Generation.",
        epilog="Defaults come from config.ini (or --preset). Exit codes: 0 ok, 1 some inputs failed, 2 usage, 3 runtime/GPU unavailable, 130 interrupted.",
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    inputs_help = "Files, or folders whose supported files are processed in name order (subfolders excluded)."

    image = commands.add_parser("image", help="Neural Rendering and upscaling for images.")
    image.add_argument("inputs", nargs="+", metavar="PATH", help=inputs_help)
    _add_common(image, settings)
    _add_neural(image, settings)
    output = image.add_argument_group("output")
    output.add_argument("--format", choices=IMAGE_FORMAT_CHOICES, default=settings.image_format, help="(default: %(default)s)")
    output.add_argument("--quality", type=int, metavar="1..100", default=settings.image_quality, help="Lossy quality for JPEG, WebP, AVIF (default: %(default)s)")
    output.add_argument("--zip", action="store_true", help="Also write a ZIP of the successful outputs next to them.")
    _add_naming(image, settings.image_rename_mode, settings.image_custom_suffix)

    video = commands.add_parser("video", help="Neural Rendering and upscaling for videos.")
    video.add_argument("inputs", nargs="+", metavar="PATH", help=inputs_help)
    _add_common(video, settings)
    _add_neural(video, settings)
    _add_encoding(video, settings.codec, settings.container, settings.quality, settings.hdr_mode)
    _add_naming(video, settings.video_rename_mode, settings.video_custom_suffix)
    video.add_argument("--preview-seconds", type=float, metavar="SEC", help="Render only the first SEC seconds with the chosen codec.")

    interpolate = commands.add_parser("interpolate", help="DLSS Frame Generation to a target frame rate.")
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

    info = commands.add_parser("info", help="Show GPUs, encoders, frame-generation capabilities, and choices.")
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
    return {
        "ai_gpu_uuid": args.ai_gpu,
        "nr_preset": args.nr_preset,
        "nr_style": args.nr_style,
        "nr_intensity": args.nr_intensity,
        "local_tone_strength": args.local_tone,
        "local_structure_strength": args.local_structure,
        "skin_structure_strength": args.skin_structure,
        "automatic_mask": bool(args.automatic_mask),
        "dlss_model_preset": args.dlss_model_preset,
        "upscaling_factor": args.upscale,
    }


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


def _check_output_dir(value: str | None) -> None:
    """Create or validate the output directory before any GPU work starts."""
    from ..core.disk_paths import prepare_output_dir

    try:
        prepare_output_dir(value)
    except (OSError, ValueError) as exc:
        raise UsageError(f"--output-dir: {exc}") from exc


def _payload(command: str, manifest_path: str, **extra: Any) -> dict[str, Any]:
    """The batch manifest written by the processing layer, plus the command."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    return {"command": command, **manifest, "manifest_path": manifest_path, **extra}


def run_image(args: argparse.Namespace, settings: UISettings, reporter: ProgressReporter) -> dict[str, Any]:
    inputs = _resolve_inputs(args.inputs, "image")
    try:
        from ..neural_rendering.image import convert_images
    except ImportError as exc:
        raise RuntimeError(
            f"Image decoding packages are missing ({exc.name}). Install with the 'image' extra: uv sync --extra image"
        ) from exc
    from ..settings.factory import image_options

    options = image_options(
        settings,
        **_neural_overrides(args),
        output_format=args.format,
        quality=args.quality,
        rename_mode=args.rename,
        custom_suffix=args.suffix,
    )
    _check_output_dir(args.output_dir)
    reporter.register(inputs)
    result = convert_images(
        inputs, options, reporter, output_dir=args.output_dir, on_item_update=reporter.item_update,
        # Thumbnails for the browser gallery are a WebUI concern.
        generate_previews=False, create_zip=bool(args.zip),
    )
    return _payload("image", result.manifest_path, zip_path=result.zip_path)


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
        # The CLI has no browser to please: previews keep the caller's codec.
        preview_compat=False,
    )
    _check_video_like(options, neural=True)
    _check_output_dir(args.output_dir)
    reporter.register(inputs)
    result = convert_videos(inputs, options, reporter, output_dir=args.output_dir, on_item_update=reporter.item_update)
    return _payload("video", result.manifest_path)


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
    _check_output_dir(args.output_dir)
    reporter.register(inputs)
    result = interpolate_videos(inputs, options, reporter, output_dir=args.output_dir, on_item_update=reporter.item_update)
    return _payload("interpolate", result.manifest_path)


def collect_info(ai_gpu_uuid: str) -> dict[str, Any]:
    """Gather what a caller needs to choose arguments; each probe fails independently."""
    from ..core.ffmpeg import probe_nvenc_codecs
    from ..core.gpu_detection import detect_gpus
    from ..core.runtime import prepare_runtime, validate_runtime_files
    from ..frame_interpolation.capabilities import probe_frame_interpolation_capabilities

    report: dict[str, Any] = {"root": str(ROOT), "config": str(CONFIG_PATH)}
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
        report["frame_generation"] = asdict(probe_frame_interpolation_capabilities(ai_gpu_uuid))
    except Exception as exc:
        report["frame_generation"] = str(exc)
    report["choices"] = {
        "upscale": [factor for factor in UPSCALING_MODES],
        "nr_preset": list(NR_PRESETS),
        "nr_style": list(NR_STYLES),
        "dlss_model_preset": list(DLSS_MODEL_PRESETS),
        "codec": list(CODEC_CHOICES),
        "container": list(CONTAINER_CHOICES),
        "encoding_quality": list(ENCODING_QUALITIES),
        "image_format": list(IMAGE_FORMAT_CHOICES),
        "fps": list(FPS_CHOICES),
        "engine": list(ENGINE_CHOICES),
        "rename": list(RENAME_MODES),
    }
    return report


def _print_info(report: dict[str, Any]) -> None:
    out = sys.stdout
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
    stream.write(
        f"{payload['status']}: {len(payload['successes'])} ok, {len(payload['failures'])} failed"
        f" | output: {payload.get('output_directory')} | manifest: {payload['manifest_path']}{extra}\n"
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
    handlers = {"image": run_image, "video": run_video, "interpolate": run_interpolate}
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
