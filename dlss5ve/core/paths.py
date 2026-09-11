from __future__ import annotations

import os
from pathlib import Path


def _resolve_root() -> Path:
    """Locate the checkout that carries bin/runtime and bin/ffmpeg.

    The package normally lives inside that checkout (editable install or the
    embedded interpreter), so the default is two levels above this file. When
    the package is installed elsewhere, DLSS5VE_HOME must point at the checkout.
    """
    override = os.environ.get("DLSS5VE_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


ROOT = _resolve_root()
TEMP = ROOT / "temp"
GRADIO_TEMP = TEMP / "gradio"
RUNTIME = ROOT / "bin" / "runtime"
DLSSG_DIR = RUNTIME / "dlssg"
# In-process D3D12/NGX feature-18 runtime. The bridge and caller shim are
# self-contained and require no Python tensor framework or external add-on.
DLSSNR_DIR = RUNTIME / "dlssnr"
DLSSNR_BRIDGE = DLSSNR_DIR / "neuroframe_engine.dll"
DLSSNR_CALLER_SHIM = DLSSNR_DIR / "neuroframe_caller.dll"
FFMPEG = ROOT / "bin" / "ffmpeg" / "bin" / "ffmpeg.exe"
FFPROBE = ROOT / "bin" / "ffmpeg" / "bin" / "ffprobe.exe"
NEURAL_RUNTIME = DLSSNR_DIR / "nvngx_dlssnr.dll"
# Live-tab externals (vendored, optional: only Live sessions require them).
MPV = ROOT / "bin" / "mpv" / "mpv.exe"
YTDLP = ROOT / "bin" / "yt-dlp" / "yt-dlp.exe"
# Ephemeral per-session HLS working dirs for Live (swept on stop/startup).
LIVE_DIR = ROOT / "live"
OUTPUTS = ROOT / "outputs"
LOGS = ROOT / "logs"
JOBS = ROOT / "jobs"
CONFIG_DIR = ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "config.ini"
