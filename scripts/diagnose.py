"""Print platform/package information and enumerate cameras without opening them."""
import importlib.metadata
import platform
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
print('Python:', sys.version)
print('Platform:', platform.platform(), platform.machine())
for name in ['PySide6-Essentials', 'numpy', 'pyqtgraph', 'Pillow', 'pypylon']:
    try:
        print(name, importlib.metadata.version(name))
    except importlib.metadata.PackageNotFoundError:
        print(name, 'MISSING')
from louasfm_camera.cameras.basler import BaslerCamera  # noqa: E402 - script adds the project path first
try:
    camera = BaslerCamera()
    print('Devices:', camera.discover())
except Exception as error:
    print('Discovery failed:', error)
    raise SystemExit(1)
