from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..core.motion import to_float16


@dataclass(slots=True)
class Guide:
    motion: np.ndarray
    reset: bool
    scene_score: float
    duplicate: bool
    confidence: float


class DLSSGGuideGenerator:
    """CUDA-free guide estimation; it never creates an image frame."""

    def __init__(self, width: int, height: int, flow_width: int = 640) -> None:
        self.width = width
        self.height = height
        scale = min(1.0, flow_width / max(1, width))
        self.flow_width = max(64, int(round(width * scale / 2) * 2))
        self.flow_height = max(64, int(round(height * scale / 2) * 2))
        self.previous: np.ndarray | None = None
        self.zero = np.zeros((height, width, 2), dtype=np.float16)
        self._scale = np.array(
            [width / self.flow_width, height / self.flow_height], dtype=np.float32
        )
        self.flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        self.flow.setUseSpatialPropagation(True)
        self.flow.setFinestScale(1)

    def _gray(self, rgba: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(rgba, cv2.COLOR_RGBA2GRAY)
        return cv2.resize(gray, (self.flow_width, self.flow_height), interpolation=cv2.INTER_AREA)

    def process(self, rgba: np.ndarray, *, force_reset: bool = False) -> Guide:
        current = self._gray(rgba)
        if self.previous is None:
            guide = Guide(self.zero, True, 1.0, False, 0.0)
        else:
            difference = cv2.absdiff(current, self.previous)
            score = float(np.mean(difference)) / 255.0
            duplicate = score < 0.0005
            reset = force_reset or score > 0.24
            if reset or duplicate:
                vectors = self.zero
                confidence = 1.0 if duplicate else 0.0
            else:
                calculated = self.flow.calc(current, self.previous, None)
                # Validate at flow resolution: the finite check over the
                # full-resolution field cost ~60 ms per 1080p frame, more than
                # the flow itself, and a non-finite low-resolution vector is
                # the only way the upsampled field can contain one. The two
                # channel checks avoid reducing an HxWx2 array along its
                # tiny last axis.
                finite = np.isfinite(calculated[..., 0])
                np.logical_and(finite, np.isfinite(calculated[..., 1]), out=finite)
                confidence = float(np.mean(finite))
                reset = confidence < 0.98
                if reset:
                    vectors = self.zero
                else:
                    if confidence < 1.0:
                        calculated[~finite] = 0
                    # Scale to full-resolution pixel units before upsampling:
                    # bilinear interpolation is linear, so the result matches
                    # scaling afterwards while touching 18x fewer values.
                    calculated *= self._scale
                    vectors = to_float16(
                        cv2.resize(calculated, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
                    )
            guide = Guide(vectors, reset, score, duplicate, confidence)
        self.previous = current
        return guide
