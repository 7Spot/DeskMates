"""狗说话的气泡（尾巴指着狗，像狗说的）。
样子和设置里的说明气泡一样（widgets.StickerTip：描边、阴影、歪 2°），大小跟着狗的菜单倍率。只显示、点不到，狗动它跟着动，一会儿自己消失。
头顶放得下就放头顶、尾巴朝下，朝着狗脸那边伸出去；放不下（狗站在贴着屏幕顶的窗口上）就放在头旁边，尾巴横着指过去。不出屏幕。"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QFontMetrics, QPainterPath

from widget import native, sticker
from widget.widgets import StickerTip


class DogBubble(StickerTip):
    SHOW_S, FADE_S = 2.5, 0.2          # 停多久、最后这么久淡出（秒）
    BASE_WRAP, BASE_PAD_X, BASE_PAD_Y, BASE_TAIL, BASE_M = 240, 12, 9, 7.0, 12
    EDGE = 3                           # 离屏幕边至少这么多像素

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self._k = 1.0
        self._left = 0.0
        self._tail_at = 20.0           # 尾巴在气泡这条边上的哪（从左 / 从上算，像素）
        self._placed = "above"         # above：头顶，尾巴朝下；right / left：气泡在头的右边 / 左边

    def showEvent(self, event) -> None:
        super().showEvent(event)
        native.set_level(self, native.LEVEL_TOP)   # 最前面一层：狗把头伸进菜单栏那条、球和物件在旁边时气泡都在上面
        native.set_ignores_mouse(self, True)

    def say(self, text: str, k: float) -> None:
        """准备说这句话：定大小，计时重来。摆好位置（follow）再 present。"""
        self.text, self._k = text, k
        self._font.setPixelSize(max(11, round(13 * k)))
        self.PAD_X, self.PAD_Y, self.TAIL, self.M = self.BASE_PAD_X * k, self.BASE_PAD_Y * k, self.BASE_TAIL * k, round(self.BASE_M * k)
        box = QFontMetrics(self._font).boundingRect(QRect(0, 0, round(self.BASE_WRAP * k), 1000), Qt.TextWordWrap, text)
        self.setFixedSize(math.ceil(box.width() + 2 * self.PAD_X) + 2 * self.M, math.ceil(box.height() + 2 * self.PAD_Y) + 2 * self.M)
        self._left = self.SHOW_S
        self.setWindowOpacity(1.0)

    def present(self) -> None:
        self._pop = 1.0 if native.reduce_motion() else 0.0
        self.show()
        self.update()
        if self._pop < 1.0:
            self._clock.start()

    def follow(self, x: float, top: float, reach: float, facing: float, screen: QRect, dt: float) -> None:
        """摆到狗头旁边并计时。(x, top)：头顶（全局坐标）；reach：头左右多宽（像素）；facing：狗朝右 +1、朝左 -1；screen：这块屏。"""
        k, m = self._k, self.M
        bw, bh = self.width() - 2 * m, self.height() - 2 * m
        gap, tail = 3.0 * k, self.TAIL
        lo, hi = screen.left() + self.EDGE, screen.left() + screen.width() - self.EDGE
        low, high = screen.top() + self.EDGE, screen.top() + screen.height() - self.EDGE
        y = top - gap - tail - bh
        if y >= low:
            self._placed = "above"
            inset = min(26.0 * k, bw / 2.0)
            left = x - inset if facing > 0 else x - (bw - inset)
            left = min(max(left, lo), hi - bw)
            margin = min(14.0 * k, bw / 2.0)
            self._tail_at = min(max(x - left, margin), bw - margin)
        else:
            right_x = x + reach + gap + tail
            left_x = x - reach - gap - tail - bw
            fits_right, fits_left = right_x + bw <= hi, left_x >= lo
            on_right = fits_right if facing > 0 and fits_right or not fits_left else False
            self._placed = "right" if on_right else "left"
            left = right_x if on_right else left_x
            y = min(max(top, low), high - bh)
            margin = min(12.0 * k, bh / 2.0)
            self._tail_at = min(max(top + 0.12 * bh - y, margin), bh - margin)
        self.move(round(left) - m, round(y) - m)
        self.update()
        if dt > 0.0:
            self._left -= dt
            if self._left <= 0.0:
                self.hide()
            elif self._left < self.FADE_S:
                self.setWindowOpacity(self._left / self.FADE_S)

    def tail_tip(self, r: QRectF) -> QPointF:
        if self._placed == "above":
            return QPointF(r.left() + self._tail_at, r.bottom() + self.TAIL)
        if self._placed == "right":
            return QPointF(r.left() - self.TAIL, r.top() + self._tail_at)
        return QPointF(r.right() + self.TAIL, r.top() + self._tail_at)

    def tail_global(self) -> QPointF:
        """尾巴尖在屏幕上的哪（测试用）。"""
        return self.tail_tip(QRectF(self.rect()).adjusted(self.M, self.M, -self.M, -self.M)) + QPointF(self.pos())

    def shape(self, r: QRectF) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(r, sticker.RADIUS_TIP, sticker.RADIUS_TIP)
        tip, w = self.tail_tip(r), 7.0 * self._k
        tail = QPainterPath()
        if self._placed == "above":
            tail.moveTo(QPointF(tip.x() - w, r.bottom() - 1))
            tail.lineTo(tip)
            tail.lineTo(QPointF(tip.x() + w, r.bottom() - 1))
        else:
            edge = r.left() + 1 if self._placed == "right" else r.right() - 1
            tail.moveTo(QPointF(edge, tip.y() - w))
            tail.lineTo(tip)
            tail.lineTo(QPointF(edge, tip.y() + w))
        tail.closeSubpath()
        return path.united(tail)
