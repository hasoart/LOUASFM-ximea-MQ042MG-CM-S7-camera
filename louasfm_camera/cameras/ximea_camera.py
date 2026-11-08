"""XIMEA xiAPI adapter for the mono CMV4000 USB3 camera; no GUI dependencies."""

from dataclasses import replace
import math

import numpy as np

from ..models import CameraSettings, Frame
from ..sdk_runtime import load_xiapi

# xiAPI status values from the manufacturer's xidefs.py, SDK 4.34.00.
UNSUPPORTED = frozenset((12, 26, 100, 106, 107, 119))
FORMATS = {"Mono8": "XI_MONO8", "Mono16": "XI_MONO16", "Raw8": "XI_RAW8", "Raw16": "XI_RAW16"}


def text(value):
    return value.decode("utf-8", errors="replace").rstrip("\0") if isinstance(value, bytes) else str(value)


class XimeaCamera:
    def __init__(self, xiapi_module=None):
        self.sdk = xiapi_module if xiapi_module is not None else load_xiapi()
        self.camera = None
        self.image = None
        self.running = False
        self.settings = None
        self.info = {}
        self.pixel_metadata = {}
        self.last_frame_id = None

    def discover(self):
        probe = self.sdk.Camera()
        result = []
        for index in range(probe.get_number_devices()):
            device = self.sdk.Camera(dev_id=index)
            result.append(
                {
                    "serial": text(device.get_device_info_string("device_sn")),
                    "model": text(device.get_device_info_string("device_name")),
                    "device_index": index,
                    "transport": "USB3 / xiAPI",
                }
            )
        return result  # No device was opened or had its trigger/settings changed.

    def open(self, serial=""):
        if self.camera is not None:
            raise RuntimeError("Камера уже подключена")
        devices = self.discover()
        matches = [device for device in devices if not serial or device["serial"] == serial]
        if not matches:
            raise RuntimeError("Камера XIMEA не найдена. Проверьте USB3, драйвер и xiCOP / xiCamTool.")
        if len(matches) > 1:
            raise RuntimeError("Найдено несколько камер: выберите серийный номер")
        device = self.sdk.Camera(dev_id=matches[0]["device_index"])
        try:
            device.open_device_by_SN(matches[0]["serial"])
        except Exception:
            if getattr(device, "CAM_OPEN", False):
                device.close_device()
            raise
        self.camera = device
        self.image = self.sdk.Image()
        self.info = matches[0].copy()
        return self.info.copy()

    def _get(self, name, optional=False):
        try:
            return self.camera.get_param(name)
        except self.sdk.Xi_error as error:
            if optional and error.status in UNSUPPORTED:
                return None
            raise

    def _set(self, name, value, optional=False):
        try:
            previous = self._get(name, optional=optional)
            if previous == value:
                return previous  # Fixed read-only settings may already be correct.
            if optional and previous is None:
                return None
            self.camera.set_param(name, value)
            return self.camera.get_param(name)
        except self.sdk.Xi_error as error:
            if optional and error.status in UNSUPPORTED:
                return None
            raise

    def _range(self, name):
        low = self._get(name + ":min")
        high = self._get(name + ":max")
        step = self._get(name + ":inc", optional=True)
        return {"node": name, "min": low, "max": high, "inc": step}

    def _number(self, name, value):
        bounds = self._range(name)
        low, high, step = bounds["min"], bounds["max"], bounds["inc"]
        if not low <= value <= high:
            raise ValueError(f"{name}: {value} вне диапазона {low}…{high}")
        if isinstance(low, int):
            step = step or 1
            value = int(low + math.floor((value - low) / step) * step)
        self._set(name, value)
        return self._get(name)

    def configure(self, settings: CameraSettings):
        settings.validate()
        if self.camera is None or self.running:
            raise RuntimeError("Остановите захват перед настройкой камеры")
        self._set("trigger_source", "XI_TRG_OFF")
        self._set("trigger_selector", "XI_TRG_SEL_FRAME_START")
        self._set("aeag", False)
        self._set("hdr", False, optional=True)
        self._set("shutter_type", "XI_SHUTTER_GLOBAL", optional=True)
        self._set("gain_selector", "XI_GAIN_SELECTOR_ALL", optional=True)
        self._set("recent_frame", False)
        self._set("buffer_policy", "XI_BP_SAFE")
        queue_bounds = self._range("buffers_queue_size")
        self._number("buffers_queue_size", max(queue_bounds["min"], min(16, queue_bounds["max"])))
        self._set("imgdataformat", FORMATS[settings.pixel_format])
        # imgdataformat automatically alters these settings: apply/read them AFTER it.
        self._set("sensor_bit_depth", f"XI_BPP_{settings.sensor_bits}")
        output_bits = 8 if settings.pixel_format.endswith("8") else settings.sensor_bits
        self._set("output_bit_depth", f"XI_BPP_{output_bits}")
        self._set("output_bit_packing", False, optional=True)
        self._set("gammaY", 1.0, optional=True)
        self._set("gammaC", 1.0, optional=True)
        for axis in ("offsetX", "offsetY"):
            self._number(axis, 0)
        # Readout mode changes invalidate ROI limits; reduce before changing it.
        for axis in ("width", "height"):
            self._number(axis, self._range(axis)["min"])
        if settings.binning != 1:
            self._set("downsampling_type", "XI_BINNING")
        self._set("downsampling", f"XI_DWN_{settings.binning}x{settings.binning}")
        width = self._number("width", settings.width or self._range("width")["max"])
        height = self._number("height", settings.height or self._range("height")["max"])
        offset_x = self._number("offsetX", settings.offset_x)
        offset_y = self._number("offsetY", settings.offset_y)
        exposure = self._number("exposure", settings.exposure_us)
        gain = self._number("gain", self._range("gain")["min"] if settings.gain is None else settings.gain)
        if settings.frame_rate:
            self._set("acq_timing_mode", "XI_ACQ_TIMING_MODE_FRAME_RATE_LIMIT")
            rate = self._number("framerate", settings.frame_rate)
        else:
            self._set("acq_timing_mode", "XI_ACQ_TIMING_MODE_FREE_RUN")
            rate = 0.0
        # Disable other GPI trigger routes so only the selected physical input triggers.
        for index in self._input_indices():
            self._set("gpi_selector", f"XI_GPI_PORT{index}")
            self._set("gpi_mode", "XI_GPI_OFF")
        if settings.trigger_mode == "external":
            port = int(settings.trigger_source[3:])
            if port not in self._input_indices():
                raise ValueError(f"Вход {settings.trigger_source} недоступен у камеры")
            self._set("gpi_selector", f"XI_GPI_PORT{port}")
            self._set("gpi_mode", "XI_GPI_TRIGGER")
            trigger = "XI_TRG_EDGE_RISING" if settings.trigger_activation == "RisingEdge" else "XI_TRG_EDGE_FALLING"
        else:
            trigger = "XI_TRG_SOFTWARE" if settings.trigger_mode == "software" else "XI_TRG_OFF"
        self._set("trigger_source", trigger)
        self.settings = replace(
            settings,
            exposure_us=exposure,
            gain=gain,
            width=width,
            height=height,
            offset_x=offset_x,
            offset_y=offset_y,
            frame_rate=rate,
        )
        self.pixel_metadata = {
            key: self._get(key, optional=True)
            for key in (
                "imgdataformat",
                "sensor_bit_depth",
                "output_bit_depth",
                "image_data_bit_depth",
                "output_bit_packing",
                "shutter_type",
                "hdr",
                "aeag",
                "gammaY",
            )
        }
        capabilities = {
            "pixel_formats": list(FORMATS),
            "trigger_sources": [f"GPI{i}" for i in self._input_indices()],
            "gain_node": "gain (dB)",
            "sensor_bits": self.pixel_metadata["sensor_bit_depth"],
            **{
                field: self._range(name)
                for field, name in (
                    ("exposure_us", "exposure"),
                    ("gain", "gain"),
                    ("width", "width"),
                    ("height", "height"),
                )
            },
        }
        return self.settings, capabilities

    def _input_indices(self):
        minimum = self._get("gpi_selector:min")
        maximum = self._get("gpi_selector:max")

        # xiAPI Python returns symbolic strings for enum min/max, not integers.
        def index(value):
            return int(value.removeprefix("XI_GPI_PORT")) if isinstance(value, str) else int(value)

        return list(range(index(minimum), index(maximum) + 1))

    def start(self):
        if self.camera is None or self.running:
            raise RuntimeError("Подключите камеру и остановите предыдущий захват")
        self.last_frame_id = None
        self.camera.start_acquisition()
        self.running = True

    def read(self, timeout_ms=100):
        if not self.running:
            return None
        try:
            self.camera.get_image(self.image, timeout=timeout_ms)
        except self.sdk.Xi_error as error:
            if error.status == 10:  # XI_TIMEOUT; no physical pulse yet is normal.
                return None
            raise
        dtype = np.dtype("uint8" if self.settings.pixel_format.endswith("8") else "uint16")
        shape = (int(self.image.height), int(self.image.width))
        required_bytes = shape[0] * shape[1] * dtype.itemsize
        if shape != (self.settings.height, self.settings.width) or self.image.bp_size < required_bytes:
            raise RuntimeError("xiAPI вернул неполный кадр или неожиданный размер ROI")
        pixels = self.image.get_image_data_numpy().copy()
        if pixels.ndim != 2 or pixels.dtype != dtype:
            raise RuntimeError("xiAPI вернул неподдерживаемый формат изображения")
        if pixels.shape != shape or pixels.nbytes > self.image.bp_size:
            raise RuntimeError("xiAPI вернул неполный кадр")
        frame_id = int(self.image.nframe)
        if self.last_frame_id is not None:
            advance = (frame_id - self.last_frame_id) % (2**32)
            if advance != 1:
                raise RuntimeError(f"Разрыв номеров кадров xiAPI: {self.last_frame_id} → {frame_id}; захват остановлен")
        self.last_frame_id = frame_id
        timestamp = int(self.image.tsSec) * 1_000_000 + int(self.image.tsUSec)
        return Frame(
            pixels,
            frame_id,
            timestamp,
            metadata={
                "backend": "ximea",
                "camera": self.info.copy(),
                "camera_timestamp_unit": "microseconds",
                "pixel_pipeline": self.pixel_metadata.copy(),
            },
        )

    def trigger(self):
        if not self.running or self.settings.trigger_mode != "software":
            raise RuntimeError("Программный триггер требует запущенного Software-режима")
        self.camera.set_param("trigger_software", 1)

    def stop(self):
        if self.camera is not None and self.running:
            try:
                self.camera.stop_acquisition()
            finally:
                self.running = False

    def close(self):
        if self.camera is not None:
            try:
                self.stop()
            finally:
                try:
                    self.camera.close_device()
                finally:
                    self.camera = self.image = None
