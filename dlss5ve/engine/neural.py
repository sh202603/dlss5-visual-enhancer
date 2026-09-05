from __future__ import annotations

from typing import Any

import numpy as np

from ..core.gpu_selection import resolve_runtime_ai_gpu
from ..core.jobs import JobController
from ..core.runtime import (
    DLSSFrameSession, prepare_runtime, resize_fit, resolve_native_settings, resolve_output_size,
    resolve_upscaling_mode, verify_feature_18,
)
from ..settings.models import DEFAULT_SETTINGS, UISettings
from ..neural_rendering.video.guides import TemporalGuideGenerator

# The DLSSG worker exits once the frame count declared at setup has been
# delivered (verified 2026-09-03: frame N+1 breaks the pipe). Declaring the
# 32-bit maximum keeps that session open indefinitely; closing early is a
# clean exit 0. The DLSSNR worker no longer needs this: since v6 it accepts an
# unknown length (frame_count=None) and a counted END message on close.
UNBOUNDED_FRAMES = 2**32 - 1


def ensure_rgba(frame: np.ndarray) -> np.ndarray:
    """Accept HxWx3 or HxWx4 uint8 and return a contiguous HxWx4 array."""
    array = np.asarray(frame)
    if array.dtype != np.uint8:
        raise ValueError(f"Frames must be uint8, got {array.dtype}.")
    if array.ndim != 3 or array.shape[2] not in (3, 4):
        raise ValueError(f"Frames must be HxWx3 or HxWx4, got shape {array.shape}.")
    if array.shape[2] == 3:
        rgba = np.empty((*array.shape[:2], 4), dtype=np.uint8)
        rgba[..., :3] = array
        rgba[..., 3] = 255
        return rgba
    return np.ascontiguousarray(array)


class NeuralRenderStream:
    """DLSS Neural Rendering on a stream of RGBA frames.

    ``push`` returns the rendered frame at ``output_size``. Motion vectors are
    estimated from the previous frame on the CPU (DIS optical flow), so the
    caller only supplies colour. ``reset=True`` cuts the temporal history; use
    it at the first frame of every independent clip.

    The worker is opened in streaming mode (no frame count declared) and told
    the delivered count on ``close``. ``expected_frames`` keeps the older
    counted mode available: the worker then stops by itself after that many
    frames.
    """

    def __init__(
        self,
        width: int,
        height: int,
        *,
        factor: float = 1.0,
        settings: UISettings | None = None,
        gpu_uuid: str = "auto",
        controller: JobController | None = None,
        expected_frames: int | None = None,
    ) -> None:
        settings = settings or DEFAULT_SETTINGS
        prepared = prepare_runtime()
        gpu = resolve_runtime_ai_gpu(prepared.gpus, prepared.runtime_bundle, gpu_uuid)
        self.factor, mode = resolve_upscaling_mode(factor)
        native = resolve_native_settings(settings)
        output_width, output_height = resolve_output_size(int(width), int(height), self.factor)
        self.input_size = (int(width), int(height))
        self.output_size = (output_width, output_height)
        self.gpu_name = str(gpu.get("display_name") or gpu.get("name") or "NVIDIA RTX GPU")
        self.controller = controller or JobController()
        self._session = DLSSFrameSession(
            input_width=int(width),
            input_height=int(height),
            output_width=output_width,
            output_height=output_height,
            frame_count=int(expected_frames) if expected_frames else None,
            warmup_frames=0,
            factor=self.factor,
            mode=mode,
            native_settings=native,
            gpu=gpu,
            runtime_bundle=prepared.runtime_bundle,
            controller=self.controller,
        )
        self.render_size = (self._session.render_width, self._session.render_height)
        self._guides = TemporalGuideGenerator(*self.render_size)
        self._index = 0
        self.closed = False

    @property
    def frames_pushed(self) -> int:
        return self._index

    def push(self, frame: np.ndarray, *, reset: bool = False) -> np.ndarray:
        if self.closed:
            raise RuntimeError("NeuralRenderStream is closed.")
        rgba = ensure_rgba(frame)
        if rgba.shape[:2] != (self.input_size[1], self.input_size[0]):
            raise ValueError(
                f"Frame is {rgba.shape[1]}x{rgba.shape[0]}; this stream was opened for "
                f"{self.input_size[0]}x{self.input_size[1]}."
            )
        render = resize_fit(rgba, *self.render_size)
        if reset:
            self._guides.previous_gray = None
        guide = self._guides.process(render)
        output, _pts = self._session.process(
            index=self._index,
            rgba=render,
            motion=guide.motion,
            reset=reset or guide.reset,
            pts=self._index,
        )
        self._index += 1
        return output

    def evidence(self) -> dict[str, Any]:
        """Confirm from the ReShade log that the signed feature-18 path ran."""
        return verify_feature_18(self._session.worker_logs, self._session.reshade_log_text())

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self._index == 0:
            # Streaming close reports "no decodable frames" for an empty
            # session; there is nothing to complete, so just stop the worker.
            self._session.abort()
            return
        self._session.close()

    def __enter__(self) -> "NeuralRenderStream":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
