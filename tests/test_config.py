import copy
import json
import pytest
from louasfm_camera.config import ConfigStore, DEFAULTS
from louasfm_camera.models import CameraSettings


def test_roundtrip_backup_and_merge(tmp_path):
    store = ConfigStore(tmp_path/"settings.json")
    data = store.load()
    data["camera"]["exposure_us"] = 3500
    store.save(data)
    previous = store.path.read_bytes()
    data["camera"]["exposure_us"] = 5000
    store.save(data)
    assert store.load() == data
    assert store.path.with_suffix(".json.bak").read_bytes() == previous
    assert DEFAULTS["camera"]["exposure_us"] == 1000
    store.path.write_text('{"camera":{"gain":2}}')
    assert store.load()["camera"]["gain"] == 2
    assert store.load()["camera"]["trigger_mode"] == "external"


def test_corrupt_settings_never_overwritten(tmp_path):
    store = ConfigStore(tmp_path/"settings.json")
    store.path.write_text("not json")
    with pytest.raises(ValueError, match="Исходный файл сохранён"):
        store.load()
    assert store.path.read_text() == "not json"


@pytest.mark.parametrize("change", [{"exposure_us": float("nan")}, {"width": -1},
                                    {"trigger_mode": "bad"}, {"binning": 0},
                                    {"gain": float("inf")}, {"sensor_bits": 12}])
def test_settings_validation(change):
    data = CameraSettings().__dict__.copy()
    data.update(change)
    with pytest.raises((ValueError, TypeError)):
        CameraSettings(**data).validate()


def test_invalid_save_preserves_previous(tmp_path):
    store = ConfigStore(tmp_path/"settings.json")
    store.save(copy.deepcopy(DEFAULTS))
    previous = store.path.read_bytes()
    data = json.loads(previous)
    data["camera"]["height"] = -5
    with pytest.raises(ValueError):
        store.save(data)
    assert store.path.read_bytes() == previous
