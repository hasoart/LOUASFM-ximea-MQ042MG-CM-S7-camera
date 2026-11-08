"""Fetch an attributed offline reference set from official XIMEA pages/PDFs."""

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "MQ042MG-CM-S7.html": "https://www.ximea.com/products/usb-vision-industrial/xiq-usb3-compact-cmos-cameras/cmosis-cmv4000-spartan-7-usb3-mono-compact-camera",
    "xiAPI-Python-manual.html": "https://www.ximea.com/support/wiki/apis/XiAPI_Python_Manual",
    "xiAPI-manual.html": "https://www.ximea.com/support/wiki/apis/XiAPI_Manual",
    "trigger-and-synchronization.html": "https://www.ximea.com/support/wiki/apis/XiAPI_Camera_Trigger_and_Synchronization_Signals",
    "windows-software-package.html": "https://www.ximea.com/support/wiki/apis/XIMEA_Windows_Software_Package",
    "linux-software-package.html": "https://www.ximea.com/support/wiki/apis/XIMEA_Linux_Software_Package",
    "python-windows-installation.html": "https://www.ximea.com/support/wiki/apis/Python_inst_win",
    "python-linux-installation.html": "https://www.ximea.com/support/wiki/apis/Python_inst_linux",
    "software-downloads.html": "https://www.ximea.com/software-downloads",
}
FILES = {
    "xiq-s7-technical-manual.pdf": "https://www.ximea.com/downloads/documents-downloads/xiq-s7-usb3-vision-compact-cameras_technical-manual-dwl_manual-pdf",
}


def fetch(url):
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as response:
            return response.read()
    except Exception:
        if not shutil.which("curl"):
            raise
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "download"
            subprocess.run(
                [
                    "curl",
                    "--noproxy",
                    "*",
                    "--location",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "90",
                    "--user-agent",
                    "Mozilla/5.0",
                    "--output",
                    str(output),
                    url,
                ],
                check=True,
            )
            return output.read_bytes()


def offline_html(data, url, stamp):
    content = data.decode("utf-8")
    # Preserve the original article content/styles, but remove scripts and forms.
    content = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", content, flags=re.I)
    content = re.sub(r"<form\b[^>]*>[\s\S]*?</form>", "", content, flags=re.I)

    def link(match):
        attr, value = match.groups()
        if value.startswith(("data:", "#", "mailto:", "javascript:")):
            return match.group(0)
        return f'{attr}="{html.escape(urljoin(url, html.unescape(value)), quote=True)}"'

    content = re.sub(r'(href|src)="([^"]*)"', link, content)
    banner = (
        f'<div style="background:#edf2f7;padding:16px;color:#111;font:16px sans-serif">'
        f"© XIMEA. Offline reference snapshot {stamp}. "
        f'<a href="{html.escape(url)}">Original source</a>. External illustrations/links may require internet.</div>'
    )
    return re.sub(r"(<body\b[^>]*>)", lambda m: m.group(1) + banner, content, count=1, flags=re.I).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT / "docs/manufacturer")
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    downloaded, failures = [], []
    for name, url in {**PAGES, **FILES}.items():
        try:
            original = fetch(url)
            if name.endswith(".pdf") and not original.startswith(b"%PDF"):
                raise ValueError("Not a PDF")
            data = offline_html(original, url, stamp) if name in PAGES else original
            (args.destination / name).write_bytes(data)
            downloaded.append(
                {
                    "file": name,
                    "source": url,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                    "downloaded_utc": stamp,
                }
            )
            print("Saved", name, len(data), flush=True)
        except Exception as error:
            failures.append({"file": name, "source": url, "error": str(error)})
            print("FAILED", name, str(error), flush=True)
    license_path = args.destination / "XIMEA-SDK-LICENSE.txt"
    if license_path.exists():
        data = license_path.read_bytes()
        downloaded.append(
            {
                "file": license_path.name,
                "source": "https://www.ximea.com/attachment/Linux-SP-Stable.tgz",
                "archive_member": "package/License.txt (SDK 4.34.00)",
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "downloaded_utc": stamp,
            }
        )
    manifest = {"files": downloaded, "failures": failures}
    (args.destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
