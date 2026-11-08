"""Build an isolated XIMEA source ZIP and optional Windows SDK/wheels bundle."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SDK_URL = "https://www.ximea.com/attachment/XIMEA_Windows_SP_Stable.exe"


def entry(path):
    return {
        "file": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-wheels", action="store_true")
    parser.add_argument(
        "--with-sdk", action="store_true", help="Include the original Windows SDK installer; never execute it"
    )
    args = parser.parse_args()
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT):
        raise SystemExit("Commit source changes before building a release")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    destination = ROOT / "artifacts"
    destination.mkdir(exist_ok=True)
    source_zip = destination / f"{ROOT.name}-{revision[:7]}.zip"
    with zipfile.ZipFile(source_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative in files:
            if relative:
                archive.write(ROOT / relative, f"{ROOT.name}/{relative}")
        archive.writestr(
            f"{ROOT.name}/RELEASE.json",
            json.dumps(
                {
                    "commit": revision,
                    "runtime": "Python 3.11 x64",
                    "camera_model": "XIMEA MQ042MG-CM-S7",
                    "sdk_reference": "Official XIMEA SDK 4.34.00",
                    "hardware_validation": "pending physical camera and Windows execution",
                },
                indent=2,
            )
            + "\n",
        )
    archives = [source_zip]
    if args.with_wheels or args.with_sdk:
        suffix = "sdk-and-wheels" if args.with_wheels and args.with_sdk else "sdk" if args.with_sdk else "wheels"
        bundle = destination / f"windows-python311-{suffix}.zip"
        paths = []
        if args.with_wheels:
            wheels = sorted((ROOT / "vendor/wheels/windows").glob("*.whl"))
            if not wheels or any("pypylon" in p.name.lower() for p in wheels):
                raise SystemExit("Expected XIMEA GUI dependencies only, without pypylon")
            paths.extend(wheels)
        if args.with_sdk:
            installer = ROOT / "vendor/sdk/XIMEA_Windows_SP_Stable.exe"
            if not installer.exists():
                raise SystemExit("Download the official SDK installer before bundling")
            with installer.open("rb") as stream:
                if stream.read(2) != b"MZ":
                    raise SystemExit("The SDK file is not a Windows executable")
            paths.append(installer)
        manifest = {"sdk_source": SDK_URL if args.with_sdk else None, "files": [entry(path) for path in paths]}
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in paths:
                archive.write(path, f"{ROOT.name}/{path.relative_to(ROOT)}")
            archive.writestr(f"{ROOT.name}/vendor/windows-bundle-manifest.json", json.dumps(manifest, indent=2) + "\n")
        archives.append(bundle)
    for path in archives:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_suffix(path.suffix + ".sha256").write_text(checksum + "  " + path.name + "\n")
        print(f"{path}: {path.stat().st_size:,} bytes, SHA256 {checksum}")


if __name__ == "__main__":
    main()
