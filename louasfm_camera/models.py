"""Device-neutral settings and copied image buffers; no GUI dependencies."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import math

import numpy as np


@dataclass(frozen=True)
class CameraSettings:
    exposure_us: float = 1000.0
    gain: float | None = None  # None selects the camera's minimum native gain.
    width: int = 0  # Zero means full sensor after binning.
    height: int = 0
    offset_x: int = 0
    offset_y: int = 0
    binning: int = 1
    pixel_format: str = "Mono8"
    trigger_mode: str = "external"  # free, software, external
    trigger_source: str = "Line1"
    trigger_activation: str = "RisingEdge"
    packet_size: int = 1500
    inter_packet_delay: int = 0
    frame_rate: float = 0.0  # Zero disables the optional rate limiter.

    def validate(self):
        if not math.isfinite(self.exposure_us) or self.exposure_us <= 0:
            raise ValueError("Экспозиция должна быть конечным положительным числом")
        if self.gain is not None and (not math.isfinite(self.gain) or self.gain < 0):
            raise ValueError("Усиление должно быть конечным неотрицательным числом")
        for key in ("width", "height", "offset_x", "offset_y", "inter_packet_delay"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{key}: требуется целое неотрицательное число")
        if self.binning not in (1, 2, 3, 4):
            raise ValueError("Binning: допустимы 1, 2, 3, 4")
        if self.trigger_mode not in ("free", "software", "external"):
            raise ValueError("Неизвестный режим триггера")
        if self.trigger_activation not in ("RisingEdge", "FallingEdge"):
            raise ValueError("Неизвестная полярность триггера")
        if not self.pixel_format.startswith("Mono"):
            raise ValueError("Эта программа поддерживает монохромные форматы Mono")
        if not self.trigger_source or not isinstance(self.trigger_source, str):
            raise ValueError("Нужен вход внешнего триггера")
        if self.trigger_mode == "external" and not self.trigger_source.startswith("Line"):
            raise ValueError("Для внешнего триггера выберите физический вход Line…")
        if not isinstance(self.packet_size, int) or not 576 <= self.packet_size <= 9000:
            raise ValueError("Размер пакета должен быть от 576 до 9000")
        if not math.isfinite(self.frame_rate) or self.frame_rate < 0:
            raise ValueError("Ограничение частоты должно быть конечным и неотрицательным")
        return self


@dataclass
class Frame:
    pixels: np.ndarray
    frame_id: int
    camera_timestamp: int | None = None
    received_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def description(self):
        return {"frame_id": self.frame_id, "camera_timestamp_ticks": self.camera_timestamp,
                "received_utc": self.received_utc, "shape": list(self.pixels.shape),
                "dtype": str(self.pixels.dtype), **self.metadata}


def settings_dict(settings: CameraSettings):
    return asdict(settings)
