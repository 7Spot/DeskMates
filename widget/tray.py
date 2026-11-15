"""菜单栏图标：app 图标（widget/marks.py，和 App 图标、设置卡片左上角的圆同一个出处：要和 App 图标一致），跟随菜单栏深浅色。菜单：Settings…、Quit。
「小组件全局可见」开着时程序没有 Dock 图标，这里就是程序的"家"。狗一直在桌面上。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from widget.i18n import tr
from widget import marks


def menu_icon() -> QIcon:
    """22×22 逻辑像素、2 倍清晰度的黑色 app 图标（18 宽）；setIsMask 让 macOS 按菜单栏深浅色自动反色。"""
    pm = QPixmap(44, 44)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    marks.draw_app(p, QPointF(11.0, 11.0), QColor(Qt.black), 18.0)
    p.end()
    icon = QIcon(pm)
    icon.setIsMask(True)
    return icon


class Tray(QSystemTrayIcon):
    def __init__(self, window, parent=None):
        super().__init__(menu_icon(), parent)
        self.window = window
        self.menu = QMenu()
        self.rebuild()
        self.setContextMenu(self.menu)
        self.show()

    def rebuild(self) -> None:
        """按当前语言重建菜单（面板换了也从窗口上重新取）；鼠标停在骨头上的提示（DeskMates / 同桌）跟着换。"""
        self.setToolTip(tr("DeskMates"))
        self.menu.clear()
        self.menu.addAction(tr("Settings…")).triggered.connect(self.window.open_settings)
        self.menu.addSeparator()
        self.menu.addAction(tr("Quit DeskMates")).triggered.connect(lambda: QApplication.instance().quit())
