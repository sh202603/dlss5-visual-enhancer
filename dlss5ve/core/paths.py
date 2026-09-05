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
RUNTIME = ROOT / "bin" / "runtime"
HOST_DIR = RUNTIME / "host"
DLSS_DIR = RUNTIME / "dlss"
DLSSG_DIR = RUNTIME / "dlssg"
# Universal FP16 Neural Rendering runtime for all supported RTX architectures.
DLSSNR_DIR = RUNTIME / "dlssnr"
FFMPEG = ROOT / "bin" / "ffmpeg" / "bin" / "ffmpeg.exe"
FFPROBE = ROOT / "bin" / "ffmpeg" / "bin" / "ffprobe.exe"
WORKER = HOST_DIR / "nvngx.dll"  # Signed-snippet caller checks require this image name.
ADDON = DLSSNR_DIR / "renodx-dlss5.addon64"
HOST_DXGI = HOST_DIR / "dxgi.dll"
RESHADE_LOG = HOST_DIR / "ReShade.log"
DLSS_SUPERRES = DLSS_DIR / "nvngx_dlss.dll"
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
