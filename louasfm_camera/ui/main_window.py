"""Qt composition and user actions; camera I/O belongs to AcquisitionService."""
import copy
from datetime import datetime
import logging

from PySide6.QtCore import QObject, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                              QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                              QPushButton, QScrollArea, QSpinBox, QSplitter, QTabWidget,
                              QTextEdit, QVBoxLayout, QWidget)

from ..config import ROOT
from ..services.acquisition import AcquisitionService
from ..services.beaglebone import BoardClient
from .camera_panel import CameraPanel, ForceIPDialog
from .image_view import ImageView
from .pulse_view import PulseView

log = logging.getLogger(__name__)


class BoardSignals(QObject):
    message = Signal(str, object)
    status = Signal(str)
    error = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, store, config):
        super().__init__()
        self.store = store
        self.config = copy.deepcopy(config)
        self.state = "disconnected"
        self.closing = False
        self.last_frame = None
        self.latest_path = ""
        self.setWindowTitle("LOUASFM · Basler acA2500-14gm")
        self.resize(1400, 950)
        self.service = AcquisitionService(config["backend"], self)
        self.board_signals = BoardSignals(self)
        self.board = BoardClient(self.board_signals.message.emit, self.board_signals.status.emit,
                                 self.board_signals.error.emit)
        self.service.context_provider = self.board.snapshot
        central = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(central)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.camera = CameraPanel(config)
        left_layout.addWidget(self.camera)
        self._build_capture(left_layout)
        left_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left)
        scroll.setMinimumWidth(390)
        central.addWidget(scroll)
        self.tabs = QTabWidget()
        self.image_view = ImageView()
        self.pulse_view = PulseView()
        self.tabs.addTab(self.image_view, "Изображение / ROI")
        self._build_board()
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.document().setMaximumBlockCount(500)
        self.tabs.addTab(self.log_view, "Журнал")
        central.addWidget(self.tabs)
        central.setSizes([430, 970])
        self.save_status = QLabel(f"Настройки: {store.path}")
        self.statusBar().addPermanentWidget(self.save_status)
        toolbar = self.addToolBar("Захват")
        toolbar.setMovable(False)
        self.start_action = toolbar.addAction("Запуск", self.start_capture)
        self.stop_action = toolbar.addAction("Стоп", lambda: self.issue("stop"))
        toolbar.addSeparator()
        self.snap_action = toolbar.addAction("Снять и сохранить", lambda: self.issue("snap", output=self.output()))
        self.save_action = toolbar.addAction("Сохранить последний кадр", lambda: self.issue("save_current", output=self.output()))
        help_menu = self.menuBar().addMenu("Справка")
        help_menu.addAction("Инструкция (рус.)", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT/'README.md'))))
        help_menu.addAction("Особенности камеры", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT/'docs/CAMERA.md'))))
        help_menu.addAction("Официальная документация Basler", lambda: QDesktopServices.openUrl(QUrl("https://docs.baslerweb.com/aca2500-14gm")))
        self._connect_signals()
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.update_state("disconnected")
        self.message("Выберите драйвер. Для проверки без оборудования используйте демонстрационную камеру.")

    def _build_capture(self, layout):
        group = QGroupBox("Захват и сохранение")
        form = QFormLayout(group)
        self.output_directory = QLineEdit(self.config["recording"]["directory"])
        browse = QPushButton("…")
        browse.clicked.connect(self.choose_directory)
        directory_row = QHBoxLayout()
        directory_row.addWidget(self.output_directory)
        directory_row.addWidget(browse)
        form.addRow("Каталог", directory_row)
        self.prefix = QLineEdit(self.config["recording"]["prefix"])
        self.file_format = QComboBox()
        self.file_format.addItems(["TIFF", "PNG"])
        self.file_format.setCurrentText(self.config["recording"]["format"])
        form.addRow("Префикс", self.prefix)
        form.addRow("Без потери данных", self.file_format)
        self.record = QCheckBox("Сохранять каждый полученный кадр")
        form.addRow(self.record)
        self.start_button = QPushButton("Запуск захвата")
        self.stop_button = QPushButton("Стоп")
        row = QHBoxLayout()
        row.addWidget(self.start_button)
        row.addWidget(self.stop_button)
        form.addRow(row)
        self.snap_button = QPushButton("Снять и сохранить")
        self.save_button = QPushButton("Сохранить последний полученный кадр")
        self.simulate_button = QPushButton("Демо: внешний импульс")
        form.addRow(self.snap_button)
        form.addRow(self.save_button)
        form.addRow(self.simulate_button)
        self.capture_status = QLabel("Отключено")
        self.capture_status.setWordWrap(True)
        form.addRow(self.capture_status)
        self.count_status = QLabel("Получено: 0 · Сохранено: 0")
        form.addRow(self.count_status)
        layout.addWidget(group)

    def _build_board(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        self.board_host = QLineEdit(self.config["beaglebone"]["host"])
        self.board_port = QSpinBox()
        self.board_port.setRange(1, 65535)
        self.board_port.setValue(self.config["beaglebone"]["port"])
        self.board_channel = QComboBox()
        self.board_channel.addItems([f"D{i}" for i in range(19)] + [f"S{i}" for i in range(8)])
        self.board_channel.setCurrentText(self.config["beaglebone"]["channel"])
        self.board_connect = QPushButton("Подключить BB")
        self.board_disconnect = QPushButton("Отключить BB")
        for label, widget in (("IP BB", self.board_host), ("UDP", self.board_port), ("Канал камеры", self.board_channel)):
            row.addWidget(QLabel(label))
            row.addWidget(widget)
        row.addWidget(self.board_connect)
        row.addWidget(self.board_disconnect)
        layout.addLayout(row)
        self.board_status = QLabel("BeagleBone отключён · Web: 8081, UDP: 9998")
        self.board_status.setWordWrap(True)
        layout.addWidget(self.board_status)
        self.board_counts = QLabel("Наблюдено начал/концов циклов: 0 / 0")
        layout.addWidget(self.board_counts)
        layout.addWidget(self.pulse_view)
        self.tabs.addTab(page, "Схема BeagleBone")

    def _connect_signals(self):
        self.camera.changed.connect(self.persist)
        for box in (self.output_directory, self.prefix, self.board_host):
            box.editingFinished.connect(self.persist)
        self.board_port.editingFinished.connect(self.persist)
        self.file_format.currentTextChanged.connect(self.persist)
        self.board_channel.currentTextChanged.connect(self.persist)
        self.camera.search.clicked.connect(lambda: self.issue("discover", backend=self.camera.backend.currentData()))
        self.camera.connect_button.clicked.connect(self.connect_camera)
        self.camera.disconnect_button.clicked.connect(lambda: self.issue("disconnect"))
        self.camera.apply.clicked.connect(self.apply_camera)
        self.camera.force_ip.clicked.connect(self.force_ip)
        self.start_button.clicked.connect(self.start_capture)
        self.stop_button.clicked.connect(lambda: self.issue("stop"))
        self.snap_button.clicked.connect(lambda: self.issue("snap", output=self.output()))
        self.save_button.clicked.connect(lambda: self.issue("save_current", output=self.output()))
        self.simulate_button.clicked.connect(lambda: self.issue("simulate_external"))
        self.board_connect.clicked.connect(self.connect_board)
        self.board_disconnect.clicked.connect(self.disconnect_board)
        self.service.devices_found.connect(self.devices_found)
        self.service.connected.connect(self.camera_connected)
        self.service.settings_applied.connect(self.settings_applied)
        self.service.state_changed.connect(self.update_state)
        self.service.error.connect(self.show_error)
        self.service.notice.connect(self.message)
        self.service.saved.connect(self.image_saved)
        self.service.closed.connect(self.finish_close)
        self.board_signals.message.connect(self.board_message)
        self.board_signals.status.connect(self.board_status.setText)
        self.board_signals.error.connect(self.show_error)

    def output(self):
        return {"directory": self.output_directory.text().strip(), "prefix": self.prefix.text(),
                "image_format": self.file_format.currentText()}

    def persist(self, *args):
        if self.closing:
            return False
        try:
            settings = self.camera.settings()
            data = copy.deepcopy(self.config)
            data.update(backend=self.camera.backend.currentData(), camera_serial=self.camera.serial.text().strip(),
                        camera_ip=self.camera.ip.text().strip(), camera=settings.__dict__.copy())
            output = self.output()
            if not output["directory"]:
                raise ValueError("Выберите каталог снимков")
            data["recording"] = {"directory": output["directory"], "prefix": output["prefix"], "format": output["image_format"]}
            data["beaglebone"] = {"host": self.board_host.text().strip(), "port": self.board_port.value(),
                                 "channel": self.board_channel.currentText()}
            self.store.save(data)
            self.config = data
            self.save_status.setText("Настройки сохранены")
            self.pulse_view.channel = self.board_channel.currentText()
            self.pulse_view.activation = settings.trigger_activation
            self.pulse_view.redraw()
            return True
        except (OSError, ValueError, TypeError) as error:
            self.save_status.setText("ОШИБКА сохранения настроек")
            self.show_error(str(error))
            return False

    def issue(self, task, **kwargs):
        try:
            self.service.command(task, **kwargs)
        except (ValueError, RuntimeError) as error:
            self.show_error(str(error))

    def connect_camera(self):
        if self.persist():
            self.camera.connect_button.setEnabled(False)
            self.issue("connect", backend=self.camera.backend.currentData(), serial=self.camera.serial.text().strip(),
                       ip=self.camera.ip.text().strip(), settings=self.camera.settings())

    def apply_camera(self):
        if self.persist():
            self.issue("apply", settings=self.camera.settings())

    def start_capture(self):
        if self.persist():
            self.issue("start", settings=self.camera.settings(), record=self.record.isChecked(), output=self.output())

    def devices_found(self, devices):
        self.camera.show_devices(devices)
        self.message(f"Найдено камер: {len(devices)}")

    def camera_connected(self, info):
        self.camera.description.setText(f"{info['model']} / SN {info['serial']} / {info.get('ip', '')}")
        self.message(f"Камера подключена: {info}")

    def settings_applied(self, settings, caps):
        self.camera.capabilities(caps)
        self.camera.set_settings(settings)
        self.persist()
        self.message(f"Применено: {settings}")

    def update_state(self, state):
        self.state = state
        self.camera.set_state(state)
        idle = state == "idle"
        streaming = state in ("streaming", "recording", "snapshot")
        self.start_button.setEnabled(idle)
        self.start_action.setEnabled(idle)
        self.stop_button.setEnabled(streaming)
        self.stop_action.setEnabled(streaming)
        self.snap_button.setEnabled(state != "disconnected" and state != "snapshot")
        self.snap_action.setEnabled(self.snap_button.isEnabled())
        self.save_button.setEnabled(self.service.preview() is not None)
        self.save_action.setEnabled(self.save_button.isEnabled())
        self.record.setEnabled(idle or state == "disconnected")
        for box in (self.output_directory, self.prefix, self.file_format):
            box.setEnabled(not streaming)
        self.simulate_button.setVisible(self.camera.backend.currentData() == "simulated")
        self.simulate_button.setEnabled(streaming)
        labels = {"disconnected": "Камера отключена", "idle": "Готово. Захват остановлен",
                  "streaming": "Захват без автоматической записи", "recording": "Запись всех полученных кадров",
                  "snapshot": "Ожидание одиночного программного снимка"}
        self.capture_status.setText(labels.get(state, state))

    def refresh(self):
        frame = self.service.preview()
        if frame is not None and frame is not self.last_frame:
            self.last_frame = frame
            self.image_view.show_frame(frame)
            self.save_button.setEnabled(not self.closing)
            self.save_action.setEnabled(not self.closing)
        received, saved = self.service.counts()
        self.count_status.setText(f"Получено: {received} · Сохранено: {saved} · В очереди записи: {self.service.writer.queue.qsize()}")

    def image_saved(self, path):
        self.latest_path = path
        self.statusBar().showMessage(f"Сохранено: {path}", 4000)

    def choose_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "Каталог снимков", self.output_directory.text())
        if folder:
            self.output_directory.setText(folder)
            self.persist()

    def force_ip(self):
        dialog = ForceIPDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.issue("force_ip", **dialog.values())

    def connect_board(self):
        if not self.persist():
            return
        try:
            self.board.connect(self.board_host.text(), self.board_port.value())
        except (OSError, RuntimeError, ValueError) as error:
            self.show_error(str(error))

    def disconnect_board(self):
        try:
            self.board.close()
        except RuntimeError as error:
            self.show_error(str(error))

    def board_message(self, task, data):
        state = self.board.snapshot()
        if task in ("Pulses", "Channel_names"):
            self.pulse_view.set_scheme(state["pulses"], state["channel_names"])
        if task in ("First_edge", "Cycle_finished"):
            self.board_counts.setText(f"Наблюдено начал/концов циклов: {state['first_edges_observed']} / {state['cycles_observed']} · "
                                      f"Последний bad_cycle: {state['bad_cycle_last_reported']}")

    def message(self, text):
        self.log_view.append(f"{datetime.now():%H:%M:%S} · {text}")
        self.statusBar().showMessage(text, 8000)

    def show_error(self, text):
        self.message(f"ОШИБКА: {text}")
        self.camera.connect_button.setEnabled(self.state == "disconnected")
        self.capture_status.setText(f"ОШИБКА: {text}")
        self.tabs.setTabText(2, "Журнал ⚠")

    def closeEvent(self, event):
        if self.closing and not self.service.thread.is_alive():
            event.accept()
            return
        event.ignore()
        if self.closing:
            return
        self.persist()
        self.closing = True
        self.timer.stop()
        self.centralWidget().setEnabled(False)
        self.message("Остановка камеры и завершение записи принятых кадров…")
        self.disconnect_board()
        self.service.request_close()

    def finish_close(self):
        # Signal is emitted just before the worker returns; don't race closeEvent.
        if self.service.wait_closed(0.2):
            self.close()
        else:
            QTimer.singleShot(50, self.finish_close)
