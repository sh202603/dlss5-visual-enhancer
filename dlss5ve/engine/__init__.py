"""Frame-level engine API for embedding DLSS 5 in other pipelines.

The processing packages work on files. These classes work on numpy frames so
that another program (lada-ex, a custom pipeline) can stream frames through
the native runtimes without touching files, the desktop UI, or torch:

- ``NeuralRenderStream``: DLSS Neural Rendering (feature 18), one RGBA frame
  in, one RGBA frame out at the chosen Scale (0.25 to 2).
- ``FrameGenStream``: DLSS Frame Generation, one RGBA frame in, the generated
  frames between it and the previous frame out.

Since v9 each feature loads its own bridge DLL into this process (Neural
Rendering through ``core.neural_bridge``, Frame Generation through
``frame_interpolation.native``, RTX Video through ``upscale.video.native``) and
keeps its NGX state for the lifetime of the process. The GPU is fixed by the
first initialisation, and a watchdog timeout or a native exception poisons that
bridge until the process restarts. Frame Generation returns NV12 surfaces, so
``FrameGenStream`` converts them back to RGBA and the generated frames carry
4:2:0 chroma. Neither stream takes the process-wide render slot
(``core.jobs.active_job``): the caller owns the lifecycle and may pass its
own ``JobController``.
"""

from .framegen import FrameGenStream
from .neural import NeuralRenderStream

__all__ = ["FrameGenStream", "NeuralRenderStream"]
