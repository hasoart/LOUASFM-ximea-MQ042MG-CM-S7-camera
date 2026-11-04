"""Validated, atomic configuration storage, independent of the working directory."""
import copy
import json
import os
from pathlib import Path
import tempfile

from .models import CameraSettings, settings_dict

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "state" / "settings.json"
DEFAULTS = {
    "schema_version": 1,
    "backend": "basler",
    "camera_serial": "",
    "camera_ip": "",
    "camera": settings_dict(CameraSettings()),
    "recording": {"directory": str(ROOT / "captures"), "prefix": "image", "format": "TIFF"},
    "beaglebone": {"host": "192.168.1.66", "port": 9998, "channel": "D0"},
}


def _merge(default, saved):
    result = copy.deepcopy(default)
    for key, value in saved.items():
        result[key] = _merge(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict) else value
    return result


def validate_config(config):
    if config.get("schema_version") != 1:
        raise ValueError("Неподдерживаемая версия настроек")
    CameraSettings(**config["camera"]).validate()
    if config["backend"] not in ("basler", "simulated"):
        raise ValueError("Неизвестный драйвер камеры")
    if config["recording"]["format"] not in ("TIFF", "PNG"):
        raise ValueError("Формат сохранения: TIFF или PNG")
    if not isinstance(config["beaglebone"]["port"], int) or not 1 <= config["beaglebone"]["port"] <= 65535:
        raise ValueError("Некорректный UDP порт BeagleBone")
    if not str(config["beaglebone"]["host"]).strip():
        raise ValueError("Укажите адрес BeagleBone")
    return config


def atomic_bytes(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ConfigStore:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path).expanduser().resolve()

    def load(self):
        if not self.path.exists():
            return copy.deepcopy(DEFAULTS)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Ожидался объект JSON")
            return validate_config(_merge(DEFAULTS, data))
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError(f"Ошибка настроек {self.path}: {error}. Исходный файл сохранён.") from error

    def save(self, config):
        validate_config(config)
        data = (json.dumps(config, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        if self.path.exists():
            atomic_bytes(self.path.with_suffix(self.path.suffix + ".bak"), self.path.read_bytes())
        atomic_bytes(self.path, data)
