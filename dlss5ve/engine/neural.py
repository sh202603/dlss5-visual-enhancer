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

# The DLSSG worker exits once the frame count declared at setup has been
# delivered (verified 2026-09-03: frame N+1 breaks the pipe). Declaring the
# 32-bit maximum keeps that session open indefinitely; closing early is a
# clean exit 0. Neural Rendering does not need this: since v8 it runs in
# process and a session simply closes when the caller is done.
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

    ``push`` returns the rendered frame at ``output_size``. ``reset=True``
    cuts the temporal history; use it at the first frame of every
    independent clip. There is no scene-cut detection here: the caller
    decides where clips start.

    ``factor`` is the Scale control of the WebUI (1, 0.75, 0.5, 0.25): the
    resolution entering Neural Rendering as a fraction of the input, and the
    size of the frames returned. Neural Rendering does not enlarge frames
    since v8.

    The feature-18 runtime lives in this process (``core.neural_bridge``):
    the first stream initialises NGX on the selected GPU and every later
    stream shares that state until the process exits. Native calls run on a
    watchdog thread; after a timeout or a native exception the bridge refuses
    further work (``NeuralBridgePoisonedError``) and the process has to be
    restarted. With ``gpu_mode`` the bridge retains the GPU's CUDA primary
    context and leaves no context current on the calling thread afterwards.

    ``gpu_mode`` follows ``settings.nr_gpu_mode`` when None. The bridge
    accepts the CUDA path only when it creates the device's primary context
    itself (it needs FFmpeg's blocking-sync flags); when another library
    (torch) created the context first, the CUDA path is refused. With
    ``gpu_mode=None`` the stream then falls back to host staging and records
    why in ``gpu_fallback_reason``; an explicit ``gpu_mode=True`` raises
    instead. Open the first stream before the first torch CUDA call to keep
    the CUDA path.

    ``expected_frames`` keeps the counted mode available: the session then
    insists on exactly that many frames before ``close``.
    """

    def __init__(
        self,
        width: int,
        height: int,
        *,
        factor: float = 1.0,
        settings: UISettings | None = None,
        gpu_uuid: str = "auto",
        gpu_mode: bool | None = None,
        controller: JobController | None = None,
        expected_frames: int | None = None,
    ) -> None:
        from dataclasses import replace

        settings = settings or DEFAULT_SETTINGS
        prepared = prepare_runtime()
        gpu = resolve_runtime_ai_gpu(prepared.gpus, prepared.runtime_bundle, gpu_uuid)
        self.gpu_fallback_reason: str | None = None
        if gpu_mode is None and settings.nr_gpu_mode:
            from ..core.neural_bridge import BRIDGE_MANAGER

            status = BRIDGE_MANAGER.initialize(gpu, require_cuda=False)
            if not status.get("cuda_supported"):
                self.gpu_fallback_reason = str(status.get("cuda_status") or "CUDA interop unavailable")
                gpu_mode = False
        if gpu_mode is not None:
            settings = replace(settings, nr_gpu_mode=bool(gpu_mode))
        self.factor, mode = resolve_upscaling_mode(factor)
        native = resolve_native_settings(settings)
        output_width, output_height = resolve_output_size(int(width), int(height), self.factor)
        self.input_size = (int(width), int(height))
        self.output_size = (output_width, output_height)
        self.gpu_name = str(gpu.get("display_name") or gpu.get("name") or "NVIDIA RTX GPU")
        self.gpu_mode = bool(native.get("gpu_mode", True))
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
            composition_mask=settings.nr_mask,
            gpu=gpu,
            runtime_bundle=prepared.runtime_bundle,
            controller=self.controller,
        )
        self.render_size = (self._session.render_width, self._session.render_height)
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
        # The first frame of a stream always resets: the bridge has no history for it.
        output, _pts = self._session.process(
            index=self._index,
            rgba=render,
            reset=reset or self._index == 0,
            pts=self._index,
        )
        self._index += 1
        return output

    def evidence(self) -> dict[str, Any]:
        """Structured evidence that feature 18 evaluated the pushed frames."""
        return verify_feature_18(self._session.bridge_logs, self._session.structured_status())

    def status(self) -> dict[str, Any]:
        """The bridge session's diagnostics (memory path, transfers, temporal state)."""
        return self._session.structured_status()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self._index == 0:
            # Streaming close reports "no decodable frames" for an empty
            # session; there is nothing to complete, so just release it.
            self._session.abort()
            return
        self._session.close()

    def __enter__(self) -> "NeuralRenderStream":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
