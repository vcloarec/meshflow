import decorator
import math
import os
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime, QSize
from PyQt5.QtWidgets import (
    QComboBox,
    QWidget,
    QGridLayout,
    QLabel,
    QToolButton,
    QAction,
    QToolBar,
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QDialogButtonBox,
    QApplication,
)
from PyQt5.QtGui import QColor, QIcon
from qgis.gui import QgsDockWidget, QgsMapLayerComboBox, QgsMapTool, QgsRubberBand, QgsDoubleSpinBox
from qgis.core import (
    QgsProject,
    Qgis,
    QgsMapLayerProxyModel,
    QgsMeshLayer,
    QgsMapLayerType,
    QgsMeshDatasetIndex,
    QgsWkbTypes,
    QgsGeometry,
    QgsVector,
    QgsSettings,
)

from ..resources import *

ui_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "ui", "dock_widget" + ".ui")

try:
    import pyqtgraph
except ImportError:
    import meshflow.pyqtgraph_0_12_2 as pyqtgraph


@decorator.decorator
def showWaitCursor(func, *args, **kwargs):
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        return func(*args, **kwargs)
    finally:
        QApplication.restoreOverrideCursor()


class ConfigDialog(QDialog):
    def __init__(self, parent, step: float):
        QDialog.__init__(self, parent)
        main_lay = QVBoxLayout()
        lay = QHBoxLayout()
        self.setLayout(main_lay)
        lay.addWidget(QLabel("Profile Step"))
        self._double_spinbox = QgsDoubleSpinBox()
        self._double_spinbox.setClearValue(0.5)
        self._double_spinbox.setSingleStep(0.1)
        self._double_spinbox.setValue(step)
        lay.addWidget(self._double_spinbox)
        main_lay.addLayout(lay)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        main_lay.addWidget(button_box)

    def value(self):
        return self._double_spinbox.value()


class PickGeometryTool(QgsMapTool):
    finished = pyqtSignal(list, bool)  # list of pointsXY, whether finished or still drawing

    def __init__(self, canvas):
        QgsMapTool.__init__(self, canvas)
        self.points = []
        self.capturing = False
        self.rubber_band = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.rubber_band.setColor(Qt.red)
        self.rubber_band.setWidth(2)

    def canvasMoveEvent(self, e):
        self.rubber_band.movePoint(e.mapPoint())

    def canvasPressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.points.append(e.mapPoint())
            self.rubber_band.addPoint(e.mapPoint())
        if e.button() == Qt.RightButton:
            if len(self.points) > 1:
                self.finished.emit(self.points, True)
            self.points = []
            self.rubber_band.reset(QgsWkbTypes.LineGeometry)

    def canvasReleaseEvent(self, e):
        pass

    def deactivate(self):
        QgsMapTool.deactivate(self)
        self.rubber_band.reset(QgsWkbTypes.LineGeometry)


class MainWidget(QWidget):
    def __init__(self, iface, parent=None):
        settings = QgsSettings()
        if settings.contains("mesh-flow/delta"):
            self._delta = float(settings.value("mesh-flow/delta"))
        else:
            self._delta = 0.5

        QWidget.__init__(self, parent)

        self._iface = iface
        lay = QGridLayout()
        self.setLayout(lay)
        self._tool_bar = QToolBar()
        icon_size = iface.iconSize(True)
        self._tool_bar.setIconSize(icon_size)
        self._tool_bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        lay.addWidget(self._tool_bar, 0, 0, 1, 2)
        lay.addWidget(QLabel("Mesh Layer"), 1, 0)
        lay.addWidget(QLabel("Vector Dataset Group"), 2, 0)
        lay.addWidget(QLabel("Depth Dataset Group"), 3, 0)
        self._combo_layer = QgsMapLayerComboBox(self)
        self._combo_layer.setFilters(QgsMapLayerProxyModel.MeshLayer)
        self._combo_layer.setProject(QgsProject.instance())
        lay.addWidget(self._combo_layer, 1, 1)

        self._combo_layer.layerChanged.connect(self._on_current_layer_changed)
        QgsProject.instance().layersAdded.connect(self._on_current_layer_changed)
        QgsProject.instance().cleared.connect(self._on_current_layer_changed)

        self._combo_vector_dataset_group = QComboBox()
        lay.addWidget(self._combo_vector_dataset_group, 2, 1)

        self._combo_depth_dataset_group = QComboBox()
        lay.addWidget(self._combo_depth_dataset_group, 3, 1)

        self._combo_vector_dataset_group.currentIndexChanged.connect(self._update_profile_flow)
        self._combo_depth_dataset_group.currentIndexChanged.connect(self._update_profile_flow)

        self._map_tool = PickGeometryTool(iface.mapCanvas())
        self._action_map_tool = QAction(QIcon(":/plugins/mesh-flow/images/draw_profile.svg"), "Draw Profile", self)
        self._action_map_tool.setCheckable(True)
        self._map_tool.setAction(self._action_map_tool)
        self._tool_bar.addAction(self._action_map_tool)
        self._action_map_tool.triggered.connect(self._on_map_tool)
        self._map_tool.finished.connect(self._on_map_tool_finished)

        self.current_profile_line = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.LineGeometry)
        self.current_profile_line.setColor(Qt.green)
        self.current_profile_line.setWidth(2)

        self._action_config = QAction(QIcon(":/plugins/mesh-flow/images/settings.svg"), "Config", self)
        self._action_config.triggered.connect(self._on_config_dialog)
        self._tool_bar.addAction(self._action_config)

        pyqtgraph.setConfigOption("background", "w")
        self._gw = pyqtgraph.GraphicsLayoutWidget()
        self._plot = self._gw.addPlot()
        self._plot.showGrid(x=True, y=True)
        axis = pyqtgraph.DateAxisItem()
        axis.setLabel("Time")
        self._plot.setAxisItems({"bottom": axis})
        lay.addWidget(self._gw, 4, 0, 1, 2)

        self._iface.mapCanvas().temporalRangeChanged.connect(self.on_time_change)
        self._time_line = pyqtgraph.InfiniteLine(angle=90)

    def _on_current_layer_changed(self):
        current_layer = self._combo_layer.currentLayer()
        self._combo_vector_dataset_group.clear()
        self._combo_depth_dataset_group.clear()
        if current_layer is None:
            return

        dataset_group_indexes = current_layer.datasetGroupsIndexes()
        for i in dataset_group_indexes:
            meta = current_layer.datasetGroupMetadata(QgsMeshDatasetIndex(i, 0))
            name = meta.name()
            if meta.isVector():
                self._combo_vector_dataset_group.addItem(name)
            else:
                self._combo_depth_dataset_group.addItem(name)

        self._update_profile_flow()

    def _on_map_tool(self):
        self._iface.mapCanvas().setMapTool(self._map_tool)

    def _on_map_tool_finished(self, points):
        geom = QgsGeometry.fromPolylineXY(points)
        self.current_profile_line.setToGeometry(geom)
        self._update_profile_flow()

    def _on_config_dialog(self):
        dial = ConfigDialog(self, self._delta)
        if dial.exec():
            self._delta = dial.value()
            settings = QgsSettings()
            settings.setValue("mesh-flow/delta", self._delta)

    @showWaitCursor
    def _update_profile_flow(self):
        self._plot.clear()
        if self._delta <= 0:
            return
        current_layer = self._combo_layer.currentLayer()
        if current_layer is None:
            return
        dataset_vector_name = self._combo_vector_dataset_group.currentText()
        group_vector_index = -1
        dataset_depth_name = self._combo_depth_dataset_group.currentText()
        group_depth_index = -1
        dataset_group_indexes = current_layer.datasetGroupsIndexes()
        for i in dataset_group_indexes:
            meta = current_layer.datasetGroupMetadata(QgsMeshDatasetIndex(i, 0))
            if meta.name() == dataset_vector_name:
                group_vector_index = i
            if meta.name() == dataset_depth_name:
                group_depth_index = i

        if group_vector_index == -1 or group_depth_index == -1:
            return

        profile_geom = self.current_profile_line.asGeometry()
        length = profile_geom.length()
        if length == 0 or length / self._delta > 10000:
            return

        dataset_vector_count = current_layer.datasetCount(QgsMeshDatasetIndex(group_vector_index, 0))
        through_line_value_series = []
        times_hour = []
        time_abs = []
        ref_time = current_layer.temporalProperties().referenceTime()
        for i in range(dataset_vector_count):
            offset = self._delta / 2
            sum = 0
            vector_ds_index = QgsMeshDatasetIndex(group_vector_index, i)
            ds_vect_meta = current_layer.datasetMetadata(vector_ds_index)
            times_hour.append(ds_vect_meta.time())
            time_ms = current_layer.datasetRelativeTimeInMilliseconds(vector_ds_index)
            time_abs.append(ref_time.addMSecs(time_ms).toPyDateTime().timestamp())
            while offset < length:
                pt = profile_geom.interpolate(offset).asPoint()
                vector_value = current_layer.datasetValue(QgsMeshDatasetIndex(group_vector_index, i), pt)
                _, _, next_vert, _ = profile_geom.closestSegmentWithContext(pt)
                prev_vert = next_vert - 1

                pt1 = profile_geom.vertexAt(prev_vert)
                pt2 = profile_geom.vertexAt(next_vert)

                depth = current_layer.datasetValue(QgsMeshDatasetIndex(group_depth_index, i), pt).scalar()

                unit_orth_vector = QgsVector(pt2.x() - pt1.x(), pt2.y() - pt1.y())
                unit_orth_vector = unit_orth_vector.perpVector()
                try:
                    unit_orth_vector = unit_orth_vector.normalized()
                except:
                    offset += self._delta
                    continue

                vel_x = vector_value.x()
                vel_y = vector_value.y()
                proj_vector_value = unit_orth_vector.x() * vector_value.x() + unit_orth_vector.y() * vector_value.y()
                proj_vector_value = proj_vector_value * depth * self._delta
                if not math.isnan(proj_vector_value):
                    sum += proj_vector_value
                offset += self._delta

            through_line_value_series.append(sum)

        pen = pyqtgraph.mkPen(color=QColor(Qt.blue), width=2, cosmetic=True)
        self._plot.plot(x=time_abs, y=through_line_value_series, connect="finite", pen=pen)
        pen = pyqtgraph.mkPen(color=QColor(Qt.red), width=1, cosmetic=True)
        self._time_line = pyqtgraph.InfiniteLine(angle=90, pen=pen)
        self._plot.addItem(self._time_line)
        self.on_time_change()

    def on_closed(self):
        self.current_profile_line.hide()

    def on_opened(self):
        self.current_profile_line.show()

    def on_time_change(self):
        current_time = self._iface.mapCanvas().temporalRange().begin()
        if not current_time.isValid():
            return
        current_time = current_time.toPyDateTime().timestamp()
        self._time_line.setValue(current_time)


class MeshFlowDockWidget(QgsDockWidget):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.setWindowTitle("Mesh Flow")
        self.setObjectName("meshFlow")
        self.widget = w = MainWidget(iface, iface.mainWindow())
        self.setWidget(w)

        self.closed.connect(self.widget.on_closed)
        self.opened.connect(self.widget.on_opened)
