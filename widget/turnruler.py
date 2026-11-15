"""没有头的转盘刻度尺（看细节那一块左上的那条，widget/closeup.py 用）：一条和胶囊一样高的槽，里面一排刻度，正中一根强调色的竖线不动。
- 拖：刻度跟着手走（DEG_PER_PX，10 像素一格）。按下不动不转（拖是相对的，不是点哪转到哪）。
- 滚轮、触摸板（怎么分看 widget/wheel.py 的 is_notch）：带格的滚轮一格、方向键一下转一格（STEP_DEG）；连续的位移（触摸板、开着平滑滚动的鼠标）
  按位移走，增益比拖小（SWIPE_DEG_PER_PX：触摸板随手一划几百像素，平滑滚动的鼠标一格约 39 像素 ≈ 一格刻度）。往下 / 往左 = 刻度往左（和「我的同桌」滑动条一个方向）。
- 刻度没有头，转多少圈都行；每过一根刻度 tick 一声（「按钮的声音」，sounds.notches，和大小滑杆共用 20 次 / 秒的上限）。
- 松手就停，没有惯性（「松手停在那个角度」）：触摸板松手后系统补的惯性滚动（ScrollMomentum）不要。
只发 turned（转了多少度，正 = 刻度往右），不认识狗，能直接拿到别处用。"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from widget import native, sounds, sticker
from widget.animation import FrameClock, Spring
from widget.capture_ui import ui_frozen
from widget.motion import MOTION_PAD
from widget.pointer import PointerDrag
from widget.wheel import is_notch, notches
from widget.widgets import PILL_H

DEG_PER_PX = 1.5          # 拖的时候：手挪 1 像素转多少度（刻度跟着手走，一格 STEP_DEG 是 10 像素）
SWIPE_DEG_PER_PX = 0.4    # 触摸板、平滑滚动的鼠标：1 像素位移转多少度
STEP_DEG = 15.0           # 一格：刻度间距、滚轮一格、方向键一下
MAJOR_EVERY = 6           # 每几格一根长刻度（90°）
FADE_PX = 22.0            # 刻度在两头这么长里淡掉（没有头的样子）
MINOR_H, MAJOR_H, MARK_H = 6.0, 12.0, 16.0   # 短刻度、长刻度、正中那根线多高（像素）
MIN_W = 120


def _smooth(u: float) -> float:
    u = 0.0 if u < 0.0 else 1.0 if u > 1.0 else u
    return u * u * (3.0 - 2.0 * u)


class TurnRuler(QWidget):
    """转盘刻度尺。turned(度)：用户转了它；set_angle 从外面对齐（不发信号）。"""
    turned = Signal(float)
    READS_ACCENT = True                                  # 画的时候读卡片的强调色：换同桌时跟着卡片一起淡过去（card.Card.set_accent）

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._angle = 0.0
        self._last: Optional[float] = None        # 拖着：上一次手在哪（全局 x）；None = 没在拖
        self._hovered = False
        self._pointer_drag = PointerDrag(self, self._drag_from_global)
        self._feedback = Spring(0.0, 0.16)        # 正中那根线：按着 1、悬停 0.45、平时 0
        self._clock = FrameClock(self, self._animate)
        self.setFixedHeight(PILL_H + 2 * MOTION_PAD)
        self.setMinimumWidth(MIN_W)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)     # 和大小滑杆一样（左右双箭头是 macOS 的「拉宽」，不像能转）

    # ---- 对外 ----
    @property
    def angle(self) -> float:
        return self._angle

    @property
    def adjusting(self) -> bool:
        """正按着拖。"""
        return self._last is not None

    def set_angle(self, deg: float) -> None:
        """从外面对齐（不发信号、不响）。"""
        if math.isfinite(deg) and deg != self._angle:
            self._angle = float(deg)
            self.update()

    def cancel_interaction(self) -> None:
        """换页、截图、藏起来：松开正在拖的。"""
        self._finish_drag()

    # ---- 转 ----
    def _turn(self, d: float) -> None:
        if not d or not math.isfinite(d):
            return
        before = self._angle
        self._angle += d
        sounds.notches(before, self._angle, STEP_DEG)
        self.update()
        self.turned.emit(d)

    # ---- 鼠标 ----
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.isEnabled() and not ui_frozen():
            self._last = event.globalPosition().x()
            self.setFocus(Qt.MouseFocusReason)
            self._retarget()
            self._pointer_drag.begin(event)
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        """连点第二下 Qt 报成双击、不报按下：当成一次按下。"""
        self.mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._last is None:
            return
        if not self._pointer_drag.move(event):        # 原生那条路已经送过这一下（细小的移动 Qt 会吞掉，pointer.py）
            self._drag_to(event.globalPosition().x())
        event.accept()

    def _drag_from_global(self, point: QPointF, _now: float) -> None:
        if self._last is not None:
            self._drag_to(point.x())

    def _drag_to(self, x: float) -> None:
        d = (x - self._last) * DEG_PER_PX
        self._last = x
        self._turn(d)

    def mouseReleaseEvent(self, event) -> None:
        if self._last is None or event.button() != Qt.LeftButton:
            return
        point = self._pointer_drag.native_release_position(event)
        self._drag_to(point.x() if point is not None else event.globalPosition().x())
        self._finish_drag()
        event.accept()

    def _finish_drag(self) -> None:
        self._pointer_drag.end()
        if self._last is not None:
            self._last = None
            self._retarget()

    # ---- 滚轮、触摸板、方向键 ----
    def wheelEvent(self, event) -> None:
        event.accept()                                     # 不让滚动漏到卡片上（卡片放得下时不滚，放不下时转盘上滚的是转盘）
        if not self.isEnabled() or ui_frozen() or event.phase() == Qt.ScrollMomentum:
            return                                         # 松手后系统补的惯性：不要
        if is_notch(event):
            self._turn(-notches(event) * STEP_DEG)         # notches：往下 / 往左是正数 → 刻度往左
            return
        px = event.pixelDelta()
        if px.isNull():
            a = event.angleDelta()
            dx, dy = a.x() / 2.0, a.y() / 2.0             # 只给了角度：精确位移的角度是像素的 2 倍（wheel.py）
        else:
            dx, dy = float(px.x()), float(px.y())
        self._turn((dx if abs(dx) > abs(dy) else dy) * SWIPE_DEG_PER_PX)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key_Left, Qt.Key_Down):
            self._turn(-STEP_DEG)
            event.accept()
        elif key in (Qt.Key_Right, Qt.Key_Up):
            self._turn(STEP_DEG)
            event.accept()
        else:
            super().keyPressEvent(event)                   # Esc 这些照旧交给卡片（关卡片）

    # ---- 悬停、按下的反馈 ----
    def _retarget(self) -> None:
        self._feedback.set_target(1.0 if self.adjusting else (0.45 if self._hovered else 0.0), instant=native.reduce_motion())
        self.update()
        if not self._feedback.settled:
            self._clock.start()

    def _animate(self, dt: float) -> bool:
        self._feedback.step(dt)
        self.update()
        return not self._feedback.settled

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._retarget()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._retarget()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    def hideEvent(self, event) -> None:
        self._finish_drag()
        self._hovered = False
        self._feedback.set_target(0.0, instant=True)
        self._clock.stop()
        super().hideEvent(event)

    def event(self, event) -> bool:
        if hasattr(self, "_pointer_drag") and (event.type() in (QEvent.UngrabMouse, QEvent.WindowDeactivate)
                                                or (event.type() == QEvent.EnabledChange and not self.isEnabled())):
            self._finish_drag()
        return super().event(event)

    # ---- 画 ----
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = getattr(self.window(), "theme", None) or sticker.theme()
        inset = MOTION_PAD + sticker.OUTLINE / 2.0
        groove = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        path = QPainterPath()
        path.addRoundedRect(groove, groove.height() / 2.0, groove.height() / 2.0)
        ink = QColor(sticker.INK)
        p.setPen(QPen(ink if self.isEnabled() else QColor(t.muted), sticker.OUTLINE))
        p.setBrush(QColor(t.btn))
        p.drawPath(path)

        p.save()
        p.setClipPath(path)
        cx, cy = groove.center().x(), groove.center().y()
        half = groove.width() / 2.0
        span = half * DEG_PER_PX                           # 看得见的角度范围（正中左右各多少度）
        for i in range(math.ceil((self._angle - span) / STEP_DEG), math.floor((self._angle + span) / STEP_DEG) + 1):
            x = cx + (self._angle - i * STEP_DEG) / DEG_PER_PX   # 角度变大，刻度往右走（跟着往右拖的手）
            major = i % MAJOR_EVERY == 0
            fade = _smooth(min(x - groove.left(), groove.right() - x) / FADE_PX)
            if fade <= 0.0:
                continue
            c = QColor(ink)
            c.setAlphaF((0.55 if major else 0.26) * fade * (1.0 if self.isEnabled() else 0.5))
            p.setPen(QPen(c, 1.4, Qt.SolidLine, Qt.RoundCap))
            h = (MAJOR_H if major else MINOR_H) / 2.0
            p.drawLine(QPointF(x, cy - h), QPointF(x, cy + h))
        p.restore()

        fb = self._feedback.value
        mark = QColor(t.accent) if self.isEnabled() else QColor(t.muted)
        h = MARK_H / 2.0 + fb
        p.setPen(QPen(mark, 2.4 + 0.8 * fb, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy - h), QPointF(cx, cy + h))
        if self.hasFocus():
            ring = QColor(t.accent)
            ring.setAlphaF(0.3)
            p.setPen(QPen(ring, 2.0))
            p.setBrush(Qt.NoBrush)
            r = groove.adjusted(-1.5, -1.5, 1.5, 1.5)
            p.drawRoundedRect(r, r.height() / 2.0, r.height() / 2.0)
