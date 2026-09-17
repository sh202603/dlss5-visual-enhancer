from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

from ..core.jobs import BoundedLogBuffer, drain_bounded_text
from ..core.paths import MPV, YTDLP


def mpv_tail(process: subprocess.Popen | None, limit: int = 12) -> str:
    """Return the last captured MPV stderr lines (empty when unavailable)."""
    logs = getattr(process, "_dlss5_err", None)
    if logs is None:
        return ""
    try:
        return "\n".join(logs.snapshot()[-limit:])
    except Exception:
        return ""


def check_live_binaries(*, resolve_pages: bool, play: bool) -> None:
    """Raise a user-facing error if required Live externals are missing."""
    if resolve_pages and not YTDLP.is_file():
        raise RuntimeError(
            f"yt-dlp is not installed ({YTDLP} missing); Live cannot "
            "resolve YouTube/Twitch page URLs. Local files still work."
        )
    if play and not MPV.is_file():
        raise RuntimeError(
            f"MPV is not installed ({MPV} missing); "
            "restore the portable player to watch Live in-tab."
        )


def launch_mpv(
    playlist_url: str,
    title: str,
    extra_args: tuple[str, ...] = (),
    *,
    buffer_seconds: float = 6.0,
    state_path: Path | None = None,
    wid: int = 0,
    ipc_server: str = "",
) -> subprocess.Popen:
    """Play a Live playlist on the vendored MPV. Raises on missing binary.

    When ``wid`` is a valid parent-window handle the player attaches to it
    (in-tab embedding) instead of opening its own window. ``ipc_server``
    enables the JSON IPC channel used by the in-tab transport controls.
    """
    if not MPV.is_file():
        raise RuntimeError(
            f"MPV is not installed ({MPV} missing); the Live stream "
            "is still being produced — restore the player to watch it."
        )
    env = os.environ.copy()
    env["PATH"] = str(YTDLP.parent) + os.pathsep + env.get("PATH", "")
    if state_path is not None:
        env["DLSS5_LIVE_PLAYER_STATE"] = str(state_path)
    command = [
        str(MPV),
        "--no-config",
        "--ytdl=no",
        "--cache=yes",
        "--cache-pause=yes",
        "--cache-pause-initial=yes",
        f"--cache-pause-wait={buffer_seconds:g}",
        f"--cache-secs={max(20, buffer_seconds * 3):g}",
        "--demuxer-max-bytes=128MiB",
        "--demuxer-lavf-o=live_start_index=0",
        "--hwdec=auto-safe",
        "--video-sync=audio",
        f"--script={Path(__file__).with_name('player_status.lua')}",
        f"--title=DLSS 5 Live — {title}",
        "--terminal=no",
        *extra_args,
    ]
    if wid:
        # In-tab embedding: MPV creates its own child window covering the
        # given parent and letterboxes the video itself. Input goes to the
        # QML transport (pause/mute via IPC); the OSD would only fight it.
        command += [
            f"--wid={int(wid)}",
            "--force-window=yes",
            "--no-border",
            "--keepaspect=yes",
            "--input-vo-keyboard=no",
            "--no-osc",
            "--no-osd-bar",
            "--cursor-autohide=no",
        ]
    if ipc_server:
        command.append(f"--input-ipc-server={ipc_server}")
    command.append(playlist_url)
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=creation_flags,
        )
    except OSError as exc:
        raise RuntimeError(f"Could not launch MPV: {exc}.") from exc
    try:
        logs = BoundedLogBuffer(max_tail=60)
        assert process.stderr is not None
        threading.Thread(
            target=drain_bounded_text, args=(process.stderr, logs), daemon=True
        ).start()
        process._dlss5_err = logs  # type: ignore[attr-defined]
    except Exception:
        pass
    return process
