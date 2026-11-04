"""Camera widgets only; device operations are requested by the main window."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                              QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                              QPushButton, QSpinBox, QVBoxLayout, QWidget)
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
        self.backend.addItem("Basler / pypylon", "basler")
        self.backend.addItem("Демонстрация без камеры", "simulated")
        self.backend.setCurrentIndex(self.backend.findData(config["backend"]))
        form.addRow("Драйвер", self.backend)
        self.devices = QComboBox()
        form.addRow("Найденные камеры", self.devices)
        self.serial = QLineEdit(config["camera_serial"])
        self.serial.setPlaceholderText("Пусто: единственная найденная камера")
        self.ip = QLineEdit(config["camera_ip"])
        self.ip.setPlaceholderText("IP камеры, например 192.168.2.10")
        form.addRow("Серийный номер", self.serial)
        form.addRow("IP камеры", self.ip)
        self.search = QPushButton("Найти")
        self.connect_button = QPushButton("Подключить")
        self.disconnect_button = QPushButton("Отключить")
        buttons = QHBoxLayout()
        for button in (self.search, self.connect_button, self.disconnect_button):
            buttons.addWidget(button)
        layout.addLayout(form)
        layout.addLayout(buttons)
        self.force_ip = QPushButton("Временный IP камеры (ForceIP)…")
        layout.addWidget(self.force_ip)
        self.description = QLabel("Камера отключена")
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.fields = {}
        settings_form = QFormLayout()
        self.fields["exposure_us"] = decimal(1e8)
        self.fields["exposure_us"].setMinimum(0.001)
        self.fields["gain"] = decimal(10000)
        self.gain_label = QLabel("Усиление (единицы камеры)")
        self.fields["binning"] = integer(4, 1)
        for name in ("width", "height", "offset_x", "offset_y"):
            self.fields[name] = integer()
        self.fields["width"].setSpecialValueText("Весь сенсор")
        self.fields["height"].setSpecialValueText("Весь сенсор")
        pixel_format = QComboBox()
        pixel_format.addItems(["Mono8", "Mono12", "Mono12Packed", "Mono16"])
        pixel_format.setEditable(True)
        self.fields["pixel_format"] = pixel_format
        trigger = QComboBox()
        for label, value in (("Внешний триггер", "external"), ("Программный триггер", "software"), ("Непрерывный поток", "free")):
            trigger.addItem(label, value)
        self.fields["trigger_mode"] = trigger
        source = QComboBox()
        source.addItem("Line1")
        source.setEditable(True)
        self.fields["trigger_source"] = source
        activation = QComboBox()
        activation.addItems(["RisingEdge", "FallingEdge"])
        self.fields["trigger_activation"] = activation
        self.fields["packet_size"] = integer(9000, 576)
        self.fields["inter_packet_delay"] = integer(1000000000)
        self.fields["frame_rate"] = decimal(100000)
        self.fields["frame_rate"].setSpecialValueText("Без ограничителя")
        labels = {"exposure_us": "Экспозиция, мкс", "gain": self.gain_label,
                  "binning": "Binning X и Y", "width": "Ширина ROI камеры", "height": "Высота ROI камеры",
                  "offset_x": "Смещение X", "offset_y": "Смещение Y", "pixel_format": "Формат пикселя",
                  "trigger_mode": "Захват", "trigger_source": "Вход триггера",
                  "trigger_activation": "Фронт триггера", "packet_size": "GigE пакет, байт",
                  "inter_packet_delay": "GigE задержка, ticks", "frame_rate": "Ограничитель FPS (0 = выкл.)"}
        for name, box in self.fields.items():
            settings_form.addRow(labels[name], box)
        layout.addLayout(settings_form)
        self.apply = QPushButton("Применить к камере")
        layout.addWidget(self.apply)
        hint = QLabel("Изменения сохраняются после Enter/выхода из поля.\nК камере применяются по кнопке «Применить» или при запуске.\nНоль ширины/высоты — весь сенсор после binning.")
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
        self.ip.editingFinished.connect(self._changed)
        self.devices.currentIndexChanged.connect(self._select_device)

    def _changed(self, *args):
        if not self.updating:
            self.changed.emit()

    def _select_device(self, index):
        data = self.devices.itemData(index)
        if data:
            self.serial.setText(data["serial"])
            self.ip.setText(data.get("ip", "") if data.get("ip") != "—" else "")
            self._changed()

    def show_devices(self, devices):
        self.devices.clear()
        self.devices.addItem("Выберите камеру…", None)
        for device in devices:
            self.devices.addItem(f"{device['model']} / {device['serial']} / {device.get('ip', '')}", device)
        if len(devices) == 1:
            self.devices.setCurrentIndex(1)

    def settings(self):
        values = {}
        for name, box in self.fields.items():
            if isinstance(box, QComboBox):
                values[name] = box.currentData() if name == "trigger_mode" else box.currentText()
            else:
                values[name] = box.value()
        return CameraSettings(**values).validate()

    def set_settings(self, settings):
        self.updating = True
        try:
            for name, value in settings_dict(settings).items():
                box = self.fields[name]
                if isinstance(box, QComboBox):
                    if name == "trigger_mode":
                        box.setCurrentIndex(box.findData(value))
                    else:
                        if box.findText(str(value)) < 0:
                            box.addItem(str(value))
                        box.setCurrentText(str(value))
                else:
                    box.setValue(value)
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
            node = caps.get("gain_node", "Gain")
            self.gain_label.setText(f"Усиление ({'Raw' if 'Raw' in node else 'dB / единицы камеры'})")
            for name in ("exposure_us", "gain", "width", "height", "binning"):
                bounds = caps.get(name, {})
                box = self.fields[name]
                box.setToolTip(f"Камера: {bounds}")
        finally:
            self.updating = False

    def set_state(self, state):
        disconnected = state == "disconnected"
        idle = state == "idle"
        for box in (self.backend, self.serial, self.ip, self.search, self.devices, self.force_ip, self.connect_button):
            box.setEnabled(disconnected)
        self.disconnect_button.setEnabled(not disconnected)
        self.apply.setEnabled(idle)
        for box in self.fields.values():
            box.setEnabled(disconnected or idle)


class ForceIPDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Временный адрес Basler GigE")
        layout = QFormLayout(self)
        label = QLabel("Камера должна быть отключена в приложении и pylon Viewer.\nАдрес сбросится после отключения питания камеры.\nЗдесь меняется только IP камеры; сетевую карту ПК настройте отдельно.")
        label.setWordWrap(True)
        layout.addRow(label)
        self.fields = {"mac": QLineEdit(), "address": QLineEdit(),
                       "mask": QLineEdit("255.255.255.0"), "gateway": QLineEdit("0.0.0.0")}
        for key, title in (("mac", "MAC камеры"), ("address", "Новый IP"), ("mask", "Маска"), ("gateway", "Шлюз")):
            layout.addRow(title, self.fields[key])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return {key: box.text().strip() for key, box in self.fields.items()}
