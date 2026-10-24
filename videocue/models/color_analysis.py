"""
Scene color statistics used to compare two cameras looking at roughly the same scene.

All features are luma-normalized chroma so small exposure differences between cameras
have little effect. Nothing here relies on pixel correspondence between the two views.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage

ANALYSIS_WIDTH = 192
ANALYSIS_HEIGHT = 108
CENTER_CROP = 0.6
CLIP_LEVEL = 0.96
DARK_LEVEL = 0.06
LUMA_EPS = 0.05
CHROMA_MIN = 0.04
NEUTRAL_PERCENTILE = 40.0
MIN_SECTOR_WEIGHT = 0.02
WB_WEIGHT = 2.0


def _sector_angles() -> np.ndarray:
    primaries = np.array(
        [[1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 1, 1], [0, 0, 1], [1, 0, 1]], dtype=np.float32
    )
    _, cb, cr = _ycbcr(primaries)
    return np.arctan2(cr, cb)


def _ycbcr(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return y, (b - y) / 1.8556, (r - y) / 1.5748


SECTOR_ANGLES = _sector_angles()


def qimage_to_rgb(image: QImage) -> np.ndarray:
    """Downscale a frame and return float32 RGB in 0..1 with shape (H, W, 3)."""
    small = image.scaled(
        ANALYSIS_WIDTH,
        ANALYSIS_HEIGHT,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    ).convertToFormat(QImage.Format.Format_RGB888)
    width, height, stride = small.width(), small.height(), small.bytesPerLine()
    ptr = small.constBits()
    ptr.setsize(small.sizeInBytes())
    rows = np.frombuffer(ptr, dtype=np.uint8).reshape(height, stride)
    rgb = rows[:, : width * 3].reshape(height, width, 3)
    return rgb.astype(np.float32) / 255.0


@dataclass
class ColorSignature:
    wb: np.ndarray  # (2,) mean normalized (cb, cr) of near-neutral pixels
    sectors: np.ndarray  # (6, 2) weighted mean normalized (cb, cr) per hue sector
    sector_weights: np.ndarray  # (6,) fraction of valid pixels belonging to each sector
    mean_luma: float


def compute_signature(frames: list[np.ndarray]) -> ColorSignature:
    """Build a color signature from one or more RGB frames of the same camera."""
    if not frames:
        raise ValueError("No frames to analyze")
    rgb = np.mean(np.stack(frames), axis=0)

    h, w = rgb.shape[:2]
    dy, dx = int(h * (1 - CENTER_CROP) / 2), int(w * (1 - CENTER_CROP) / 2)
    rgb = rgb[dy : h - dy, dx : w - dx].reshape(-1, 3)

    y, cb, cr = _ycbcr(rgb)
    valid = (rgb.max(axis=1) < CLIP_LEVEL) & (y > DARK_LEVEL)
    if valid.sum() < 50:
        raise ValueError("Too few usable pixels (scene too dark or clipped)")

    y, cb, cr = y[valid], cb[valid], cr[valid]
    cbn, crn = cb / (y + LUMA_EPS), cr / (y + LUMA_EPS)
    sat = np.hypot(cbn, crn)

    neutral = sat <= np.percentile(sat, NEUTRAL_PERCENTILE)
    wb = np.array([cbn[neutral].mean(), crn[neutral].mean()], dtype=np.float64)

    chromatic = sat > CHROMA_MIN
    chroma = np.stack([cbn[chromatic], crn[chromatic]], axis=1)
    hue = np.arctan2(chroma[:, 1], chroma[:, 0])
    diff = np.angle(np.exp(1j * (hue[:, None] - SECTOR_ANGLES[None, :])))
    # Soft membership keeps features continuous when a hue drifts across a sector boundary
    membership = np.clip(np.cos(diff * 1.5), 0.0, None) ** 2
    weights = membership.sum(axis=0)
    sectors = (membership.T @ chroma) / np.maximum(weights, 1e-9)[:, None]

    return ColorSignature(
        wb=wb,
        sectors=sectors,
        sector_weights=weights / len(y),
        mean_luma=float(y.mean()),
    )


def common_sector_mask(ref: ColorSignature, tgt: ColorSignature) -> np.ndarray:
    """Sectors with enough pixels in both views to be compared."""
    return (ref.sector_weights >= MIN_SECTOR_WEIGHT) & (tgt.sector_weights >= MIN_SECTOR_WEIGHT)


def wb_residual(ref: ColorSignature, tgt: ColorSignature) -> np.ndarray:
    return tgt.wb - ref.wb


def color_residual(ref: ColorSignature, tgt: ColorSignature, sector_mask: np.ndarray) -> np.ndarray:
    """Residual vector (target - reference) combining white point and hue-sector chroma."""
    sector_diff = (tgt.sectors - ref.sectors)[sector_mask].ravel()
    return np.concatenate([WB_WEIGHT * wb_residual(ref, tgt), sector_diff])


def residual_error(residual: np.ndarray) -> float:
    """RMS error scaled by 100 for readability."""
    if residual.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(residual**2)) * 100.0)
