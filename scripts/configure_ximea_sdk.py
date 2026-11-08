"""Register the unmodified official SDK's Python package for this project only."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from louasfm_camera.config import atomic_bytes  # noqa: E402
from louasfm_camera.sdk_runtime import load_xiapi, python_package_parents  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-root', type=Path, required=True,
                        help='SDK installation root, or API/Python/v3 containing the ximea directory')
    parser.add_argument('--check', action='store_true', help='Also import xiAPI/native libraries and enumerate devices')
    args = parser.parse_args()
    root = args.sdk_root.expanduser().resolve()
    parents = python_package_parents(root)
    if not parents:
        parser.error('No ximea/xiapi.py found under this root. Select xiAPI Python in the SDK installer.')
    marker = ROOT/'state/ximea-sdk-path.txt'
    atomic_bytes(marker, (str(root)+'\n').encode('utf-8'))
    print('Project-local SDK setting:', marker)
    print('Python package:', parents[0]/'ximea')
    print('SDK sources and system environment were not modified.')
    if args.check:
        sdk = load_xiapi()
        print('xiAPI loaded:', sdk.__file__)
        print('Connected devices:', sdk.Camera().get_number_devices())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
