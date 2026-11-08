"""Camera widgets only; device operations are requested by the main window."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from ..models import CameraSettings, settings_dict


def integer(maximum=65536, minimum=0):
    box = QSpinBox()
    box.setRange(minimum, maximum)
    return box


def decimal(maximum, decimals=3):
    box = QDoubleSpinBox()
    box.setRange(0, maximum)
    box.setDecimals(decimals)
    box.setKeyboardTracking(False)
    return box


class CameraPanel(QWidget):
    changed = Signal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.updating = False
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.backend = QComboBox()
        self.backend.addItem("XIMEA / xiAPI (USB3)", "ximea")
        self.backend.addItem("Демонстрация без камеры", "simulated")
        self.backend.setCurrentIndex(self.backend.findData(config["backend"]))
        form.addRow("Драйвер", self.backend)
        self.devices = QComboBox()
        form.addRow("Найденные камеры", self.devices)
        self.serial = QLineEdit(config["camera_serial"])
        self.serial.setPlaceholderText("Пусто: единственная найденная камера")
        form.addRow("Серийный номер", self.serial)
        self.search = QPushButton("Найти")
        self.connect_button = QPushButton("Подключить")
        self.disconnect_button = QPushButton("Отключить")
        buttons = QHBoxLayout()
        for button in (self.search, self.connect_button, self.disconnect_button):
            buttons.addWidget(button)
        layout.addLayout(form)
        layout.addLayout(buttons)
        self.description = QLabel("Камера отключена")
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.fields = {}
        settings_form = QFormLayout()
        self.fields["exposure_us"] = decimal(1e8)
        self.fields["exposure_us"].setMinimum(0.001)
        self.fields["gain"] = decimal(10000)
        self.fields["gain"].setMinimum(-1)
        self.fields["gain"].setSpecialValueText("Минимум камеры")
        self.gain_label = QLabel("Усиление (единицы камеры)")
        self.fields["binning"] = integer(4, 1)
        for name in ("width", "height", "offset_x", "offset_y"):
            self.fields[name] = integer()
        self.fields["width"].setSpecialValueText("Весь сенсор")
        self.fields["height"].setSpecialValueText("Весь сенсор")
        pixel_format = QComboBox()
        pixel_format.addItems(["Mono8", "Mono16", "Raw8", "Raw16"])
        pixel_format.setEditable(True)
        self.fields["pixel_format"] = pixel_format
        trigger = QComboBox()
        for label, value in (
            ("Внешний триггер", "external"),
            ("Программный триггер", "software"),
            ("Непрерывный поток", "free"),
        ):
            trigger.addItem(label, value)
        self.fields["trigger_mode"] = trigger
        source = QComboBox()
        source.addItem("GPI1")
        source.setEditable(True)
        self.fields["trigger_source"] = source
        activation = QComboBox()
        activation.addItems(["RisingEdge", "FallingEdge"])
        self.fields["trigger_activation"] = activation
        bits = QComboBox()
        bits.addItem("8", 8)
        bits.addItem("10", 10)
        self.fields["sensor_bits"] = bits
        self.fields["frame_rate"] = decimal(100000)
        self.fields["frame_rate"].setSpecialValueText("Без ограничителя")
        labels = {
            "exposure_us": "Экспозиция, мкс",
            "gain": self.gain_label,
            "binning": "Binning X и Y",
            "width": "Ширина ROI камеры",
            "height": "Высота ROI камеры",
            "offset_x": "Смещение X",
            "offset_y": "Смещение Y",
            "pixel_format": "Формат пикселя",
            "trigger_mode": "Захват",
            "trigger_source": "Вход триггера",
            "trigger_activation": "Фронт триггера",
            "sensor_bits": "Биты АЦП (8 / 10)",
            "frame_rate": "Ограничитель FPS (0 = выкл.)",
        }
        for name, box in self.fields.items():
            settings_form.addRow(labels[name], box)
        layout.addLayout(settings_form)
        self.apply = QPushButton("Применить к камере")
        layout.addWidget(self.apply)
        hint = QLabel(
            "Изменения сохраняются после Enter/выхода из поля.\nК камере применяются по кнопке «Применить» или при запуске.\nНоль ширины/высоты — весь сенсор после binning."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        self.set_settings(CameraSettings(**config["camera"]))
        for box in (self.backend, *self.fields.values()):
            if isinstance(box, QComboBox):
                box.currentTextChanged.connect(self._changed)
            else:
                box.editingFinished.connect(self._changed)
        self.serial.editingFinished.connect(self._changed)
        self.devices.currentIndexChanged.connect(self._select_device)

    def _changed(self, *args):
        if not self.updating:
            self.changed.emit()

    def _select_device(self, index):
        data = self.devices.itemData(index)
        if data:
            self.serial.setText(data["serial"])
            self._changed()

    def show_devices(self, devices):
        self.devices.clear()
        self.devices.addItem("Выберите камеру…", None)
        for device in devices:
            self.devices.addItem(f"{device['model']} / {device['serial']} / {device.get('transport', 'USB3')}", device)
        if len(devices) == 1:
            self.devices.setCurrentIndex(1)

    def settings(self):
        values = {}
        for name, box in self.fields.items():
            if isinstance(box, QComboBox):
                values[name] = box.currentData() if name in ("trigger_mode", "sensor_bits") else box.currentText()
            else:
                values[name] = None if name == "gain" and box.value() == -1 else box.value()
        return CameraSettings(**values).validate()

    def set_settings(self, settings):
        self.updating = True
        try:
            for name, value in settings_dict(settings).items():
                box = self.fields[name]
                if isinstance(box, QComboBox):
                    if name in ("trigger_mode", "sensor_bits"):
                        box.setCurrentIndex(box.findData(value))
                    else:
                        if box.findText(str(value)) < 0:
                            box.addItem(str(value))
                        box.setCurrentText(str(value))
                else:
                    box.setValue(-1 if name == "gain" and value is None else value)
        finally:
            self.updating = False

    def capabilities(self, caps):
        self.updating = True
        try:
            for name, key in (("pixel_format", "pixel_formats"), ("trigger_source", "trigger_sources")):
                values = caps.get(key, [])
                box = self.fields[name]
                current = box.currentText()
                if values:
                    box.clear()
                    box.addItems(values)
                    box.setCurrentText(current if current in values else values[0])
            self.gain_label.setText("Усиление, дБ")
            for name in ("exposure_us", "gain", "width", "height", "binning"):
                bounds = caps.get(name, {})
                box = self.fields[name]
                box.setToolTip(f"Камера: {bounds}")
        finally:
            self.updating = False

    def set_state(self, state):
        disconnected = state == "disconnected"
        idle = state == "idle"
        for box in (self.backend, self.serial, self.search, self.devices, self.connect_button):
            box.setEnabled(disconnected)
        self.disconnect_button.setEnabled(not disconnected)
        self.apply.setEnabled(idle)
        for box in self.fields.values():
            box.setEnabled(disconnected or idle)
