"""Build source and optional offline Windows dependency ZIPs without user data."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-wheels', action='store_true', help='Create a separate Windows x64/Python 3.11 wheels ZIP')
    args = parser.parse_args()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT):
        raise SystemExit('Commit source changes before building a release')
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    files = subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    destination = ROOT/'artifacts'
    destination.mkdir(exist_ok=True)
    name = ROOT.name
    source_zip = destination/f'{name}-{revision[:7]}.zip'
    with zipfile.ZipFile(source_zip,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for relative in files:
            if relative:
                archive.write(ROOT/relative,f'{name}/{relative}')
        archive.writestr(f'{name}/RELEASE.json',json.dumps({'commit':revision,'runtime':'Python 3.11 x64','hardware_validation':'pending Windows and physical Basler camera'},indent=2)+'\n')
    archives = [source_zip]
    if args.with_wheels:
        wheel_dir = ROOT/'vendor/wheels/windows'
        wheels = sorted(wheel_dir.glob('*.whl'))
        if not wheels:
            raise SystemExit('No Windows wheels downloaded')
        wheel_zip = destination/'windows-python311-wheels.zip'
        manifest = []
        with zipfile.ZipFile(wheel_zip,'w',compression=zipfile.ZIP_STORED) as archive:
            for path in wheels:
                archive.write(path,f'{name}/vendor/wheels/windows/{path.name}')
                manifest.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
            archive.writestr(f'{name}/vendor/wheels/windows/manifest.json',json.dumps(manifest,indent=2)+'\n')
        archives.append(wheel_zip)
    for path in archives:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_suffix(path.suffix+'.sha256').write_text(checksum+'  '+path.name+'\n')
        print(f'{path}: {path.stat().st_size:,} bytes, SHA256 {checksum}')


if __name__ == '__main__':
    main()
