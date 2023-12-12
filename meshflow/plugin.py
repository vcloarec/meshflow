from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QMenu, QAction
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt

from qgis.gui import QgsDockWidget
from .resources import *

from .gui.dock_widget import MeshFlowDockWidget


class MeshFlowPlugin:
    def __init__(self, iface):
        self._iface = iface

        self._dock_widget = None
        self._visibility_action = None

    def initGui(self):
        self._dock_widget = MeshFlowDockWidget(self._iface)
        self._visibility_action = QAction("Mesh Flow", self._iface.mainWindow())
        self._iface.mainWindow().addDockWidget(Qt.LeftDockWidgetArea, self._dock_widget)
        self._dock_widget.setToggleVisibilityAction(self._visibility_action)

        mesh_menu = self._iface.mainWindow().findChild(QMenu, "mMeshMenu")
        mesh_menu.addAction(self._visibility_action)

    def unload(self):
        self._dock_widget.deleteLater()
