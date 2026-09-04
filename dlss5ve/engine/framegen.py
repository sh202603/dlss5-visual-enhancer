from __future__ import annotations

from fractions import Fraction

import numpy as np

from ..core.jobs import JobController
from ..frame_interpolation.capabilities import probe_frame_interpolation_capabilities
from ..frame_interpolation.guides import DLSSGGuideGenerator
from ..frame_interpolation.native import DirectDLSSGSession
from .neural import UNBOUNDED_FRAMES, ensure_rgba

SCENE_CUT_MODES = ("duplicate", "skip")


class FrameGenStream:
    """DLSS Frame Generation on a stream of RGBA frames.

    ``push`` takes the next source frame and returns the ``multiplier - 1``
    frames generated between the previous source frame and this one (an empty
    list for the very first frame). When the guide estimator detects a scene
    cut, or the caller passes ``reset=True``, the worker's history is reset and
    no real interpolation exists for that interval; ``on_scene_cut`` decides
    whether the gap is filled with copies of the previous frame (keeps the
    frame count constant, which PTS-driven writers rely on) or left empty.
    """

    def __init__(
        self,
        width: int,
        height: int,
        *,
        multiplier: int,
        gpu_uuid: str = "auto",
        controller: JobController | None = None,
        expected_frames: int | None = None,
        on_scene_cut: str = "duplicate",
        frame_rate: Fraction | int = 30,
    ) -> None:
        if on_scene_cut not in SCENE_CUT_MODES:
            raise ValueError(f"on_scene_cut must be one of {', '.join(SCENE_CUT_MODES)}.")
        multiplier = int(multiplier)
        if multiplier < 2:
            raise ValueError("multiplier must be 2 or more.")
        capabilities = probe_frame_interpolation_capabilities(gpu_uuid)
        if not capabilities.available:
            raise RuntimeError(capabilities.detail or "DLSS Frame Generation is unavailable on this GPU.")
        if multiplier - 1 > capabilities.native_generated_frame_max:
            raise ValueError(
                f"multiplier {multiplier}x exceeds the native maximum of "
                f"{capabilities.native_multiplier}x on {capabilities.gpu}."
            )
        self.size = (int(width), int(height))
        self.multiplier = multiplier
        self.generated_count = multiplier - 1
        self.on_scene_cut = on_scene_cut
        self.capabilities = capabilities
        self.controller = controller or JobController()
        self._frame_rate = Fraction(frame_rate)
        self._session = DirectDLSSGSession(
            int(width), int(height),
            int(expected_frames) if expected_frames else UNBOUNDED_FRAMES,
            self.generated_count, self.controller,
        )
        self._guides = DLSSGGuideGenerator(int(width), int(height))
        self._previous: np.ndarray | None = None
        self._index = 0
        self.scene_cuts = 0
        self.closed = False

    @property
    def frames_pushed(self) -> int:
        return self._index

    def push(self, frame: np.ndarray, *, reset: bool = False) -> list[np.ndarray]:
        if self.closed:
            raise RuntimeError("FrameGenStream is closed.")
        rgba = ensure_rgba(frame)
        if rgba.shape[:2] != (self.size[1], self.size[0]):
            raise ValueError(
                f"Frame is {rgba.shape[1]}x{rgba.shape[0]}; this stream was opened for "
                f"{self.size[0]}x{self.size[1]}."
            )
        first = self._previous is None
        guide = self._guides.process(rgba, force_reset=reset or first)
        cut = not first and (reset or guide.reset)
        timestamp = Fraction(self._index, 1) / self._frame_rate
        generated = self._session.process_frame(
            rgba, guide.motion, timestamp, reset=first or cut,
        )
        self._index += 1
        previous = self._previous
        self._previous = rgba
        if first:
            return []
        if cut:
            self.scene_cuts += 1
            if self.on_scene_cut == "skip":
                return []
            assert previous is not None
            return [previous.copy() for _ in range(self.generated_count)]
        if len(generated) < self.generated_count:
            # The runtime declined this interval (it reports "disabled"); treat
            # it like a cut so the caller still receives a full set.
            if self.on_scene_cut == "skip":
                return generated
            assert previous is not None
            generated = list(generated) + [previous.copy() for _ in range(self.generated_count - len(generated))]
        return generated

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._session.close()

    def __enter__(self) -> "FrameGenStream":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
