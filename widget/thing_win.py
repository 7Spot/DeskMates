"""一件物件的窗口：只画那一张图的透明小窗口（照球的窗口 widget/ball.py），摆在哪、图是哪张由 widget/things.py 管（place 每帧给）。

- 在它那一档的层级（native.LEVEL_THING：盆那一档在窝、狗屋前面，都在狗、球后面）、不激活程序、所有桌面都在；
  Qt 每次显示都会把这些原生属性改回去，所以在 showEvent 里重设。
- 停着的物件每帧一次系统调用都没有：大小变了才 setGeometry、只挪了才 move、长相（图、压扁、浓淡）变了才 update。
- 点击范围只有画出来的地方：鼠标先看在不在窗口里，在的话看图上那一点透不透明（影子不算；图还没出好时按物件的方框算），
  变了才告诉系统接不接鼠标（native.set_ignores_mouse）。按着的时候一直接。
- 窗口不骑在两块屏中间：things 给的方框已经夹在一块屏里（底下伸出屏的那一截裁掉，origin 是图的左上角在窗口里哪）。
- front=True：前沿（窝沿、盆沿；狗歇在窝里、在盆边吃喝时才显示）在这一档的前沿那一层（native.LEVEL_RIM：盖在里面的狗前面），永远点得穿；
  显示、藏起来都告诉 things（rims_changed：狗跟着换层）。看得见的地方狗的窗口不接鼠标（things.covers_dog → input._covered），点在那儿落到物件本身的窗口上。
鼠标事件原样转给 things（thing_press / thing_drag / thing_release，带系统给事件打的时间）；右键（触摸板两指点）弹这一款的小胶囊。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget

from widget import native
from widget.hand import event_time

HIT_ALPHA = 128            # 图上这一点的 alpha 不低于这个才算点到物件：描边、物件本身是实心的，影子最浓才 77


class ThingWindow(QWidget):
    def __init__(self, host, thing=None, front: bool = False, tier: int = 0):
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint
        super().__init__(None, flags | Qt.WindowTransparentForInput if front else flags)
        self.host, self.thing, self.front = host, thing, front
        self.level = (native.LEVEL_RIM if front else native.LEVEL_THING)[tier]   # 前后哪一档（things.tier）定在哪一层
        self.setAttribute(Qt.WA_TranslucentBackground)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setWindowTitle("Thing")
        native.apply(self)
        self.shot: Optional[QImage] = None           # 画的那张图（thing_art 出的，带像素密度）；None = 还没出好，窗口是空的
        self.origin = QPointF(0.0, 0.0)              # 图的左上角在窗口里哪（窗口被屏幕边裁掉一截时不是 0）
        self.pic = (0.0, 0.0)                        # 图画多大（逻辑像素）：换屏、换大小后新图还没出好时，旧图先撑成这么大
        self.pivot = QPointF(0.0, 0.0)               # duang 贴着哪一点压（图里：物件正中、脚下那条线）
        self.box = QRectF()                          # 物件本身的方框（图里的坐标）：没图时点击范围用它
        self.squash = 0.0
        self.alpha = 1.0
        self._accepting: Optional[bool] = None
        self._pressed = False
        self._painted: Optional[tuple] = None        # 上次画的时候长什么样（place：没变就不重画）

    # ---- 摆放 ----
    def place(self, rect: QRect, origin: QPointF, pic: tuple[float, float], pivot: QPointF, box: QRectF,
              shot: Optional[QImage], squash: float, alpha: float) -> None:
        """窗口摆在 rect（全局，已经夹在一块屏里）；图的左上角在窗口里的 origin、画成 pic 那么大。什么都没变就什么都不做。"""
        self.shot, self.origin, self.pic, self.pivot, self.box = shot, origin, pic, pivot, box
        self.squash, self.alpha = squash, alpha
        if (self.width(), self.height()) != (rect.width(), rect.height()):
            self.setGeometry(rect)
        elif (self.x(), self.y()) != (rect.x(), rect.y()):
            self.move(rect.x(), rect.y())
        look = (rect.width(), rect.height(), origin.x(), origin.y(), pic, shot.cacheKey() if shot is not None else None, squash, alpha)
        if look != self._painted:
            self._painted = look
            self.update()

    def showEvent(self, event) -> None:
        native.set_all_spaces(self, True)        # 所有桌面、全屏 App 上都在（和狗一样）
        native.set_no_activate(self)             # 点物件不把程序切到前台
        native.set_level(self, self.level)
        if self.front:
            native.set_ignores_mouse(self, True)
        self._accepting = None                   # 下一帧重新告诉系统接不接鼠标（Qt 重新显示时按窗口标志重设过）
        super().showEvent(event)
        if self.front:
            self.host.rims_changed()             # 狗换到这件那一档里（窝和窝沿之间）

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self.front:
            self.host.rims_changed()             # 狗回到所有物件前面

    # ---- 点击范围只有画出来的地方 ----
    def covers(self, local: QPointF) -> bool:
        """窗口里这一点是不是物件：图上那一点够不透明（影子、透明的地方不算）；图还没出好就按物件的方框。"""
        x, y = local.x() - self.origin.x(), local.y() - self.origin.y()
        shot = self.shot
        if shot is None or shot.isNull() or self.pic[0] <= 0 or self.pic[1] <= 0:
            return self.box.contains(QPointF(x, y))
        px, py = int(x * shot.width() / self.pic[0]), int(y * shot.height() / self.pic[1])
        return 0 <= px < shot.width() and 0 <= py < shot.height() and shot.pixelColor(px, py).alpha() >= HIT_ALPHA

    def update_hit(self, cursor_global) -> bool:
        """每帧：鼠标在物件上才接鼠标，按着的时候一直接（拖到一半别脱手）。鼠标不在窗口的方框里就不往下看。返回鼠标在不在物件上。"""
        if self.front:
            return False
        inside = self.geometry().contains(cursor_global)
        over = inside and self.covers(QPointF(cursor_global - self.pos()))
        accept = (over or self._pressed) and self.isVisible() and self.alpha > 0.5
        if accept != self._accepting and native.set_ignores_mouse(self, not accept):
            self._accepting = accept
        if over and accept:
            self.setCursor(Qt.ClosedHandCursor if self._pressed else Qt.OpenHandCursor)
        return over

    def let_go(self) -> None:
        """松手事件丢了（things 兜底）：这个窗口也当松了手。"""
        self._pressed = False

    # ---- 鼠标 ----
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self.front:
            self._pressed = True
            self.setCursor(Qt.ClosedHandCursor)
            self.host.thing_press(self.thing, event.globalPosition(), event_time(event))
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._pressed:
            self.host.thing_drag(self.thing, event.globalPosition(), event_time(event))
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._pressed and event.button() == Qt.LeftButton:
            self._pressed = False
            self.setCursor(Qt.OpenHandCursor)
            self.host.thing_release(self.thing, event.globalPosition(), event_time(event))
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        self.mousePressEvent(event)              # 连点：第二下照样当按下

    def contextMenuEvent(self, event) -> None:
        if not self.front:
            self.host.thing_menu(self.thing, event.globalPos())   # 右键：这一款的小胶囊（关掉 = 收起来）
        event.accept()

    # ---- 画 ----
    def paintEvent(self, event) -> None:
        shot = self.shot
        if shot is None or shot.isNull() or self.alpha <= 0.0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setOpacity(self.alpha)
        p.translate(self.origin)
        if abs(self.squash) > 1e-3:                               # duang：贴着脚下那条线竖直压扁，横向鼓一点（照球）
            p.translate(self.pivot)
            p.scale(1.0 + self.squash * 0.5, 1.0 - self.squash)
            p.translate(-self.pivot)
        p.drawImage(QRectF(0.0, 0.0, self.pic[0], self.pic[1]), shot)
        p.end()
