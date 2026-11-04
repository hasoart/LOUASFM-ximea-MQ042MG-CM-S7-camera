from dataclasses import replace
import numpy as np
import pytest
from louasfm_camera.models import CameraSettings
from louasfm_camera.cameras.simulated import SimulatedCamera
from louasfm_camera.cameras.basler import BaslerCamera
from louasfm_camera.services.analysis import analyze


def test_demo_external_and_software_are_explicit():
    camera = SimulatedCamera()
    camera.open()
    camera.configure(CameraSettings(trigger_mode='external',width=40,height=30))
    camera.start()
    assert camera.read(1) is None
    camera.simulate_external()
    assert camera.read(1).pixels.shape == (30,40)
    with pytest.raises(RuntimeError):
        camera.trigger()
    camera.stop()
    camera.configure(CameraSettings(trigger_mode='software',width=40,height=30,pixel_format='Mono12'))
    camera.start()
    camera.trigger()
    assert camera.read(1).pixels.dtype == np.uint16
    camera.close()


def test_roi_profiles_and_clipping():
    pixels = np.arange(12,dtype=np.uint16).reshape(3,4)
    data = analyze(pixels, (2,1,20,20))
    assert data['roi'] == (2,1,2,2)
    assert data['maximum'] == 11
    np.testing.assert_array_equal(data['profile_x'],[8,9])
    assert data['sum'] == 34


def test_basler_sdk_emulator_acquisition_and_reconfigure():
    camera = BaslerCamera()
    try:
        devices = camera.discover()
        assert any(d['model'] == 'Emulation' for d in devices)
        info = camera.open(serial=devices[0]['serial'])
        assert info['model'] == 'Emulation'
        settings,caps = camera.configure(CameraSettings(trigger_mode='software',width=80,height=60))
        assert 'Mono8' in caps['pixel_formats']
        assert camera._node('ThisNodeDoesNotExist',required=False) is None
        assert camera._node('ExposureTimeAbs') is not None
        camera.start()
        assert camera.read(50) is None
        camera.trigger()
        first = camera.read(2000)
        assert first.pixels.shape == (60,80)
        copy = first.pixels.copy()
        camera.trigger()
        assert camera.read(2000) is not None
        np.testing.assert_array_equal(first.pixels,copy)
        camera.stop()
        actual,_ = camera.configure(replace(settings,pixel_format='Mono12',binning=2,width=40,height=30))
        assert actual.width == 40 and actual.binning == 2
        camera.start()
        camera.trigger()
        assert camera.read(2000).pixels.dtype == np.uint16
    finally:
        camera.close()


def test_force_ip_validation_never_calls_transport_for_bad_values():
    camera = BaslerCamera()
    for values in [('bad','192.168.2.2','255.255.255.0'),
                   ('001122334455','192.168.2.0','255.255.255.0')]:
        with pytest.raises(ValueError):
            camera.force_ip(*values)
