"""Read-only visualization of channel transitions received from ThuliumBB."""
import re
import pyqtgraph as pg
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from ..services.beaglebone import trigger_edges


class PulseView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.show_shutters = QCheckBox("Показать S0–S7")
        self.show_shutters.setChecked(True)
        self.show_analog = QCheckBox("Показать аналоговые каналы (нормированные)")
        controls.addWidget(self.show_shutters)
        controls.addWidget(self.show_analog)
        layout.addLayout(controls)
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "Время схемы", units="ms")
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        layout.addWidget(self.plot)
        self.summary = QLabel("Подключитесь к UDP 9998. На BeagleBone должен быть открыт веб-интерфейс ThuliumBB.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.pulses, self.names = {}, {}
        self.channel, self.activation = "D0", "RisingEdge"
        self.show_shutters.toggled.connect(self.redraw)
        self.show_analog.toggled.connect(self.redraw)

    def set_scheme(self, pulses, names):
        self.pulses, self.names = pulses, names
        self.redraw()

    def redraw(self, *args):
        self.plot.clear()
        end = max((edge[0] for edges in self.pulses.values() for edge in edges), default=0)
        ticks = []
        channels = sorted(self.pulses, key=lambda name: (name[:1], int(name[1:]) if name[1:].isdigit() else 1000, name))
        index = 0
        for channel in channels:
            digital = bool(re.fullmatch(r"D\d+", channel))
            shutter = bool(re.fullmatch(r"S\d+", channel))
            if shutter and not self.show_shutters.isChecked():
                continue
            if not (digital or shutter) and not self.show_analog.isChecked():
                continue
            edges = self.pulses[channel]
            if not edges:
                continue
            xs, ys = zip(*edges)
            xs, ys = list(xs), list(ys)
            if xs[-1] < end:
                xs.append(end)
                ys.append(ys[-1])
            if not (digital or shutter):
                scale = max(abs(v) for v in ys) or 1
                ys = [v/scale for v in ys]
            color = "#ffcc55" if channel == self.channel else pg.intColor(index, hues=24)
            self.plot.plot(xs, [index*1.5+v for v in ys], stepMode="left", pen=pg.mkPen(color, width=2))
            name = self.names.get(channel, "")
            ticks.append((index*1.5, f"{channel} {name}"))
            index += 1
        self.plot.getAxis("left").setTicks([ticks])
        edges = trigger_edges(self.pulses, self.channel, self.activation)
        for point in edges:
            self.plot.addItem(pg.InfiniteLine(point, angle=90, pen=pg.mkPen("#ffcc55", style=pg.QtCore.Qt.PenStyle.DashLine)))
        self.summary.setText(f"Канал камеры: {self.channel}, {self.activation}. Фронты, мс: {edges or 'нет'}.\n"
                             f"Последнее переданное переключение: {end:g} мс. Полная длительность цикла и хвост 10 мс "
                             "в UDP не передаются; график не вычисляет их по последнему импульсу. "
                             "UDP служит для наблюдения; экспозицию запускает физический вход камеры.")
