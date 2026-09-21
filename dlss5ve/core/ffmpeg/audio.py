from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .. import app_log
from ..jobs import Cancelled, JobController
from ..paths import FFMPEG, FFPROBE
from .probe import _run_json


@dataclass(frozen=True, slots=True)
class AudioStreamPlan:
    source_index: int
    source_codec: str
    mode: str


@dataclass(frozen=True, slots=True)
class AudioPlan:
    streams: tuple[AudioStreamPlan, ...]

    def encoder_args(self) -> list[str]:
        args: list[str] = []
        for output_index, stream in enumerate(self.streams):
            args.extend([f"-c:a:{output_index}", "copy" if stream.mode == "copy" else "aac"])
            if stream.mode != "copy":
                args.extend([f"-b:a:{output_index}", "192k"])
        return args

    def diagnostics(self) -> list[dict[str, str | int]]:
        return [
            {"source_index": stream.source_index, "source_codec": stream.source_codec,
             "mode": stream.mode, "output_codec": stream.source_codec if stream.mode == "copy" else "aac"}
            for stream in self.streams
        ]


_FORMATS = {"MP4": ("mp4", ".mp4"), "MOV": ("mov", ".mov"),
            "MKV": ("matroska", ".mkv")}


def _copy_works(source: Path, stream_index: int, mux_format: str, suffix: str,
                directory: Path, controller: JobController | None) -> bool:
    output = directory / f"audio-{stream_index}{suffix}"
    command = [
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-map", f"0:{stream_index}", "-frames:a", "1", "-c:a", "copy",
        "-map_metadata", "-1", "-map_chapters", "-1", "-f", mux_format, str(output),
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if controller is not None:
        controller.register(process)
    try:
        while True:
            if controller is not None and controller.cancel.is_set():
                raise Cancelled("Render stopped by user.")
            try:
                process.wait(timeout=0.2)
                return process.returncode == 0
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if controller is not None:
            controller.unregister(process)


def plan_audio_streams(source: Path, container: str,
                       controller: JobController | None = None) -> AudioPlan:
    """Choose stream copy per audio stream before video encoding starts."""
    if container not in _FORMATS:
        raise ValueError(f"Unknown output container: {container!r}.")
    data = _run_json([
        str(FFPROBE), "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index,codec_name", "-of", "json", str(source),
    ], controller=controller)
    mux_format, suffix = _FORMATS[container]
    streams: list[AudioStreamPlan] = []
    with tempfile.TemporaryDirectory(prefix="visual-enhancer-audio-") as temp:
        for stream in data.get("streams") or []:
            index = int(stream["index"])
            codec = str(stream.get("codec_name") or "unknown")
            mode = "copy" if _copy_works(
                source, index, mux_format, suffix, Path(temp), controller
            ) else "aac"
            streams.append(AudioStreamPlan(index, codec, mode))
            app_log.info("audio", f"stream={index} codec={codec} output={mode} container={container}")
    return AudioPlan(tuple(streams))
