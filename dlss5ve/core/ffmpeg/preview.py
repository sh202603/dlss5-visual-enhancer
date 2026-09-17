from __future__ import annotations

import subprocess
from pathlib import Path

from .. import app_log
from ..paths import FFMPEG
from .codecs import _base_codec

PREVIEW_ENCODING_CHOICES = ("Auto", "Always H.264", "Disabled")
DEFAULT_PREVIEW_ENCODING = "Auto"


def normalize_preview_encoding(value: object) -> str:
    """Return a valid preview-encoding mode, defaulting to Auto."""
    if isinstance(value, str) and value.strip() in PREVIEW_ENCODING_CHOICES:
        return value.strip()
    return DEFAULT_PREVIEW_ENCODING


def is_user_playable_request(codec: str, container: str) -> bool:
    """Pre-check whether the requested encode settings are browser-playable.

    Strict definition: MP4 container + H.264 base codec (plain or NVENC).
    Used to pick the encode path without paying for a probe first.
    """
    try:
        if container != "MP4":
            return False
        return _base_codec(codec) == "H.264"
    except Exception:
        return False


def resolve_preview_codec(
    requested_codec: str, requested_container: str, mode: object
) -> tuple[str, str]:
    """Return the (codec, container) to encode a truncated preview with."""
    normalized = normalize_preview_encoding(mode)
    if normalized == "Disabled":
        return requested_codec, requested_container
    if normalized == "Always H.264":
        return "H.264", "MP4"
    # Auto: reuse the user's settings when they are already browser-playable,
    # otherwise fall back to the compatible H.264/MP4 preview.
    if is_user_playable_request(requested_codec, requested_container):
        return requested_codec, requested_container
    return "H.264", "MP4"


def wants_compat_preview(
    requested_codec: str, requested_container: str, mode: object
) -> bool:
    """True when a truncated preview must use the forced H.264 SDR path."""
    normalized = normalize_preview_encoding(mode)
    if normalized == "Disabled":
        return False
    if normalized == "Always H.264":
        return True
    return not is_user_playable_request(requested_codec, requested_container)


def is_browser_playable(path: str | Path) -> bool:
    """Probe the actual output file: playable iff MP4 + H.264 video stream."""
    from .probe import probe_video

    candidate = Path(path)
    if candidate.suffix.lower() != ".mp4":
        return False
    try:
        metadata = probe_video(candidate, count_mode="metadata")
    except Exception:
        return False
    codec = str(metadata.get("codec") or "").lower()
    if codec not in ("h264", "avc"):
        return False
    container_format = str(metadata.get("format") or "").lower()
    # ffprobe reports e.g. "mov,mp4,m4a,3gp,3g2,mj2" for MP4 files.
    if "mp4" not in container_format:
        return False
    return True


def make_browser_preview(
    source: str | Path,
    dest_dir: str | Path | None = None,
    controller=None,
    *, sdr_filter: str | None = None,
    max_seconds: float | None = None,
    max_width: int | None = None,
) -> str:
    """Transcode an existing result file to a browser-playable H.264 MP4.

    Returns the new preview path as a string. Raises RuntimeError on failure.
    """
    from ..paths import OUTPUTS
    from ..jobs import current_job_controller
    from ..disk_paths import OutputFile

    controller = controller or current_job_controller()

    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(src)
    out_dir = Path(dest_dir) if dest_dir is not None else OUTPUTS
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{src.stem}_BROWSERPREVIEW.mp4"
    counter = 1
    while dest.exists():
        counter += 1
        dest = out_dir / f"{src.stem}_BROWSERPREVIEW_{counter}.mp4"
    output_file = OutputFile(dest)
    filters: list[str] = []
    if sdr_filter:
        filters.append(sdr_filter)
    if max_width is not None and max_width > 0:
        filters.append(f"scale=if(gt(iw\\,{int(max_width)})\\,{int(max_width)}\\,iw):-2")
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-i",
        str(src),
        *(["-t", f"{float(max_seconds):.6f}"] if max_seconds is not None and max_seconds > 0 else []),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        *(["-vf", ",".join(filters)] if filters else []),
        *(["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"] if sdr_filter else []),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_file.temporary),
    ]
    process = None
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if controller is not None:
            controller.register(process)
        _stdout, stderr = process.communicate()
        if process.returncode:
            app_log.error("ffmpeg-preview", "browser preview transcode failed", (stderr or "")[-500:])
            raise RuntimeError("Browser preview transcode failed:\n" + (stderr or "")[-4000:])
        if not is_browser_playable(output_file.temporary):
            raise RuntimeError("Browser preview transcode produced an unplayable file.")
        if controller is not None and controller.cancel.is_set():
            from ..jobs import Cancelled
            raise Cancelled("Preview cancelled.")
        output_file.publish()
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                process.communicate()
            if controller is not None:
                controller.unregister(process)
        output_file.cleanup()
    return str(dest)


def extract_preview_subclip(
    source: str | Path,
    dest_dir: str | Path | None = None,
    *,
    start_seconds: float = 0.0,
    length_seconds: float | None = None,
    single_frame: bool = False,
    controller=None,
) -> str:
    """Extract a frame-quantized subclip starting at ``start_seconds``.

    Callers pass the *nominal frame start* ``(N-1)/fps`` matching the timeline
    counter ``floor(position*fps)+1``. A raw playhead anywhere inside frame N
    would otherwise select N+1, because ``-ss`` emits the first frame with
    ``pts >= START``. A 2 ms epsilon absorbs ``%.6f`` rounding on
    non-terminating rates (23.976/29.97) so the seek lands on N, not N+1.
    Accurate output seeking (``-i`` then ``-ss``) is used with a 2 s fast
    pre-seek so long 4K files stay fast while remaining frame-exact.
    Returns the temp clip path as string. Caller owns cleanup.
    """
    from ..disk_paths import OutputFile
    from ..jobs import current_job_controller

    controller = controller or current_job_controller()
    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(src)
    try:
        start = max(0.0, float(start_seconds or 0.0))
    except (TypeError, ValueError):
        start = 0.0
    if start <= 0.05 and not single_frame and not length_seconds:
        return str(src)
    # Epsilon: land just inside the intended frame's leading edge.
    aligned = max(0.0, start - 0.002)
    fast = max(0.0, aligned - 2.0)
    accurate = max(0.0, aligned - fast)
    from ..paths import OUTPUTS
    out_dir = Path(dest_dir) if dest_dir is not None else OUTPUTS
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_PLAYHEADFRAME.mp4" if single_frame else "_PLAYHEAD.mp4"
    dest = out_dir / f"{src.stem}{suffix}"
    counter = 1
    while dest.exists():
        counter += 1
        dest = out_dir / f"{src.stem}{suffix.replace('.mp4', f'_{counter}.mp4')}"
    output_file = OutputFile(dest)
    command = [
        str(FFMPEG), "-hide_banner", "-loglevel", "warning", "-y",
        "-ss", f"{fast:.6f}", "-i", str(src),
        "-ss", f"{accurate:.6f}",
    ]
    if single_frame:
        command += ["-frames:v", "1"]
    elif length_seconds is not None and float(length_seconds) > 0:
        command += ["-t", f"{float(length_seconds):.6f}"]
    command += [
        "-map", "0:v:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_file.temporary),
    ]
    process = None
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if controller is not None:
            controller.register(process)
        _stdout, stderr = process.communicate()
        if process.returncode:
            app_log.error("ffmpeg-preview", "playhead subclip failed", (stderr or "")[-500:])
            raise RuntimeError("Playhead subclip failed:\n" + (stderr or "")[-2000:])
        if not Path(output_file.temporary).is_file():
            raise RuntimeError("Playhead subclip produced no file.")
        if controller is not None and controller.cancel.is_set():
            from ..jobs import Cancelled
            raise Cancelled("Preview cancelled.")
        output_file.publish()
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                process.communicate()
            if controller is not None:
                controller.unregister(process)
        output_file.cleanup()
    return str(dest)


def grab_video_poster_jpeg(
    source: str | Path,
    *,
    seconds: float = 0.0,
    max_width: int = 960,
    controller=None,
) -> bytes:
    """Extract one JPEG still at ``seconds`` for the QML poster fallback."""
    import subprocess as _sp

    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(src)
    try:
        start = max(0.0, float(seconds or 0.0))
    except (TypeError, ValueError):
        start = 0.0
    aligned = max(0.0, start - 0.002)
    fast = max(0.0, aligned - 2.0)
    accurate = max(0.0, aligned - fast)
    command = [
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{fast:.6f}", "-i", str(src),
        "-ss", f"{accurate:.6f}", "-frames:v", "1",
        *([ "-vf", f"scale={int(max_width)}:-2"] if max_width and max_width > 0 else []),
        "-q:v", "3", "-f", "mjpeg", "pipe:1",
    ]
    process = _sp.Popen(
        command, stdout=_sp.PIPE, stderr=_sp.PIPE,
        creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
    )
    try:
        out, err = process.communicate(timeout=30)
    except _sp.TimeoutExpired:
        process.kill()
        out, err = process.communicate()
        raise RuntimeError("Poster extraction timed out.")
    if process.returncode or not out:
        detail = (err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err or ""))[-500:]
        raise RuntimeError(f"Poster extraction failed: {detail}")
    return bytes(out)


def resolve_final_preview(
    result_path: str | Path | None,
    mode: object,
    controller=None,
    *, bounded_proxy: bool = False,
) -> tuple[str | None, bool]:
    """Decide which file the final-render in-app player should show.

    Returns (display_path, used_derivative). Applies the agreed policy:
    - Always H.264: current behavior (MP4 result only, else no preview).
    - Disabled: always show the actual file (even MKV/MOV).
    - Auto: probe the result; show directly when playable, else transcode
      one H.264 derivative and show that.
    """
    if not result_path:
        return None, False
    normalized = normalize_preview_encoding(mode)
    candidate = str(result_path)
    if normalized == "Disabled":
        return candidate, False
    if normalized == "Always H.264":
        if Path(candidate).suffix.lower() == ".mp4":
            return candidate, False
        return None, False
    # Auto
    try:
        if is_browser_playable(candidate):
            return candidate, False
    except Exception:
        pass
    try:
        derived = make_browser_preview(
            candidate, controller=controller,
            max_seconds=12.0 if bounded_proxy else None,
            max_width=1280 if bounded_proxy else None,
        )
    except Exception:
        # Never break the render status path: fall back to no in-app preview
        # (the real file is still in the download list).
        return None, False
    return derived, True
