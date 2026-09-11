from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import TextIO

from ..core.batch_progress import TERMINAL, BatchItemUpdate

_ETA_SUFFIX = re.compile(r" - Time Remaining: [0-9.]+s$")


class ProgressReporter:
    """Adapt the processing layer's progress callbacks to stderr.

    Two callbacks feed the reporter: ``progress(value, message)`` with the
    batch-wide fraction, and ``item_update(BatchItemUpdate)`` with one
    file's state (Queued, Running, Complete, Failed, Cancelled, Skipped).

    ``text`` rewrites one line on a terminal and prints a line whenever a
    file reaches a terminal state; on a pipe it prints a line only when the
    percentage or the message (minus its ETA suffix) changes, so a long
    render does not flood a log. ``json`` prints one object per item update
    (JSON Lines) and ignores the batch-wide fraction, which the per-item
    progress already carries. ``none`` discards everything.
    """

    def __init__(self, mode: str, stream: TextIO | None = None) -> None:
        if mode not in ("text", "json", "none"):
            raise ValueError(f"Unknown progress mode: {mode!r}.")
        self.mode = mode
        self.stream = stream or sys.stderr
        try:
            self._tty = bool(self.stream.isatty())
        except Exception:
            self._tty = False
        self._last: tuple[int, str] | None = None
        self._line_length = 0
        self._names: dict[int, str] = {}
        self._total = 0

    def __call__(self, value: float, message: str) -> None:
        if self.mode != "text":
            return
        try:
            fraction = float(value)
        except (TypeError, ValueError):
            fraction = 0.0
        fraction = 0.0 if fraction < 0 else (1.0 if fraction > 1 else fraction)
        text = str(message)
        percent = int(fraction * 100)
        if self._tty:
            width = max(20, shutil.get_terminal_size((100, 20)).columns - 1)
            line = f"{percent:3d}% {text}"
            if len(line) > width:
                line = line[: width - 1] + "…"
            padded = line.ljust(self._line_length)
            self._line_length = len(line)
            self._write("\r" + padded)
            return
        key = (percent, _ETA_SUFFIX.sub("", text))
        if key == self._last:
            return
        self._last = key
        self._write(f"{percent:3d}% {key[1]}\n")

    def register(self, paths: list) -> None:
        """Remember the input names so terminal-state lines can show them."""
        self._names = {index: Path(path).name for index, path in enumerate(paths)}
        self._total = len(paths)

    def item_update(self, update: BatchItemUpdate) -> None:
        if self.mode == "none":
            return
        if self.mode == "json":
            record = {
                "index": update.index,
                "state": update.state,
                "progress": round(float(update.progress), 4),
                "detail": update.detail,
                "output_path": update.output_path,
                "elapsed_seconds": round(float(update.elapsed_seconds), 3),
            }
            if update.index is None:
                record["log_path"] = update.manifest_path
            else:
                record["input"] = self._names.get(update.index, "")
            self._write(json.dumps(record) + "\n")
            return
        if update.index is None or update.state not in TERMINAL:
            return
        self.finish()
        name = self._names.get(update.index, str(update.index))
        position = f"[{update.index + 1}/{self._total}] " if self._total else ""
        detail = update.detail.splitlines()[0] if update.detail else ""
        if update.state == "Complete":
            self._write(f"{position}{name}: Complete -> {update.output_path}\n")
        else:
            self._write(f"{position}{name}: {update.state}{': ' + detail if detail else ''}\n")

    def finish(self) -> None:
        """Terminate a rewritten terminal line so later output starts fresh."""
        if self.mode == "text" and self._tty and self._line_length:
            self._write("\n")
            self._line_length = 0

    def _write(self, text: str) -> None:
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError):
            pass
