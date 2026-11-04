"""Deterministic synthetic camera. External pulses are simulated only on request."""
from dataclasses import replace
import time
import numpy as np
from ..models import CameraSettings, Frame


class SimulatedCamera:
    def __init__(self):
        self.opened = False
        self.running = False
        self.settings = CameraSettings()
        self.counter = 0
        self.pending = 0
        self.last = 0.0
        self.rng = np.random.default_rng(1234)

    def discover(self):
        return [{"serial": "DEMO-001", "model": "Демонстрационная камера", "ip": "—"}]

    def open(self, serial="", ip=""):
        self.opened = True
        return self.discover()[0]

    def configure(self, settings):
        if not self.opened or self.running:
            raise RuntimeError("Настройка разрешена для подключённой остановленной камеры")
        settings.validate()
        width = settings.width or 640 // settings.binning
        height = settings.height or 480 // settings.binning
        if width + settings.offset_x > 2592 // settings.binning or height + settings.offset_y > 1942 // settings.binning:
            raise ValueError("ROI выходит за границы демонстрационного сенсора")
        if settings.pixel_format not in ("Mono8", "Mono12", "Mono16"):
            raise ValueError("Демонстрационный драйвер: Mono8, Mono12, Mono16")
        self.settings = replace(settings, width=width, height=height)
        return self.settings, {"pixel_formats": ["Mono8", "Mono12", "Mono16"],
                               "trigger_sources": ["Line1"], "gain_node": "DemoRaw",
                               "exposure_us": {"min": 35, "max": 999985},
                               "gain": {"min": 0, "max": 100}}

    def start(self):
        self.running = True
        self.pending = 0
        self.last = time.monotonic()

    def trigger(self):
        if not self.running or self.settings.trigger_mode != "software":
            raise RuntimeError("Программный триггер доступен только в режиме Software")
        self.pending += 1

    def simulate_external(self):
        if not self.running or self.settings.trigger_mode != "external":
            raise RuntimeError("Сначала запустите демонстрационный внешний триггер")
        self.pending += 1

    def read(self, timeout_ms=100):
        if not self.running:
            return None
        rate = self.settings.frame_rate or 10
        due = self.settings.trigger_mode == "free" and time.monotonic() - self.last >= 1 / rate
        if not due and not self.pending:
            time.sleep(min(timeout_ms / 1000, 0.02))
            return None
        self.pending = max(0, self.pending - 1)
        self.counter += 1
        self.last = time.monotonic()
        h, w = self.settings.height, self.settings.width
        y, x = np.ogrid[:h, :w]
        peak = 180 if self.settings.pixel_format == "Mono8" else 3000
        image = 20 + peak * np.exp(-((x-w/2-10*np.sin(self.counter/5))**2/(w/8)**2 + (y-h/2)**2/(h/8)**2)/2)
        image += self.rng.normal(0, 2, (h, w))
        dtype = np.uint8 if self.settings.pixel_format == "Mono8" else np.uint16
        return Frame(np.clip(image, 0, np.iinfo(dtype).max).astype(dtype), self.counter,
                     metadata={"backend": "simulated", "simulated": True})

    def stop(self):
        self.running = False
        self.pending = 0

    def close(self):
        self.stop()
        self.opened = False
