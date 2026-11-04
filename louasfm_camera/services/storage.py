"""Ordered bounded writer: raw pixels plus JSON sidecar, never silent loss."""
from concurrent.futures import Future
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import re
import threading
import uuid

import numpy as np
from PIL import Image


class ImageWriter:
    def __init__(self, max_pending=8):
        self.queue = queue.Queue(maxsize=max_pending)
        self.closed = False
        self._lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name="image-writer", daemon=True)
        self.thread.start()

    def submit(self, frame, directory, prefix="image", image_format="TIFF", context=None):
        future = Future()
        if frame.pixels.ndim != 2 or frame.pixels.dtype not in (np.dtype("uint8"), np.dtype("uint16")):
            raise ValueError("Для сохранения нужен монохромный uint8/uint16 кадр")
        if image_format not in ("TIFF", "PNG"):
            raise ValueError("Поддерживаются TIFF и PNG")
        # Immutable frame ownership: the SDK backend copies the released buffer.
        record = (future, frame, Path(directory).expanduser(), prefix, image_format, context or {})
        with self._lock:
            if self.closed:
                raise RuntimeError("Запись уже закрыта")
            try:
                self.queue.put_nowait(record)
            except queue.Full as error:
                raise RuntimeError("Диск не успевает: очередь сохранения заполнена. Захват остановлен.") from error
        return future

    def _run(self):
        while True:
            record = self.queue.get()
            try:
                if record is None:
                    return
                future, frame, directory, prefix, image_format, context = record
                try:
                    future.set_result(self._save(frame, directory, prefix, image_format, context))
                except Exception as error:
                    future.set_exception(error)
            finally:
                self.queue.task_done()

    @staticmethod
    def _save(frame, directory, prefix, image_format, context):
        directory.mkdir(parents=True, exist_ok=True)
        prefix = re.sub(r'[^\w.-]+', '_', prefix, flags=re.UNICODE).strip(' .')[:80] or "image"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        stem = f"{prefix}_{stamp}_{frame.frame_id}_{uuid.uuid4().hex[:8]}"
        extension = ".tiff" if image_format == "TIFF" else ".png"
        target = directory / (stem + extension)
        temporary = directory / ("." + stem + ".part")
        sidecar = target.with_suffix(".json")
        sidecar_temporary = directory / ("." + stem + ".json.part")
        metadata = {"schema_version": 1, "image_file": target.name,
                    "frame": frame.description(), "context": context,
                    "association": "UDP context is approximate; not a guaranteed trigger/cycle match"}
        try:
            with temporary.open("xb") as output:
                Image.fromarray(frame.pixels).save(output, format=image_format)
                output.flush()
                os.fsync(output.fileno())
            with sidecar_temporary.open("x", encoding="utf-8") as output:
                json.dump(metadata, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
            os.replace(sidecar_temporary, sidecar)
        finally:
            temporary.unlink(missing_ok=True)
            sidecar_temporary.unlink(missing_ok=True)
        return str(target)

    def close(self):
        with self._lock:
            if self.closed:
                return
            self.closed = True
        self.queue.put(None)  # Finish accepted records before returning.
        self.thread.join()
