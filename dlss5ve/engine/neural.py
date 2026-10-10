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

_ORDERING_HINT = (
    " Call initialize_neural_rendering() or open the first NeuralRenderStream before the first "
    "CUDA call of any other library (torch included): the bridge accepts the CUDA path only for "
    "a primary context it created itself, and since Visual Enhancer v15 there is no host-memory "
    "fallback."
)


def initialize_neural_rendering(gpu_uuid: str = "auto") -> dict[str, Any]:
    """Bind the Neural Rendering bridge to the GPU in this process and return its status.

    The bridge takes the CUDA path only for a primary context it created itself,
    and v15 has no other path, so this has to run before any torch CUDA call in
    the process. Opening a ``NeuralRenderStream`` does the same; this function
    exists for callers that open their streams later (lada-ex constructs its
    restorer before loading models but opens the stream on the first clip).
    Repeated calls are cheap: NGX state is process-lifetime.
    """
    prepared = prepare_runtime()
    gpu = resolve_runtime_ai_gpu(prepared.gpus, prepared.runtime_bundle, gpu_uuid)
    from ..core.neural_bridge import BRIDGE_MANAGER, NeuralBridgeError

    try:
        return BRIDGE_MANAGER.initialize(gpu)
    except NeuralBridgeError as exc:
        message = str(exc).rstrip()
        if "interoperab" in message or "primary context" in message or "CUDA" in message:
            message += ("" if message.endswith(".") else ".") + _ORDERING_HINT
        raise type(exc)(message) from exc


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

    ``factor`` is the Scale control (0.25 to 2 in the steps of
    ``UPSCALING_MODES``): frames are fitted to the input size times ``factor``
    with Lanczos before Neural Rendering, and the rendered frame keeps that
    size. Feature 18 itself never resizes. The 7680x4320 boundary of
    ``resolve_output_size`` applies to the scaled size.

    ``settings`` carries the Neural Rendering controls of ``UISettings``
    (``nr_style``, ``nr_intensity``, ``nr_passes``, the three strengths,
    ``automatic_mask``, ``nr_optical_flow_quality``, and the ``nr_mask``
    control mask). ``still_image=True`` selects the bridge's static motion
    mode, as the app does for still images; the default is the video mode
    with NVIDIA Optical Flow between consecutive frames.

    The feature-18 runtime lives in this process (``core.neural_bridge``):
    the first stream initialises NGX on the selected GPU and every later
    stream shares that state until the process exits. Native calls run on a
    watchdog thread; after a timeout or a native exception the bridge refuses
    further work (``NeuralBridgePoisonedError``) and the process has to be
    restarted.

    Since Visual Enhancer v15 Neural Rendering runs only on the CUDA/D3D12
    path: the bridge retains the GPU's CUDA primary context, leaves no context
    current on the calling thread afterwards, and refuses to initialise when
    another library (torch) created that context first. The v11 host-staging
    fallback is gone, so ``gpu_mode`` is kept only for compatibility:
    ``None`` and ``True`` take the CUDA path and ``False`` raises
    ``ValueError``. ``gpu_fallback_reason`` is always ``None``. Open the first
    stream before the first torch CUDA call.

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
        still_image: bool = False,
    ) -> None:
        if gpu_mode is False:
            raise ValueError(
                "gpu_mode=False is not available: since Visual Enhancer v15 Neural Rendering "
                "runs only on the CUDA/D3D12 path and has no host-memory fallback."
            )
        settings = settings or DEFAULT_SETTINGS
        prepared = prepare_runtime()
        gpu = resolve_runtime_ai_gpu(prepared.gpus, prepared.runtime_bundle, gpu_uuid)
        # Kept for callers written against v11, where a refused CUDA path fell
        # back to host staging and this recorded why. v15 has no such path.
        self.gpu_fallback_reason: str | None = None
        # The session would initialise the bridge itself; doing it here first
        # lets the ordering hint reach the caller on failure.
        initialize_neural_rendering(gpu_uuid)
        self.factor, mode = resolve_upscaling_mode(factor)
        native = resolve_native_settings(settings)
        output_width, output_height = resolve_output_size(int(width), int(height), self.factor)
        self.input_size = (int(width), int(height))
        self.output_size = (output_width, output_height)
        self.gpu_name = str(gpu.get("display_name") or gpu.get("name") or "NVIDIA RTX GPU")
        self.gpu_mode = True
        self.still_image = bool(still_image)
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
            still_image=self.still_image,
            control_mask=settings.nr_mask,
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
