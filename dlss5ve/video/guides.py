from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..core.motion import to_float16

@dataclass(slots=True)
class GuideFrame:
    motion: np.ndarray
    reset: bool
    scene_score: float


class TemporalGuideGenerator:
    """Estimate the guide buffers an encoded video does not contain."""

    def __init__(self, width: int, height: int, flow_width: int = 640) -> None:
        self.width = width
        self.height = height
        scale = min(1.0, flow_width / width)
        self.flow_width = max(64, int(round(width * scale / 2) * 2))
        self.flow_height = max(64, int(round(height * scale / 2) * 2))
        self.previous_gray: np.ndarray | None = None
        self.zero_motion = np.zeros((height, width, 2), dtype=np.float16)
        self._scale = np.array(
            [width / self.flow_width, height / self.flow_height], dtype=np.float32
        )
        self.dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        self.dis.setUseSpatialPropagation(True)
        self.dis.setFinestScale(1)

    def _small_gray(self, rgba: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(rgba, cv2.COLOR_RGBA2GRAY)
        return cv2.resize(
            gray,
            (self.flow_width, self.flow_height),
            interpolation=cv2.INTER_AREA,
        )

    def process(self, rgba: np.ndarray) -> GuideFrame:
        current = self._small_gray(rgba)
        if self.previous_gray is None:
            motion = self.zero_motion
            reset = True
            scene_score = 1.0
        else:
            scene_score = float(np.mean(cv2.absdiff(current, self.previous_gray))) / 255.0
            reset = scene_score > 0.24
            if reset:
                motion = self.zero_motion
            else:
                motion = self.dis.calc(current, self.previous_gray, None)
                # Scale at flow resolution, then upsample; see
                # frame_interpolation.guides for the reasoning.
                motion *= self._scale
                motion = to_float16(
                    cv2.resize(motion, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
                )
        self.previous_gray = current
        return GuideFrame(
            motion=motion,
            reset=reset,
            scene_score=scene_score,
        )
