from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

from ...core.ffmpeg.preview import is_browser_playable, make_browser_preview
from .processor import upscale_video


def display_result_native(result, options, *, preview_encoding: str = "Auto", controller=None, output_dir=None):
    """Return a plain media path/detail tuple with no UI-framework objects."""
    mode = preview_encoding
    if mode == "Disabled":
        return result.output_path, "Actual output; HDR/codec support depends on the native media backend."
    if not options.hdr_enabled and mode == "Auto" and is_browser_playable(result.output_path):
        return result.output_path, ""
    vf = None
    if options.hdr_enabled:
        peak = options.hdr_peak_luminance / 100
        vf = (
            "zscale=matrixin=bt2020nc:primariesin=bt2020:transferin=smpte2084:rangein=limited:"
            "transfer=linear:npl=100,format=gbrpf32le,zscale=primaries=bt709,"
            f"tonemap=mobius:desat=2:peak={peak:g},zscale=transfer=bt709:matrix=bt709:range=limited,format=yuv420p"
        )
    try:
        path = make_browser_preview(
            result.output_path, dest_dir=output_dir, controller=controller, sdr_filter=vf
        )
    except Exception as exc:
        return None, f"Output saved; compatibility preview unavailable: {exc}"
    return path, (
        "SDR tone-mapped compatibility preview. Open the original for HDR playback."
        if options.hdr_enabled else "H.264 compatibility preview."
    )


def preview_upscale_native(
    path: str,
    options,
    *,
    one_frame: bool = False,
    progress=None,
    controller=None,
    output_dir=None,
    preview_encoding: str = "Auto",
    start_seconds: float | None = None,
    frame_index: int | None = None,
    preview_seconds: float | None = None,
):
    if not path or not Path(path).is_file():
        raise ValueError("Select one valid video to preview.")
    try:
        start = max(0.0, float(start_seconds or 0.0))
    except (TypeError, ValueError):
        start = 0.0
    try:
        frame_no = max(1, int(frame_index or 1)) if frame_index else 1
    except (TypeError, ValueError):
        frame_no = 1
    length_seconds = 3.0 if preview_seconds is None else float(preview_seconds)
    if not math.isfinite(length_seconds) or length_seconds <= 0:
        raise ValueError("Preview duration must be positive and finite.")
    effective_path = str(path)
    temp_clip: str | None = None
    # Both preview modes start at the parked timeline frame. Extract only
    # when seeking: processing the original directly avoids an extra encode
    # at the beginning of the source.
    if start > 0.05:
        from ...core.ffmpeg.preview import extract_preview_subclip
        if progress:
            try:
                progress(0.02, "Seeking to timeline frame…" if one_frame else "Seeking to preview clip…")
            except TypeError:
                pass
        temp_clip = extract_preview_subclip(
            path, dest_dir=output_dir, start_seconds=start,
            length_seconds=None if one_frame else length_seconds,
            single_frame=one_frame, controller=controller,
        )
        effective_path = temp_clip
    opts = replace(
        options,
        preview_frames=1 if one_frame else None,
        preview_seconds=None if one_frame else length_seconds,
    )
    try:
        result = upscale_video(
            effective_path, opts, progress=progress, controller=controller, output_dir=output_dir
        )
    finally:
        if temp_clip:
            try:
                Path(temp_clip).unlink(missing_ok=True)
            except OSError:
                pass
    display, detail = display_result_native(
        result,
        opts,
        preview_encoding=preview_encoding,
        controller=controller,
        output_dir=output_dir,
    )
    stamp = (f" f{frame_no} @ {start:.2f}s" if one_frame and start > 0.05 else
             f" {length_seconds:g}s @ {start:.2f}s" if not one_frame else "")
    return display, (
        f"Preview complete{stamp}: {result.output_width}×{result.output_height}, {result.frames} frames.\n"
        f"{detail}\nOriginal preview file: {result.output_path}\nReport: {result.report_path}"
    )
