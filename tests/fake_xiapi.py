"""Strict xiAPI test double following official SDK 4.34.00 signatures/types.

This is not a sensor/USB emulator. Enumeration returns bytes without opening;
enum min/max are symbolic; image memory is reused; only XI_TIMEOUT is normal.
"""

from types import SimpleNamespace
import numpy as np


class XiError(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(f"xiAPI error {status}")


class FakeImage:
    def __init__(self):
        self.width = self.height = self.nframe = self.bp_size = 0
        self.tsSec, self.tsUSec = 12, 345
        self.pixels = None

    def get_image_data_numpy(self):
        return self.pixels


class FakeCamera:
    def __init__(self, sdk, dev_id=0):
        self.sdk = sdk
        self.dev_id = dev_id
        self.CAM_OPEN = False
        self.running = False
        self.pending = 0
        self.frame_id = 0
        self.failure = None
        self.frame_advance = 1
        self.values = {
            "trigger_source": "XI_TRG_OFF",
            "trigger_selector": "XI_TRG_SEL_FRAME_START",
            "aeag": True,
            "hdr": True,
            "shutter_type": "XI_SHUTTER_GLOBAL",
            "gain_selector": "XI_GAIN_SELECTOR_ALL",
            "gain": 0.0,
            "exposure": 1000,
            "recent_frame": True,
            "buffer_policy": "XI_BP_UNSAFE",
            "buffers_queue_size": 4,
            "imgdataformat": "XI_MONO8",
            "sensor_bit_depth": "XI_BPP_10",
            "output_bit_depth": "XI_BPP_8",
            "image_data_bit_depth": "XI_BPP_8",
            "output_bit_packing": False,
            "gammaY": 2.2,
            "gammaC": 1.0,
            "offsetX": 0,
            "offsetY": 0,
            "width": 2048,
            "height": 2048,
            "downsampling": "XI_DWN_1x1",
            "downsampling_type": "XI_BINNING",
            "acq_timing_mode": "XI_ACQ_TIMING_MODE_FREE_RUN",
            "framerate": 10.0,
            "gpi_selector": "XI_GPI_PORT1",
            "gpi_mode": "XI_GPI_OFF",
        }
        self.ranges = {
            "exposure": (26, 1_000_000, 1),
            "gain": (0.0, 6.0, 0.1),
            "offsetX": (0, 2040, 16),
            "offsetY": (0, 2046, 2),
            "width": (16, 2048, 16),
            "height": (2, 2048, 2),
            "buffers_queue_size": (2, 64, 1),
            "framerate": (1.0, 90.3, 0.1),
            "gpi_selector": ("XI_GPI_PORT1", "XI_GPI_PORT1", 1),
        }

    def get_number_devices(self):
        assert not self.CAM_OPEN, "Enumeration is called before opening"
        return len(self.sdk.serials)

    def get_device_info_string(self, param):
        assert not self.CAM_OPEN
        return {"device_sn": self.sdk.serials[self.dev_id].encode(), "device_name": b"MQ042MG-CM-S7"}[param]

    def open_device_by_SN(self, serial_number):
        assert serial_number == self.sdk.serials[self.dev_id]
        self.CAM_OPEN = True
        self.sdk.opened.append(self)

    def close_device(self):
        assert self.CAM_OPEN
        self.CAM_OPEN = False
        self.running = False

    def get_param(self, param, buffer_size=256, raw_output=False):
        assert self.CAM_OPEN
        if self.failure is not None:
            raise XiError(self.failure)
        name, _, modifier = param.partition(":")
        if modifier:
            if name not in self.ranges:
                raise XiError(107)
            return self.ranges[name][{"min": 0, "max": 1, "inc": 2}[modifier]]
        if name not in self.values:
            raise XiError(100)
        return self.values[name]

    def set_param(self, param, val):
        assert self.CAM_OPEN
        if self.failure is not None:
            raise XiError(self.failure)
        self.sdk.writes.append((param, val))
        if param == "trigger_software":
            if not self.running or self.values["trigger_source"] != "XI_TRG_SOFTWARE":
                raise XiError(40)
            self.pending += 1
            return
        assert not self.running, "Settings must change while acquisition is stopped"
        if param not in self.values:
            raise XiError(100)
        if param in ("downsampling", "sensor_bit_depth"):
            allowed = {"downsampling": ["XI_DWN_1x1"], "sensor_bit_depth": ["XI_BPP_8", "XI_BPP_10"]}[param]
            if val not in allowed:
                raise XiError(101)
        if param in self.ranges and isinstance(self.ranges[param][0], (int, float)):
            low, high, inc = self.ranges[param]
            if not low <= val <= high:
                raise XiError(205)
            if isinstance(low, int) and (not isinstance(val, int) or (val - low) % inc):
                raise XiError(101)
        if param == "imgdataformat":
            # Official documented automatic changes made by this parameter.
            eight = val.endswith("8")
            self.values.update(
                sensor_bit_depth="XI_BPP_8" if eight else "XI_BPP_10",
                output_bit_depth="XI_BPP_8" if eight else "XI_BPP_12",
                image_data_bit_depth="XI_BPP_8" if eight else "XI_BPP_12",
            )
        self.values[param] = val
        if param == "output_bit_depth":
            self.values["image_data_bit_depth"] = val

    def start_acquisition(self):
        assert self.CAM_OPEN and not self.running
        self.running = True
        self.pending = 0
        self.frame_id = 0

    def stop_acquisition(self):
        assert self.running
        self.running = False

    def get_image(self, image, timeout=5000):
        assert self.running
        if self.failure is not None:
            raise XiError(self.failure)
        if self.values["trigger_source"] != "XI_TRG_OFF" and not self.pending:
            raise XiError(10)
        self.pending = max(0, self.pending - 1)
        self.frame_id = (self.frame_id + self.frame_advance) % (2**32)
        image.nframe = self.frame_id
        image.width = self.values["width"]
        image.height = self.values["height"]
        dtype = np.uint8 if self.values["imgdataformat"].endswith("8") else np.uint16
        if image.pixels is None or image.pixels.shape != (image.height, image.width) or image.pixels.dtype != dtype:
            image.pixels = np.zeros((image.height, image.width), dtype=dtype)
        image.pixels.fill(self.frame_id % 255)
        image.pixels[0, 0] = 255 if dtype == np.uint8 else 1023
        image.bp_size = image.pixels.nbytes


def make_sdk(serials=("XIMEA-0001",)):
    sdk = SimpleNamespace(Xi_error=XiError, Image=FakeImage, serials=list(serials), opened=[], writes=[])
    sdk.Camera = lambda dev_id=0: FakeCamera(sdk, dev_id)
    return sdk
