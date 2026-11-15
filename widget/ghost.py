"""过屏幕交界时另一块屏上的窗口（跨屏不连贯、闪一下、卡；站在交界上两边都该点得到）。

macOS 一个窗口只画在一块屏上，狗跨在两块屏中间时主窗口只能画它在的那块屏上的半截。所以每块屏各放一个这样的窗口，固定待在那块屏上：
- 从不搬到别的屏（搬一次两块屏像素密度不一样，画布要重建，新画面出来之前显示的还是上次的狗，就是"另一块屏上闪一下"）；
- 启动时就建好（第一次建要一百多毫秒，放到跨屏那一刻就是卡一下），没狗的时候画空的，透明、不接鼠标；
- 狗靠近这块屏时画同一只狗同一个姿势（画布位置按全局坐标算，两边正好接上）；
- 鼠标在它画的狗身上时接鼠标（window._update_hit 每帧定），按下、拖、松手都转交给主窗口（狗身上看得见的地方都能点）。
主窗口只在狗停下来才换屏（window._screen_for_scene）。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from widget import native
from widget.dogview import DogView
from widget.gltf import Model
from widget.render import Frame


class GhostWindow(QWidget):
    def __init__(self, model: Model, owner, home):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.owner = owner
        self.home = home                     # 这个窗口待在哪块屏
        self.drawing = False                 # 现在画着狗（没画就是空的）
        self.pressed = False                 # 鼠标是在这里按下的：拖到哪、松手都还从这里来
        self._accepting = None
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setWindowTitle("Dog")
        native.apply(self)
        self.view = DogView(model, parent=self)   # 这里不叠「···」
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)

    def showEvent(self, event) -> None:
        native.set_all_spaces(self, True)
        native.set_level(self, self.owner.level)   # 和主窗口同一层（window.set_dog_level 换层时也一起换）
        native.set_no_activate(self)
        native.pin_contents_to_bottom(self)
        self._accepting = None
        self.set_accepting(False)
        super().showEvent(event)

    def set_accepting(self, accept: bool) -> None:
        """告诉系统这个窗口接不接鼠标，变了才说；没说成（原生窗口还没建）下一帧再说。"""
        if accept != self._accepting and native.set_ignores_mouse(self, not accept):
            self._accepting = accept

    def sync(self, rect: QRect, frame: Frame, coat) -> None:
        """这一帧：窗口摆在 rect（全局坐标），画 frame；毛色跟主窗口一样。"""
        renderer = self.view.renderer
        if renderer.coat_image is not coat:
            renderer.set_coat(coat)
        self.view.set_frame(frame)
        self.drawing = True
        if self.geometry() != rect:
            self.setGeometry(rect)
        self.view.refresh()

    def clear(self) -> None:
        """狗不在这块屏附近了：画空的。"""
        if self.drawing:
            self.drawing = False
            self.view.set_frame(None)
            self.view.refresh()

    # ---- 鼠标都转交给主窗口 ----
    def _forward(self, event, handler) -> None:
        g = QPointF(event.globalPosition())
        forwarded = QMouseEvent(event.type(), QPointF(self.owner.mapFromGlobal(g)), g, event.button(), event.buttons(), event.modifiers())
        forwarded.setTimestamp(event.timestamp())       # 系统打的时间也带上：算手速用（widget/hand.py）
        handler(forwarded)
        event.accept()

    def mousePressEvent(self, event) -> None:
        self.pressed = True
        self._forward(event, self.owner.mousePressEvent)

    def mouseDoubleClickEvent(self, event) -> None:
        self.pressed = True
        self._forward(event, self.owner.mouseDoubleClickEvent)

    def mouseMoveEvent(self, event) -> None:
        if self.pressed:
            self._forward(event, self.owner.mouseMoveEvent)

    def mouseReleaseEvent(self, event) -> None:
        self.pressed = False
        self._forward(event, self.owner.mouseReleaseEvent)

    def contextMenuEvent(self, event) -> None:
        self.owner.contextMenuEvent(event)

    def wheelEvent(self, event) -> None:
        self.owner.wheelEvent(event)
