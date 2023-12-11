from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt

from qgis.gui import QgsDockWidget
from .resources import *

from .gui.dock_widget import MeshFlowDockWidget


class MeshFlowPlugin:
    def __init__(self, iface):
        self._iface = iface

        self._dock_widget = None

    def initGui(self):
        self._dock_widget = MeshFlowDockWidget(self._iface)
        self._iface.mainWindow().addDockWidget(Qt.LeftDockWidgetArea, self._dock_widget)

    def unload(self):
        self._dock_widget.deleteLater()
