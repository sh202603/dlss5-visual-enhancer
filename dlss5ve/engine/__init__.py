"""Frame-level engine API for embedding DLSS 5 in other pipelines.

The processing packages work on files. These classes work on numpy frames so
that another program (lada-ex, a custom pipeline) can stream frames through
the native workers without touching files, Gradio, or torch:

- ``NeuralRenderStream``: DLSS Neural Rendering (feature 18), one RGBA frame
  in, one RGBA frame out at the chosen Scale (1, 0.75, 0.5, 0.25).
- ``FrameGenStream``: DLSS Frame Generation, one RGBA frame in, the generated
  frames between it and the previous frame out.

Neural Rendering runs in this process through ``core.neural_bridge``; its NGX
state is initialised by the first stream and kept until the process exits.
Frame Generation keeps one worker process alive for the life of the stream;
the worker stops after the frame count declared at setup, so the stream
declares an effectively unbounded count and closes early; see
``UNBOUNDED_FRAMES``. Neither takes the process-wide render slot
(``core.jobs.active_job``): the caller owns the lifecycle and may pass its
own ``JobController``.
"""

from .framegen import FrameGenStream
from .neural import NeuralRenderStream, UNBOUNDED_FRAMES

__all__ = ["FrameGenStream", "NeuralRenderStream", "UNBOUNDED_FRAMES"]
