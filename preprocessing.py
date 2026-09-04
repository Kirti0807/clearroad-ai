"""
Visibility enhancement using CLAHE.

Why CLAHE and not plain histogram equalization:
plain equalization stretches contrast globally, which tends to blow out
already-bright regions (sky) while doing little for dark, fog-choked areas
near the road. CLAHE operates on small tiles independently and clips the
histogram to limit noise amplification, which is why it works better on
frames with uneven fog density.
"""

import cv2
import numpy as np

import config


class VisibilityEnhancer:
    def __init__(
        self,
        clip_limit: float = config.CLAHE_CLIP_LIMIT,
        tile_grid_size: tuple = config.CLAHE_TILE_GRID_SIZE,
    ):
        self._clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)

    def enhance(self, frame_bgr: np.ndarray) -> np.ndarray:
        """
        Applies CLAHE on the L channel of LAB color space.
        We convert to LAB (not just grayscale) so we boost contrast on
        lightness only and leave color (A/B channels) untouched -- this
        avoids introducing color casts into the enhanced frame.
        """
        lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        l_enhanced = self._clahe.apply(l_channel)

        merged = cv2.merge((l_enhanced, a_channel, b_channel))
        enhanced_bgr = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
        return enhanced_bgr

    def estimate_visibility_score(self, frame_bgr: np.ndarray) -> float:
        """
        Rough proxy for how 'foggy' a frame is, based on the standard
        deviation of pixel intensity in the L channel. Fog compresses the
        dynamic range (everything trends toward mid-gray), so low std-dev
        roughly correlates with low visibility. This is a heuristic, not a
        calibrated physical measurement -- good enough to log a relative
        trend for the dashboard, not for safety-critical decisions on its own.
        """
        lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]
        std_dev = float(np.std(l_channel))
        # Normalize roughly to a 0-100 scale for readability on the dashboard.
        score = min(100.0, (std_dev / 80.0) * 100.0)
        return round(score, 1)
