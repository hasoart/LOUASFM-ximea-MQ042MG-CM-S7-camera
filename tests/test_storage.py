import json
import threading
import numpy as np
import pytest
from PIL import Image
from louasfm_camera.models import Frame
from louasfm_camera.services.storage import ImageWriter


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
@pytest.mark.parametrize("image_format", ["TIFF", "PNG"])
def test_raw_pixels_survive_saving(tmp_path, dtype, image_format):
    pixels = np.array([[0, 1, 127], [255, 11, 200]], dtype=dtype)
    if dtype == np.uint16:
        pixels[1, 1] = 4095
        pixels[1, 2] = 65535
    writer = ImageWriter()
    try:
        first = writer.submit(Frame(pixels, 17), tmp_path, "../unsafe/name", image_format, {"pulses": {"D2": [[0,1],[200,0]]}})
        second = writer.submit(Frame(pixels, 17), tmp_path, "../unsafe/name", image_format)
        paths = [first.result(5), second.result(5)]
        assert paths[0] != paths[1]
        for path in paths:
            np.testing.assert_array_equal(np.array(Image.open(path)), pixels)
        metadata = json.loads(__import__('pathlib').Path(paths[0]).with_suffix('.json').read_text())
        assert metadata["frame"]["dtype"] == str(pixels.dtype)
        assert metadata["context"]["pulses"]["D2"][1] == [200, 0]
        assert not list(tmp_path.glob('*.part'))
    finally:
        writer.close()


def test_full_queue_reports_loss_instead_of_silently_dropping(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = ImageWriter._save
    def slow(*args):
        entered.set()
        release.wait(5)
        return original(*args)
    monkeypatch.setattr(ImageWriter, '_save', staticmethod(slow))
    writer = ImageWriter(max_pending=1)
    try:
        frame = Frame(np.zeros((4,4), dtype=np.uint8), 1)
        first = writer.submit(frame, tmp_path)
        assert entered.wait(2)
        second = writer.submit(frame, tmp_path)
        with pytest.raises(RuntimeError, match="очередь"):
            writer.submit(frame, tmp_path)
        release.set()
        assert first.result(5) and second.result(5)
    finally:
        release.set()
        writer.close()


def test_write_error_is_not_success(tmp_path):
    occupied = tmp_path/'file'
    occupied.write_text('not a directory')
    writer = ImageWriter()
    try:
        future = writer.submit(Frame(np.zeros((2,2), dtype=np.uint8), 1), occupied)
        with pytest.raises(OSError):
            future.result(3)
    finally:
        writer.close()
