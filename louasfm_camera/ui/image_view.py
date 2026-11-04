"""Image contrast/zoom and ROI projections; displayed levels never modify pixels."""
import pyqtgraph as pg
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from ..services.analysis import analyze


class ImageView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.auto_levels = QCheckBox("Автоконтраст")
        self.auto_levels.setChecked(True)
        self.use_roi = QCheckBox("ROI анализа")
        self.fit = QPushButton("Вписать изображение")
        for widget in (self.auto_levels, self.use_roi, self.fit):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.canvas = pg.GraphicsLayoutWidget()
        self.plot = self.canvas.addPlot()
        self.plot.setAspectLocked(True)
        self.plot.invertY(True)
        self.plot.setLabel("bottom", "X", units="px")
        self.plot.setLabel("left", "Y", units="px")
        self.image = pg.ImageItem(axisOrder="row-major")
        self.plot.addItem(self.image)
        self.histogram = pg.HistogramLUTItem()
        self.histogram.setImageItem(self.image)
        self.canvas.addItem(self.histogram)
        self.roi = pg.RectROI([0, 0], [100, 100], pen=pg.mkPen("y", width=2))
        self.roi.addScaleHandle([1, 1], [0, 0])
        self.plot.addItem(self.roi)
        self.roi.hide()
        self.canvas.nextRow()
        self.profile_x = self.canvas.addPlot(title="Средний профиль по X")
        self.x_curve = self.profile_x.plot(pen="c")
        self.canvas.nextRow()
        self.profile_y = self.canvas.addPlot(title="Средний профиль по Y")
        self.y_curve = self.profile_y.plot(pen="y")
        layout.addWidget(self.canvas)
        self.statistics = QLabel("Нет изображения")
        self.statistics.setWordWrap(True)
        layout.addWidget(self.statistics)
        self.current = None
        self.shape = None
        self.use_roi.toggled.connect(self._roi_toggled)
        self.roi.sigRegionChangeFinished.connect(self.update_analysis)
        self.fit.clicked.connect(lambda: self.plot.autoRange())

    def _roi_toggled(self, checked):
        self.roi.setVisible(checked)
        self.update_analysis()

    def show_frame(self, frame):
        self.current = frame
        self.image.setImage(frame.pixels, autoLevels=self.auto_levels.isChecked(), autoDownsample=True)
        if frame.pixels.shape != self.shape:
            self.shape = frame.pixels.shape
            height, width = self.shape
            self.roi.setPos([width/4, height/4])
            self.roi.setSize([width/2, height/2])
            self.plot.autoRange()
        self.update_analysis()

    def update_analysis(self, *args):
        if self.current is None:
            return
        region = None
        if self.use_roi.isChecked():
            position, size = self.roi.pos(), self.roi.size()
            region = (position.x(), position.y(), size.x(), size.y())
        data = analyze(self.current.pixels, region)
        self.x_curve.setData(data["profile_x"])
        self.y_curve.setData(data["profile_y"])
        frame = self.current
        self.statistics.setText(f"Кадр {frame.frame_id} · {frame.pixels.shape[1]}×{frame.pixels.shape[0]} · {frame.pixels.dtype} · "
                                f"ROI {data['roi']} · min={data['minimum']} max={data['maximum']} "
                                f"mean={data['mean']:.2f} sum={data['sum']:.0f}\n{frame.received_utc}")
