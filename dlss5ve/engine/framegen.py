from __future__ import annotations

from fractions import Fraction

import av
import numpy as np

from ..core.gpu_selection import detect_gpu
from ..core.jobs import JobController
from ..frame_interpolation.capabilities import probe_frame_interpolation_capabilities
from ..frame_interpolation.native import DirectDLSSGSession
from .neural import ensure_rgba

SCENE_CUT_MODES = ("duplicate", "skip")

# The bridge takes and returns BT.709. Full range avoids the 16..235
# quantization of limited range; the matching decode below is "JPEG".
_BRIDGE_MATRIX = 1
_BRIDGE_FULL_RANGE = 1
_DECODE_COLORSPACE = "ITU709"
_DECODE_RANGE = "JPEG"


class FrameGenStream:
    """DLSS Frame Generation on a stream of RGBA frames.

    ``push`` takes the next source frame and returns the ``multiplier - 1``
    frames generated between the previous source frame and this one (an empty
    list for the very first frame). When the bridge detects a scene cut, or the
    caller passes ``reset=True``, the history is reset and no real interpolation
    exists for that interval; ``on_scene_cut`` decides whether the gap is filled
    with copies of the previous frame (keeps the frame count constant, which
    PTS-driven writers rely on) or left empty.

    Since v9 the runtime is a bridge DLL in this process
    (``frame_interpolation.native``) rather than a worker executable, and it
    estimates motion itself with NVIDIA Optical Flow. Two consequences for
    callers:

    - Generated frames are taken as NV12 and converted back to RGBA here. That
      round trip makes the generated frames' chroma 4:2:0; the source frames
      the caller keeps are untouched. The colour matrix and range used on the
      way in and out must agree, or the result shifts: the pair here is BT.709
      full range.
    - The frames are taken as CUDA surfaces and brought to host memory by
      swscale, because the bridge's own host download is far slower. The v11
      bridge can also return the generated frame as an RGBA surface
      (``output_rgb=True``), which would avoid the 4:2:0 chroma entirely, but
      its RGB download costs too much: measured at 1080p with one generated
      frame per push, this NV12 path takes 26.9 ms per push, the RGB download
      101.2 ms, and converting the RGB surface back to NV12 on the GPU before
      swscale 43.7 ms (same 4:2:0 result as this path). A bridge without CUDA
      interop falls back to the host download.
    - NGX state is process-lifetime and bound to the GPU that initialised it,
      so every stream in a process shares one adapter, and a watchdog timeout
      or native exception poisons the bridge until the process restarts.

    ``expected_frames`` and ``frame_rate`` are accepted for compatibility with
    the v8 signature and ignored: the v9 bridge declares no frame count and
    derives no timing from the caller.
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
        del expected_frames, frame_rate
        if on_scene_cut not in SCENE_CUT_MODES:
            raise ValueError(f"on_scene_cut must be one of {', '.join(SCENE_CUT_MODES)}.")
        multiplier = int(multiplier)
        if multiplier < 2:
            raise ValueError("multiplier must be 2 or more.")
        capabilities = probe_frame_interpolation_capabilities(gpu_uuid)
        if not capabilities.available:
            detail = capabilities.detail or "DLSS Frame Generation is unavailable on this GPU."
            if "primary-context" in detail or "primary context" in detail:
                # v9 needs FFmpeg's CUDA primary context, and creating it fails
                # once another library (torch) owns the device's context.
                detail += (
                    " Open this stream before the first CUDA call of any other library "
                    "(torch included); the bridge cannot adopt a context it did not create."
                )
            raise RuntimeError(detail)
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
        self._reformatter = av.video.reformatter.VideoReformatter()
        self._output_cuda = bool(capabilities.cuda_interop)
        self._session = DirectDLSSGSession(
            int(width), int(height), self.generated_count,
            self.controller, int(detect_gpu(gpu_uuid)["cuda_ordinal"]),
        )
        self._previous: np.ndarray | None = None
        self._index = 0
        self.scene_cuts = 0
        self.closed = False

    @property
    def frames_pushed(self) -> int:
        return self._index

    def _to_rgba(self, frame: av.VideoFrame) -> np.ndarray:
        """Bring one generated NV12 frame back to the RGBA contract.

        The same call covers a CUDA surface and a host frame; swscale downloads
        the former on its own.
        """
        converted = self._reformatter.reformat(
            frame, format="rgba", src_colorspace=_DECODE_COLORSPACE, src_color_range=_DECODE_RANGE,
        )
        return converted.to_ndarray()

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
        frames, detail = self._session.process_frame(
            rgba, force_reset=reset or first, detect_scene_cut=True,
            output_cuda=self._output_cuda,
            color_matrix=_BRIDGE_MATRIX, color_range=_BRIDGE_FULL_RANGE,
        )
        self._index += 1
        previous = self._previous
        self._previous = rgba
        if first:
            return []
        if reset or detail["scene_cut"]:
            # A forced reset reports scene_cut False, so both are counted here.
            self.scene_cuts += 1
        generated = [self._to_rgba(item) for item in frames]
        if len(generated) < self.generated_count:
            # A reset, a detected cut, or a declined interval ("disabled")
            # produces nothing real; keep the frame count constant unless the
            # caller asked for the gap to stay empty.
            if self.on_scene_cut == "skip":
                return generated
            assert previous is not None
            generated += [previous.copy() for _ in range(self.generated_count - len(generated))]
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
