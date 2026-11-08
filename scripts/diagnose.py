"""Show runtime/SDK diagnostics and enumerate cameras without opening them."""
import argparse
import ctypes
import importlib.metadata
import platform
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from louasfm_camera.sdk_runtime import configured_roots, load_xiapi  # noqa: E402
from louasfm_camera.cameras.ximea_camera import XimeaCamera  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-library', type=Path,
                        help='Optional read-only native SDK enumeration, without installing the Python wrapper')
    args = parser.parse_args()
    print('Python:', sys.version)
    print('Platform:', platform.platform(), platform.machine())
    for name in ['PySide6-Essentials', 'numpy', 'pyqtgraph', 'Pillow']:
        try:
            print(name, importlib.metadata.version(name))
        except importlib.metadata.PackageNotFoundError:
            print(name, 'MISSING')
    print('SDK roots:', list(map(str, configured_roots())))
    if args.native_library:
        library = ctypes.CDLL(str(args.native_library.resolve()))
        function = library.xiGetNumberDevices
        function.argtypes = [ctypes.POINTER(ctypes.c_uint32)]
        function.restype = ctypes.c_int
        count = ctypes.c_uint32()
        status = function(ctypes.byref(count))
        print('Native xiGetNumberDevices:', status, 'devices:', count.value)
        return int(status != 0)
    try:
        sdk = load_xiapi()
        print('xiAPI module:', sdk.__file__)
        print('Devices:', XimeaCamera(sdk).discover())
        return 0
    except Exception as error:
        print('Discovery failed:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
