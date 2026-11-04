"""ROI statistics and projections in raw pixel units, without atom calibration."""
import numpy as np


def analyze(pixels, roi=None):
    if pixels.ndim != 2:
        raise ValueError("Ожидался монохромный двумерный кадр")
    h, w = pixels.shape
    if roi is None:
        x, y, width, height = 0, 0, w, h
    else:
        x, y, width, height = (int(v) for v in roi)
        x, y = max(0, min(x, w-1)), max(0, min(y, h-1))
        width, height = max(1, min(width, w-x)), max(1, min(height, h-y))
    crop = pixels[y:y+height, x:x+width]
    return {"roi": (x, y, width, height), "minimum": int(crop.min()),
            "maximum": int(crop.max()), "mean": float(crop.mean()),
            "sum": float(crop.sum(dtype=np.float64)),
            "profile_x": crop.mean(axis=0), "profile_y": crop.mean(axis=1)}
