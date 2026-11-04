"""Download a small, attributed offline reference set from Basler's own sites."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "acA2500-14gm.html": "https://docs.baslerweb.com/aca2500-14gm",
    "triggered-image-acquisition.html": "https://docs.baslerweb.com/triggered-image-acquisition",
    "electronic-shutter-types.html": "https://docs.baslerweb.com/electronic-shutter-types.html",
    "exposure-time.html": "https://docs.baslerweb.com/exposure-time",
    "gain.html": "https://docs.baslerweb.com/gain",
    "network-configuration.html": "https://docs.baslerweb.com/network-configuration-(gige-cameras)",
    "pypylon-installation.html": "https://docs.baslerweb.com/pypylon-installation-and-environment-setup",
}
FILES = {
    "pypylon-LICENSE.txt": "https://raw.githubusercontent.com/basler/pypylon/master/LICENSE",
}
OPTIONAL_LEGACY_PDFS = {
    "acA2500-14gm-EMVA1288.pdf": "https://www2.baslerweb.com/media/downloads/documents/emva_data/BD00056301_Basler_acA2500-14gm_EMVA_Standard_1288.pdf",
    "pylon-Windows-installation-legacy.pdf": "https://www2.baslerweb.com/media/downloads/documents/users_manuals/AW00061112000_Install_and_Setup_Guide_pylon_Windows.pdf",
}


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "LOUASFM-documentation-downloader/1.0"}), timeout=40) as response:
        return response.read(), response.headers.get_content_type()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT/"docs/manufacturer")
    parser.add_argument("--with-legacy-pdfs", action="store_true", help="Also try legacy www2.baslerweb.com PDF links")
    args = parser.parse_args()
    destination = args.destination
    destination.mkdir(parents=True, exist_ok=True)
    downloaded = []
    failures = []
    timestamp = datetime.now(timezone.utc).isoformat()
    # Pin the guide to an upstream commit so the local snapshot is reproducible.
    commit_data, _ = fetch("https://api.github.com/repos/basler/pypylon/commits/master")
    revision = json.loads(commit_data)["sha"]
    listing, _ = fetch("https://api.github.com/repos/basler/pypylon/contents/docs/programmers_guide?ref="+revision)
    files = dict(FILES)
    if args.with_legacy_pdfs:
        files.update(OPTIONAL_LEGACY_PDFS)
    for item in json.loads(listing):
        if item["name"].endswith(".md"):
            files["programmers_guide/"+item["name"]] = item["download_url"]
    files["pypylon-LICENSE.txt"] = f"https://raw.githubusercontent.com/basler/pypylon/{revision}/LICENSE"
    for name, url in {**PAGES, **files}.items():
        try:
            data, content_type = fetch(url)
            if name.endswith(".pdf") and not data.startswith(b"%PDF"):
                raise ValueError("Server did not return a PDF")
            if name in PAGES:
                text = data.decode("utf-8")
                match = re.search(r"<article\b[^>]*>([\s\S]*?)</article>", text)
                if match is None:
                    raise ValueError("Article section not found")
                body = match.group(1)
                # Keep article links absolute and embed article illustrations for offline reading.
                def link(match):
                    attribute, value = match.groups()
                    absolute = urljoin(url, html.unescape(value))
                    if attribute == "src" and not absolute.startswith("data:"):
                        try:
                            picture, mime = fetch(absolute)
                            if mime.startswith("image/") and len(picture)<2_000_000:
                                absolute = "data:"+mime+";base64,"+base64.b64encode(picture).decode()
                        except Exception:
                            pass
                    return attribute+'="'+html.escape(absolute, quote=True)+'"'
                body = re.sub(r'(href|src)="([^"]*)"', link, body)
                body = re.sub(r'<script\b[^>]*>[\s\S]*?</script>', '', body)
                text = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Basler reference</title>'
                        '<style>body{max-width:1100px;margin:2em auto;font:16px sans-serif;line-height:1.5}'
                        'table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:6px}'
                        'img{max-width:100%}pre{overflow:auto;background:#eee;padding:1em}</style>'
                        f'<p>© Basler AG. Offline article snapshot {timestamp}. '
                        f'<a href="{html.escape(url)}">Original source</a>. Links may require internet.</p>'
                        +body+'</html>')
                data = text.encode("utf-8")
            target = destination/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            downloaded.append({"file":name,"source":url,"sha256":hashlib.sha256(data).hexdigest(),
                               "bytes":len(data),"downloaded_utc":timestamp})
            print("Saved",name,len(data),flush=True)
        except Exception as error:
            failures.append({"file":name,"source":url,"error":str(error)})
            print("FAILED",name,error,flush=True)
    manifest = {"upstream_pypylon_commit":revision,"files":downloaded,"failures":failures,
                "optional_legacy_pdf_links":OPTIONAL_LEGACY_PDFS}
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
