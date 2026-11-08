"""Find the unmodified xiAPI Python package shipped by XIMEA's SDK."""

import importlib
import os
from pathlib import Path
import sys

from .config import ROOT

_DLL_HANDLES = []


def configured_roots():
    roots = []
    for name in ("XIMEA_SDK_ROOT", "XI_API_DIR"):
        if os.environ.get(name):
            roots.append(Path(os.environ[name]).expanduser())
    marker = ROOT / "state" / "ximea-sdk-path.txt"
    if marker.exists():
        roots.append(Path(marker.read_text(encoding="utf-8").strip()))
    if os.name == "nt":
        roots.extend([Path("C:/XIMEA"), Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "XIMEA"])
    else:
        roots.append(Path("/opt/XIMEA"))
    return list(dict.fromkeys(path.resolve() for path in roots))


def python_package_parents(root):
    # SDK versions use API or api; a direct path to ximea or its parent is valid.
    candidates = [root.parent if root.name.lower() == "ximea" and (root / "xiapi.py").exists() else root]
    for api in ("API", "api", ""):
        for suffix in ("Python/v3", "Python", "python/v3", "python"):
            candidates.append(root / api / suffix)
    return [path for path in candidates if (path / "ximea/xiapi.py").is_file()]


def prepare_sdk_paths():
    roots = configured_roots()
    for root in roots:
        for parent in python_package_parents(root):
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
        if os.name == "nt" and hasattr(os, "add_dll_directory"):
            for path in (root / "API/x64", root / "API/X64", root / "API", root / "api/X64", root):
                if path.is_dir():
                    _DLL_HANDLES.append(os.add_dll_directory(str(path)))
    return roots


def load_xiapi():
    roots = prepare_sdk_paths()
    try:
        return importlib.import_module("ximea.xiapi")
    except (ImportError, OSError) as error:
        locations = ", ".join(map(str, roots))
        raise RuntimeError(
            "Не удалось загрузить официальный xiAPI Python / native SDK XIMEA. "
            "Установите XIMEA Software Package с xiAPI Python и драйвером USB3, "
            "затем выполните scripts/configure_ximea_sdk.py --sdk-root <папка SDK>. "
            "Для проверки без оборудования используйте --demo. "
            f"Проверены: {locations}. Причина: {error}"
        ) from error
