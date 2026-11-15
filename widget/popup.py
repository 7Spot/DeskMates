"""右键道具（球、物件）弹出的小胶囊。放的位置算法 place_menu 先下后上、再左右。
弹出来（带回弹）：从点的地方放大。
两种：带开关的（set_switch，名字 + 开关，点了原地切）；一句话的（set_action：右键道具通通是「我不要饭盆了」，点一下这件收起来、胶囊跟着收；
鼠标走远了、点别处也收）。"""
from __future__ import annotations

import math
from typing import Callable, Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QCursor, QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from widget import native, overlay, sounds, sticker
from widget.widgets import FrameClock, bounce, ease_out

SLIDE_S = 0.18                                    # 圆钮滑过去多久（和设置里的开关一样）
POP_FROM, POP_FADE_S, POP_S = 0.8, 0.12, 0.45    # 从多大放大、淡入多久、整段多久（回弹停稳）
LEAVE_PX = 40.0                                   # 一句话的胶囊：鼠标离胶囊（画出来的那颗）这么远（1 倍时的像素）就收
BOUNCE = (0.28, 0.5)                              # 弹簧：0.28 秒、阻尼 0.5（冲过头 16% × 0.2 ≈ 3%，回来一次就停）


def place_menu(origin: QPointF, painted: QRectF, screen: QRectF,
               anchor: Optional[QRectF] = None, gap: float = 0.0) -> tuple[QPoint, str]:
    """只排可见范围（含描边/阴影），透明窗口边距不算间隔；下、上、右、左依次试。"""
    width, height = painted.width(), painted.height()
    clamp_x = lambda x: min(max(x, screen.left()), max(screen.left(), screen.right() - width))
    clamp_y = lambda y: min(max(y, screen.top()), max(screen.top(), screen.bottom() - height))
    window_x = lambda x: min(max(round(x), math.ceil(screen.left() - painted.left())), math.floor(screen.right() - painted.right()))
    window_y = lambda y: min(max(round(y), math.ceil(screen.top() - painted.top())), math.floor(screen.bottom() - painted.bottom()))
    if anchor is None or anchor.isEmpty():
        top_left = QPointF(clamp_x(origin.x()), clamp_y(origin.y()))
        return QPoint(window_x(top_left.x() - painted.left()), window_y(top_left.y() - painted.top())), "point"

    x = clamp_x(origin.x() - width / 2)
    y = clamp_y(origin.y() - height / 2)
    candidates = (("below", QRectF(x, anchor.bottom() + gap, width, height)),
                  ("above", QRectF(x, anchor.top() - gap - height, width, height)),
                  ("right", QRectF(anchor.right() + gap, y, width, height)),
                  ("left", QRectF(anchor.left() - gap - width, y, width, height)))
    for side, candidate in candidates:
        if not screen.contains(candidate):
            continue
        px, py = candidate.left() - painted.left(), candidate.top() - painted.top()
        # 向远离悬浮栏的一侧取整，0.5px 的窗口坐标取整不能吃掉间距。
        px = math.ceil(px) if side == "right" else math.floor(px) if side == "left" else window_x(px)
        py = math.ceil(py) if side == "below" else math.floor(py) if side == "above" else window_y(py)
        placed = painted.translated(px, py)
        if screen.contains(placed):
            return QPoint(px, py), side

    # 极小可用区域无法容下任何一侧时，选遮挡最少的屏内位置。
    fallback = [(side, QRectF(clamp_x(r.left()), clamp_y(r.top()), width, height)) for side, r in candidates]
    side, best = min(fallback, key=lambda item: item[1].intersected(anchor).width() * item[1].intersected(anchor).height())
    return QPoint(window_x(best.left() - painted.left()), window_y(best.top() - painted.top())), side


class SwitchMenu(QWidget):
    """一颗小胶囊：和悬浮栏里的胶囊同一种画法、同样跟着大小缩放。带开关的（set_switch，overlay.draw_switch_pill）点了在原地切换，不收起；
    一句话的（set_action，右键道具的「我不要……了」：只有字，overlay.draw_posture_strip 那一种）点了做那件事、胶囊收起。
    普通的浮动小窗，不接管鼠标（弹出菜单开着时点外面的第一下只用来关它，球要多点一下才拿得到）：
    球随时能直接拿起，点别处这一下照常生效，同时胶囊收起（_watch 看全局的鼠标键）。"""
    PAD = 6.0                        # 胶囊四周留的透明边（1 倍时）：弹出回弹时不被裁

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._armed = False              # 弹出来时右键还按着：等它松开了，再按才算点别处
        self._watcher = QTimer(self)
        self._watcher.setInterval(30)
        self._watcher.timeout.connect(self._watch)
        self.setMouseTracking(True)
        self.text = ""
        self.on = False
        self.action = False              # 一句话的胶囊（set_action）：没有开关，点了做完就收
        self._callback: Optional[Callable[[bool], None]] = None
        self._act: Optional[Callable[[], None]] = None
        self._accent = QColor(sticker.INK)
        self._k = 1.0
        self._pos = 0.0                  # 圆钮滑到哪（0 关 … 1 开）
        self._hot = False
        self._pop_t: Optional[float] = None
        self._origin = QPointF()
        self._clock = FrameClock(self, self._tick)

    def set_switch(self, text: str, on: bool, callback: Callable[[bool], None], accent: str, k: float) -> None:
        self.action, self._act = False, None
        self.text, self.on, self._callback, self._accent, self._k = text, on, callback, QColor(accent), k
        self._pos = 1.0 if on else 0.0
        h = overlay.MENU_BASE_H * k
        margin = round(self.PAD * k)
        self.setFixedSize(math.ceil(overlay.switch_pill_width(text, h)) + 2 * margin, math.ceil(h) + 2 * margin)
        self.update()

    def set_action(self, text: str, act: Callable[[], None], k: float) -> None:
        """一句话的胶囊（右键道具：「我不要小球了」）：只有字，点一下叫 act、胶囊收起。"""
        self.action, self._act, self._callback = True, act, None
        self.text, self._k = text, k
        h = overlay.MENU_BASE_H * k
        margin = round(self.PAD * k)
        self.setFixedSize(math.ceil(overlay.plain_pill_width(text, h)) + 2 * margin, math.ceil(h) + 2 * margin)
        self.update()

    def pill_rect(self) -> QRectF:
        margin = round(self.PAD * self._k)
        return QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)

    def popup_at(self, pos: QPoint, avoid: Optional[QRectF] = None) -> None:
        """弹在 pos；给了 avoid（全局坐标）就摆在它旁边，不盖住它（下、上、右、左依次试）。"""
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        placed, _ = place_menu(QPointF(pos), self.pill_rect(), QRectF(screen.availableGeometry()), avoid)
        self.move(placed)
        self._origin = QPointF(pos - placed)
        self._pop_t = None if native.reduce_motion() else 0.0
        self.show()
        self.raise_()
        self._clock.start()
        self._armed = False
        self._watcher.start()

    def _watch(self) -> None:
        """胶囊开着：鼠标在胶囊外面按下了就收起（这一下照常落到按的地方）；一句话的胶囊鼠标走远了（LEAVE_PX）也收。"""
        down = native.mouse_any_down()
        if not down:
            self._armed = True
        elif self._armed and not self.geometry().contains(QCursor.pos()):
            self.hide()
            return
        if self.action and self._far(QCursor.pos()):
            self.hide()

    def _far(self, cursor) -> bool:
        """鼠标离画出来的那颗胶囊超过 LEAVE_PX（跟着大小）。"""
        r = self.pill_rect().translated(QPointF(self.pos()))
        dx = max(r.left() - cursor.x(), 0.0, cursor.x() - r.right())
        dy = max(r.top() - cursor.y(), 0.0, cursor.y() - r.bottom())
        return math.hypot(dx, dy) > LEAVE_PX * self._k

    def toggle(self) -> None:
        self.on = not self.on
        sounds.play("switch-on" if self.on else "switch-off")
        if self._callback is not None:
            self._callback(self.on)
        self._clock.start()

    def set_on(self, on: bool) -> None:
        """别处切了这个开关（设置卡片、「···」旁边的胶囊）：圆钮跟过去，不响、不回调；没显示着就直接到位。"""
        if on == self.on:
            return
        self.on = bool(on)
        if self.isVisible():
            self._clock.start()
        else:
            self._pos = 1.0 if self.on else 0.0

    def _tick(self, dt: float) -> bool:
        if self._pop_t is not None:
            self._pop_t += dt
            if self._pop_t >= POP_S:
                self._pop_t = None
        target = 1.0 if self.on else 0.0
        if self._pos != target:
            step = dt / SLIDE_S
            self._pos = min(target, self._pos + step) if target > self._pos else max(target, self._pos - step)
        self.update()
        return self._pop_t is not None or self._pos != target

    def showEvent(self, event) -> None:
        native.set_all_spaces(self, True)      # 程序的每个窗口都在所有桌面上，激活时 macOS 就不会跳桌面
        native.set_no_activate(self)           # 点它不把程序切到前台（native.set_no_activate）
        native.set_level(self, native.LEVEL_TOP)   # 最前面一层：狗、物件、球都盖不住它
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._watcher.stop()
        self._clock.stop()
        self._pop_t = None
        self._pos = 1.0 if self.on else 0.0
        super().hideEvent(event)

    def mouseMoveEvent(self, event) -> None:
        hot = self.pill_rect().contains(event.position())
        if hot != self._hot:
            self._hot = hot
            self.setCursor(Qt.PointingHandCursor if hot else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event) -> None:
        self._hot = False
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.pill_rect().contains(event.position()):
            if self.action:
                act = self._act
                sounds.play("switch-off")            # 收起这一件：和「物件」页、道具栏关掉同一个开关、同一声
                self.hide()
                if act is not None:
                    act()
            else:
                self.toggle()
        event.accept()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        amount = 1.0
        if self._pop_t is not None:              # 弹出中：从点的地方放大、带回弹
            s = POP_FROM + (1.0 - POP_FROM) * bounce(self._pop_t, *BOUNCE)
            amount = ease_out(self._pop_t / POP_FADE_S)
            pivot = QPointF(min(max(self._origin.x(), 0.0), self.width()), min(max(self._origin.y(), 0.0), self.height()))
            p.translate(pivot)
            p.scale(s, s)
            p.translate(-pivot)
        if self.action:
            overlay.draw_posture_strip(p, [(self.pill_rect(), self.text, 0.0, 1.0 if self._hot else 0.0, 0.0)], amount, overlay.MENU_BASE_H * self._k)
        else:
            overlay.draw_switch_pill(p, self.pill_rect(), self.text, self._pos, 1.0 if self._hot else 0.0, 0.0, amount,
                                     overlay.MENU_BASE_H * self._k, self._accent)
        p.end()
