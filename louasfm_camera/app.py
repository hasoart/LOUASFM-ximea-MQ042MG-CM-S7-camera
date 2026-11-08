"""Cross-platform application entry point; no camera is opened on import."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sys

from .config import ConfigStore, DEFAULT_PATH


def main(argv=None):
    parser = argparse.ArgumentParser(description="LOUASFM XIMEA MQ042MG-CM-S7 camera")
    parser.add_argument("--demo", action="store_true", help="Демонстрация без камеры, отдельные настройки")
    parser.add_argument("--config", type=Path, help="Файл настроек JSON")
    parser.add_argument("--smoke-seconds", type=float, help="Автоматически закрыть GUI после N секунд")
    args = parser.parse_args(argv)
    path = args.config or DEFAULT_PATH.with_name("demo.json") if args.demo else args.config or DEFAULT_PATH
    store = ConfigStore(path)
    try:
        config = store.load()
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    if args.demo:
        config["backend"] = "simulated"
        config["camera_serial"] = ""
    log_dir = store.path.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), RotatingFileHandler(log_dir/"camera.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")])
    # Select PySide6 even if PyQt5 happens to be installed for the legacy program.
    os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from .ui.main_window import MainWindow
    app = QApplication(sys.argv[:1])
    app.setApplicationName("LOUASFM XIMEA Camera")
    window = MainWindow(store, config)
    signal.signal(signal.SIGINT, lambda *_: window.close())
    signal.signal(signal.SIGTERM, lambda *_: window.close())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(200)  # Allow Python to deliver process signals while Qt is idle.
    if args.smoke_seconds is not None:
        QTimer.singleShot(max(1, int(args.smoke_seconds*1000)), window.close)
    window.show()
    return app.exec()
