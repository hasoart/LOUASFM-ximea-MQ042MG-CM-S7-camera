"""One camera-owning worker, bounded latest preview and an ordered disk writer."""
from dataclasses import replace
import copy
import logging
import queue
import threading
import time

from PySide6.QtCore import QObject, Signal

from ..cameras.base import create_camera
from ..models import CameraSettings, settings_dict
from .storage import ImageWriter

log = logging.getLogger(__name__)


class CommandRejected(RuntimeError):
    """A rejected user action has not changed the current camera configuration."""


class AcquisitionService(QObject):
    devices_found = Signal(object)
    connected = Signal(object)
    settings_applied = Signal(object, object)
    state_changed = Signal(str)
    notice = Signal(str)
    error = Signal(str)
    saved = Signal(str)
    closed = Signal()

    def __init__(self, backend="basler", parent=None):
        super().__init__(parent)
        self.backend = backend
        self.commands = queue.Queue(maxsize=32)
        self.camera = None
        self.settings = CameraSettings()
        self.actual_settings = self.settings
        self.streaming = False
        self.recording = False
        self.single = False
        self.pending_save = False
        self.pending_since = 0.0
        self.output = {}
        self.latest = None
        self.received = 0
        self.saved_count = 0
        self.lock = threading.Lock()
        self.context_provider = lambda: {}
        self.writer = ImageWriter()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="camera-owner", daemon=True)
        self.thread.start()

    def command(self, task, **kwargs):
        if self.stop_event.is_set():
            raise RuntimeError("Программа завершает работу")
        try:
            self.commands.put_nowait((task, kwargs))
        except queue.Full as error:
            raise RuntimeError("Очередь команд камеры заполнена") from error

    def preview(self):
        with self.lock:
            return self.latest

    def counts(self):
        with self.lock:
            return self.received, self.saved_count

    def _save(self, frame, output):
        future = self.writer.submit(frame, **output, context=copy.deepcopy(self.context_provider()))
        future.add_done_callback(self._save_done)

    def _save_done(self, future):
        try:
            path = future.result()
        except Exception as error:
            log.exception("Image write failed")
            self.error.emit(f"Ошибка сохранения: {error}")
            self.stop_event_on_disk_error.set()
        else:
            with self.lock:
                self.saved_count += 1
            self.saved.emit(path)

    def _stop(self):
        was_single = self.single
        self.streaming = self.recording = self.single = self.pending_save = False
        if self.camera is not None:
            self.camera.stop()
        if was_single:
            self.actual_settings, caps = self.camera.configure(self.settings)
            self.settings_applied.emit(self.actual_settings, caps)
        self.state_changed.emit("idle" if self.camera else "disconnected")

    def _handle(self, task, data):
        if task == "discover":
            if self.camera is not None:
                raise CommandRejected("Сначала отключите камеру перед поиском")
            driver = create_camera(data.get("backend", self.backend))
            try:
                self.devices_found.emit(driver.discover())
            finally:
                driver.close()
        elif task == "connect":
            if self.camera is not None:
                raise CommandRejected("Камера уже подключена")
            self.backend = data["backend"]
            driver = create_camera(self.backend)
            try:
                info = driver.open(data.get("serial", ""), data.get("ip", ""))
                settings, caps = driver.configure(data["settings"])
            except Exception:
                driver.close()
                raise
            self.camera = driver
            self.settings = self.actual_settings = settings
            with self.lock:
                self.latest = None
                self.received = self.saved_count = 0
            self.connected.emit(info)
            self.settings_applied.emit(settings, caps)
            self.state_changed.emit("idle")
        elif task == "disconnect":
            self._stop()
            if self.camera is not None:
                self.camera.close()
                self.camera = None
            self.state_changed.emit("disconnected")
        elif task == "apply":
            if self.camera is None or self.streaming:
                raise CommandRejected("Настройки применяются при остановленном захвате")
            self.settings, caps = self.camera.configure(data["settings"])
            self.actual_settings = self.settings
            self.settings_applied.emit(self.settings, caps)
        elif task == "start":
            if self.camera is None or self.streaming:
                raise CommandRejected("Подключите камеру и остановите предыдущий захват")
            self.settings, caps = self.camera.configure(data["settings"])
            self.actual_settings = self.settings
            self.settings_applied.emit(self.settings, caps)
            self.output = data["output"]
            self.recording = data.get("record", False)
            self.camera.start()
            self.streaming = True
            self.state_changed.emit("recording" if self.recording else "streaming")
        elif task == "stop":
            self._stop()
        elif task == "save_current":
            frame = self.preview()
            if frame is None:
                raise CommandRejected("Нет кадра для сохранения")
            self._save(frame, data["output"])
        elif task == "snap":
            if self.camera is None:
                raise CommandRejected("Подключите камеру")
            if self.pending_save:
                raise CommandRejected("Уже ожидается снимок")
            if not self.streaming:
                self.actual_settings, _ = self.camera.configure(replace(self.settings, trigger_mode="software"))
                self.camera.start()
                self.streaming = self.single = True
                self.state_changed.emit("snapshot")
            if self.actual_settings.trigger_mode == "software":
                self.camera.trigger()
            elif self.actual_settings.trigger_mode == "external":
                self.notice.emit("Ожидается следующий физический триггер; режим камеры не изменён")
            self.pending_save = True
            self.pending_since = time.monotonic()
            self.output = data["output"]
        elif task == "simulate_external":
            if self.backend != "simulated" or self.camera is None:
                raise CommandRejected("Доступно только для демонстрационной камеры")
            self.camera.simulate_external()
        elif task == "force_ip":
            if self.camera is not None:
                raise CommandRejected("Сначала отключите камеру")
            driver = create_camera("basler")
            try:
                self.notice.emit(driver.force_ip(**data))
            finally:
                driver.close()
        else:
            raise ValueError(f"Неизвестная команда: {task}")

    def _run(self):
        self.stop_event_on_disk_error = threading.Event()
        try:
            while not self.stop_event.is_set():
                if self.stop_event_on_disk_error.is_set():
                    self.stop_event_on_disk_error.clear()
                    try:
                        self._stop()
                    except Exception:
                        log.exception("Could not stop after a disk error")
                try:
                    task, data = self.commands.get(timeout=0.001 if self.streaming else 0.1)
                except queue.Empty:
                    pass
                else:
                    try:
                        self._handle(task, data)
                    except Exception as error:
                        log.exception("Camera command %s failed", task)
                        # A failed configuration may leave partially changed hardware.
                        # Close it rather than advertise a valid prior configuration.
                        if (not isinstance(error, CommandRejected)
                                and task in ("apply", "start", "snap", "stop", "disconnect")
                                and self.camera is not None):
                            try:
                                self.camera.close()
                            except Exception:
                                log.exception("Camera cleanup after command failure")
                            self.camera = None
                            self.streaming = self.recording = self.single = self.pending_save = False
                            self.state_changed.emit("disconnected")
                        self.error.emit(str(error))
                    finally:
                        self.commands.task_done()
                if self.streaming and not self.stop_event.is_set():
                    try:
                        frame = self.camera.read(100)
                        if frame is not None:
                            frame.metadata["settings"] = settings_dict(self.actual_settings)
                            with self.lock:
                                self.latest = frame
                                self.received += 1
                            if self.recording or self.pending_save:
                                self._save(frame, self.output)
                            self.pending_save = False
                            if self.single:
                                self._stop()
                        elif self.pending_save and self.actual_settings.trigger_mode != "external" and time.monotonic()-self.pending_since > max(5, self.actual_settings.exposure_us/1e6 + 3):
                            raise TimeoutError("Не получен снимок после программного триггера")
                    except Exception as error:
                        log.exception("Acquisition stopped after an error")
                        try:
                            self._stop()
                        except Exception:
                            log.exception("Camera stop failed")
                            try:
                                self.camera.close()
                            except Exception:
                                log.exception("Camera close failed after acquisition error")
                            self.camera = None
                            self.state_changed.emit("disconnected")
                        self.error.emit(str(error))
        finally:
            try:
                if self.camera is not None:
                    self.camera.close()
            except Exception as error:
                log.exception("Camera close failed")
                self.error.emit(str(error))
            finally:
                self.writer.close()
                self.closed.emit()

    def request_close(self):
        self.stop_event.set()

    def wait_closed(self, timeout=10):
        self.thread.join(timeout)
        return not self.thread.is_alive()
