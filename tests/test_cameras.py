from dataclasses import replace
import numpy as np
import pytest
from louasfm_camera.models import CameraSettings
from louasfm_camera.cameras.simulated import SimulatedCamera
from louasfm_camera.cameras.ximea_camera import XimeaCamera
from louasfm_camera.services.analysis import analyze
from fake_xiapi import make_sdk, XiError


@pytest.fixture
def camera():
    driver = XimeaCamera(make_sdk())
    driver.open()
    yield driver
    driver.close()


def test_demo_external_and_software_are_explicit():
    camera = SimulatedCamera()
    camera.open()
    camera.configure(CameraSettings(trigger_mode="external", width=40, height=30))
    camera.start()
    assert camera.read(1) is None
    camera.simulate_external()
    assert camera.read(1).pixels.shape == (30, 40)
    with pytest.raises(RuntimeError):
        camera.trigger()
    camera.stop()
    camera.configure(CameraSettings(trigger_mode="software", width=40, height=30, pixel_format="Raw16"))
    camera.start()
    camera.trigger()
    assert camera.read(1).pixels.dtype == np.uint16
    camera.close()


def test_roi_profiles_and_clipping():
    pixels = np.arange(12, dtype=np.uint16).reshape(3, 4)
    data = analyze(pixels, (2, 1, 20, 20))
    assert data["roi"] == (2, 1, 2, 2)
    assert data["maximum"] == 11
    np.testing.assert_array_equal(data["profile_x"], [8, 9])
    assert data["sum"] == 34


def test_enumeration_does_not_open_camera():
    sdk = make_sdk()
    driver = XimeaCamera(sdk)
    assert driver.discover()[0]["model"] == "MQ042MG-CM-S7"
    assert not sdk.opened and not sdk.writes


def test_multiple_devices_require_serial():
    driver = XimeaCamera(make_sdk(("A", "B")))
    with pytest.raises(RuntimeError, match="несколько"):
        driver.open()
    assert driver.open("B")["serial"] == "B"
    driver.close()


@pytest.mark.parametrize(
    "mode,expected", [("external", "XI_TRG_EDGE_RISING"), ("software", "XI_TRG_SOFTWARE"), ("free", "XI_TRG_OFF")]
)
def test_xiapi_configuration_and_actual_values(camera, mode, expected):
    actual, caps = camera.configure(
        CameraSettings(width=100, height=61, exposure_us=1000.9, trigger_mode=mode, pixel_format="Raw16")
    )
    assert actual.width == 96 and actual.height == 60 and actual.exposure_us == 1000
    assert caps["trigger_sources"] == ["GPI1"]
    assert camera.camera.values["trigger_source"] == expected
    assert camera.camera.values["aeag"] is False and camera.camera.values["hdr"] is False
    assert camera.camera.values["recent_frame"] is False
    assert camera.camera.values["buffer_policy"] == "XI_BP_SAFE"
    assert camera.camera.values["sensor_bit_depth"] == "XI_BPP_10"
    assert camera.camera.values["output_bit_depth"] == "XI_BPP_10"
    assert camera.camera.values["gpi_mode"] == ("XI_GPI_TRIGGER" if mode == "external" else "XI_GPI_OFF")


def test_falling_edge_and_usb_frame_rate_limit(camera):
    actual, _ = camera.configure(CameraSettings(width=64, height=48, trigger_activation="FallingEdge", frame_rate=10))
    assert camera.camera.values["trigger_source"] == "XI_TRG_EDGE_FALLING"
    assert camera.camera.values["acq_timing_mode"] == "XI_ACQ_TIMING_MODE_FRAME_RATE_LIMIT"
    assert actual.frame_rate == 10


@pytest.mark.parametrize(
    "fmt,dtype", [("Mono8", np.uint8), ("Mono16", np.uint16), ("Raw8", np.uint8), ("Raw16", np.uint16)]
)
def test_acquisition_copies_memory_and_pixel_metadata(camera, fmt, dtype):
    camera.configure(CameraSettings(width=64, height=48, trigger_mode="software", pixel_format=fmt))
    camera.start()
    assert camera.read(1) is None
    camera.trigger()
    first = camera.read(1)
    copy = first.pixels.copy()
    camera.trigger()
    second = camera.read(1)
    assert first.pixels.dtype == dtype
    assert first.frame_id == 1 and second.frame_id == 2
    np.testing.assert_array_equal(first.pixels, copy)
    assert first.camera_timestamp == 12_000_345
    assert first.metadata["pixel_pipeline"]["sensor_bit_depth"] == "XI_BPP_10"
    assert first.metadata["camera_timestamp_unit"] == "microseconds"


def test_unsupported_requested_downsampling_is_not_silently_ignored(camera):
    with pytest.raises(RuntimeError, match="downsampling") as error:
        camera.configure(CameraSettings(binning=2))
    assert error.value.__cause__.status == 101


def test_gap_in_frame_numbers_is_an_error_but_wrap_and_new_start_are_valid(camera):
    camera.configure(CameraSettings(width=64, height=48, trigger_mode="free"))
    camera.start()
    camera.read(1)
    camera.camera.frame_advance = 3
    with pytest.raises(RuntimeError, match="Разрыв"):
        camera.read(1)
    camera.stop()
    camera.camera.frame_advance = 1
    camera.start()
    camera.read(1)
    camera.last_frame_id = 2**32 - 1
    camera.camera.frame_id = 2**32 - 1
    assert camera.read(1).frame_id == 0


@pytest.mark.parametrize("status", [9, 25, 46, 52])
def test_only_timeout_is_normal(camera, status):
    camera.configure(CameraSettings(width=64, height=48))
    camera.start()
    camera.camera.failure = status
    with pytest.raises(XiError):
        camera.read(1)
    camera.camera.failure = None


def test_device_error_is_not_hidden_as_unsupported(camera):
    camera.camera.failure = 25
    with pytest.raises(XiError):
        camera._get("hdr", optional=True)
    camera.camera.failure = None
    assert camera._get("imaginary_optional_parameter", optional=True) is None


def test_partial_frame_is_rejected(camera, monkeypatch):
    camera.configure(CameraSettings(width=64, height=48, trigger_mode="free"))
    camera.start()
    original = camera.camera.get_image

    def incomplete(image, timeout):
        original(image, timeout)
        image.bp_size = 1

    monkeypatch.setattr(camera.camera, "get_image", incomplete)
    with pytest.raises(RuntimeError, match="неполный"):
        camera.read(1)


def test_zero_frame_rate_restores_free_run(camera):
    settings = CameraSettings(width=64, height=48, frame_rate=10)
    camera.configure(settings)
    camera.configure(replace(settings, frame_rate=0))
    assert camera.camera.values["acq_timing_mode"] == "XI_ACQ_TIMING_MODE_FREE_RUN"
